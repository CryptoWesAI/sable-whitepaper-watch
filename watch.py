#!/usr/bin/env python3
"""
Sable whitepaper watch.

Fetches the Sable Network whitepaper every run, and when the file changes:
  - keeps the PDF as evidence (snapshots/),
  - extracts the text (whitepaper.txt, faithful layout) and a sentence-per-line
    version (whitepaper.sentences.txt) that ignores line reflow,
  - writes a unified diff of the sentences (diffs/),
  - prepends an entry to CHANGELOG.md.

Every run also appends one compact line to status/log.jsonl from Sable's
public endpoints: /v1/status, /v1/nodes, /v1/receipts/pubkey, /v1/models.
A change of the receipt signer address is flagged loudly, because every
receipt ever issued verifies against it.

Independent. Not affiliated with Sable Network. Reads only public URLs.

Usage:
  python watch.py                 # normal run
  python watch.py --pdf FILE      # seed a run from a local PDF (history import)
  python watch.py --no-status     # skip the status ledger
"""
import argparse, datetime, difflib, hashlib, json, os, re, subprocess, sys, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
PDF_URL = "https://www.buildsable.com/sable-whitepaper.pdf"
API = "https://api.buildsable.com/v1/"
UA = "sable-whitepaper-watch (+https://github.com/CryptoWesAI/sable-whitepaper-watch)"
STATE = os.path.join(ROOT, "state")
SNAP = os.path.join(ROOT, "snapshots")
DIFFS = os.path.join(ROOT, "diffs")
STATUS = os.path.join(ROOT, "status")


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def stamp(t):
    return t.strftime("%Y-%m-%d-%H%M")


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def read(path, default=""):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return default


def write(path, data, mode="w"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode, encoding=None if "b" in mode else "utf-8", newline=None if "b" in mode else "\n") as f:
        f.write(data)


def pdftotext(pdf_path):
    out = subprocess.run(["pdftotext", "-layout", pdf_path, "-"], capture_output=True, check=True)
    return out.stdout.decode("utf-8", "replace")


def sentences(text):
    """Collapse layout so that a re-rendered PDF with different line breaks
    does not show up as a change. One sentence per line."""
    flat = re.sub(r"\s+", " ", text).strip()
    # A word hyphenated across a line break comes out as "TEE- attested".
    # Re-join it so a re-render that moves the break is not a "change".
    flat = re.sub(r"(\w)- (?=[a-z0-9])", r"\1-", flat)
    flat = re.sub(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])", "\n", flat)
    return "\n".join(s.strip() for s in flat.split("\n") if s.strip()) + "\n"


def cover_version(text):
    m = re.search(r"(\d+\.\d+)\s*-+\s*([A-Z][a-z]+ 20\d\d)", text)
    return f"v{m.group(1)}, {m.group(2)}" if m else "version line not found"


def set_output(key, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def whitepaper(args):
    t = now()
    if args.pdf:
        with open(args.pdf, "rb") as f:
            pdf = f.read()
        source = f"{PDF_URL}, from a copy saved on {args.label or 'an earlier date'} and imported into this record"
    else:
        pdf = fetch(PDF_URL)
        source = PDF_URL
    sha = hashlib.sha256(pdf).hexdigest()
    prev_sha = read(os.path.join(STATE, "whitepaper.sha256")).strip()
    if sha == prev_sha:
        print(f"whitepaper unchanged ({sha[:12]}, {len(pdf)} bytes)")
        set_output("changed", "false")
        return False

    label = args.label or stamp(t)
    snap_path = os.path.join(SNAP, f"whitepaper-{label}.pdf")
    write(snap_path, pdf, "wb")
    text = pdftotext(snap_path)
    sent = sentences(text)
    prev_sent = read(os.path.join(ROOT, "whitepaper.sentences.txt"))
    version = cover_version(text)

    added = removed = 0
    diff_rel = None
    if prev_sent:
        diff = list(difflib.unified_diff(prev_sent.splitlines(), sent.splitlines(),
                                         fromfile="previous", tofile=label, lineterm="", n=1))
        added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
        diff_rel = f"diffs/{label}.diff"
        write(os.path.join(ROOT, diff_rel), "\n".join(diff) + "\n")

    write(os.path.join(ROOT, "whitepaper.txt"), text)
    write(os.path.join(ROOT, "whitepaper.sentences.txt"), sent)
    write(os.path.join(STATE, "whitepaper.sha256"), sha + "\n")

    entry = [f"## {label}", "",
             f"- Cover says: **{version}**",
             f"- File: {len(pdf):,} bytes, sha256 `{sha}`",
             f"- Source: {source}",
             f"- Snapshot: [`{os.path.relpath(snap_path, ROOT).replace(os.sep, '/')}`]({os.path.relpath(snap_path, ROOT).replace(os.sep, '/')})"]
    if diff_rel:
        entry.append(f"- Change vs previous text: **{added} sentences added, {removed} removed** ([diff]({diff_rel}))")
    else:
        entry.append("- First snapshot in this record; nothing to diff against.")
    entry += ["", ""]
    changelog = read(os.path.join(ROOT, "CHANGELOG.md"))
    head = "# Sable whitepaper changelog\n\nNewest first. Every entry is a snapshot of the PDF as served at buildsable.com/sable-whitepaper.pdf, with the extracted text diffed sentence by sentence so that line reflow does not count as a change.\n\n"
    body = changelog[len(head):] if changelog.startswith(head) else changelog
    write(os.path.join(ROOT, "CHANGELOG.md"), head + "\n".join(entry) + body)

    summary = f"whitepaper CHANGED: {version}; {len(pdf):,} bytes; +{added}/-{removed} sentences"
    print(summary)
    set_output("changed", "true")
    set_output("summary", summary)
    set_output("label", label)
    return True


def status_ledger():
    t = now()
    row = {"t": t.strftime("%Y-%m-%dT%H:%M:%SZ")}
    try:
        s = json.loads(fetch(API + "status", 12))
        c = s.get("confidential") or {}
        row["status"] = s.get("status")
        row["uptime_24h"] = s.get("uptime_24h_pct")
        row["uptime_30d"] = s.get("uptime_30d_pct")
        row["conf_verified"] = c.get("verified")
        row["conf_error"] = c.get("error_class")
        row["conf_failures"] = c.get("consecutive_failures")
        row["conf_backends"] = f"{c.get('verified_backends')}/{c.get('total_backends')}"
        row["sandbox_ok"] = (s.get("sandbox") or {}).get("ok")
    except Exception as e:
        row["status"] = f"unreachable: {type(e).__name__}"
    try:
        nodes = json.loads(fetch(API + "nodes", 12))
        row["nodes"] = [f"{n.get('id')}:{n.get('status')}" for n in nodes]
        row["third_party_nodes"] = sum(1 for n in nodes if not n.get("synthetic") and n.get("id") != "gateway")
    except Exception as e:
        row["nodes"] = f"unreachable: {type(e).__name__}"
    signer_flag = ""
    try:
        p = json.loads(fetch(API + "receipts/pubkey", 12))
        row["signer"] = p.get("signer_address")
        row["scheme"] = p.get("scheme")
        prev = read(os.path.join(STATE, "signer.txt")).strip()
        if prev and p.get("signer_address") and prev.lower() != p["signer_address"].lower():
            signer_flag = f"SIGNER CHANGED: {prev} -> {p['signer_address']}"
            row["signer_changed_from"] = prev
        if p.get("signer_address"):
            write(os.path.join(STATE, "signer.txt"), p["signer_address"] + "\n")
    except Exception as e:
        row["signer"] = f"unreachable: {type(e).__name__}"
    try:
        m = json.loads(fetch(API + "models", 12))
        data = m.get("data", [])
        row["models"] = len(data)
        row["confidential_models"] = [x["id"] for x in data if x.get("privacy_tier") == "confidential"]
        fast = next((x for x in data if x.get("id") == "sable-fast"), None)
        if fast:
            row["sable_fast_usd_per_mtok"] = [fast.get("prompt_usd_per_mtok"), fast.get("completion_usd_per_mtok")]
    except Exception as e:
        row["models"] = f"unreachable: {type(e).__name__}"
    write(os.path.join(STATUS, "log.jsonl"), json.dumps(row, separators=(",", ":")) + "\n", "a")
    print("status:", json.dumps(row))
    if signer_flag:
        print(signer_flag)
        set_output("signer_changed", "true")
        set_output("signer_summary", signer_flag)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", help="seed from a local PDF instead of fetching")
    ap.add_argument("--label", help="label for the snapshot (default: UTC timestamp)")
    ap.add_argument("--no-status", action="store_true")
    ap.add_argument("--reset", action="store_true",
                    help="start the record over: removes the generated files under this directory (snapshots, diffs, status, state, texts, changelog)")
    args = ap.parse_args()
    if args.reset:
        import shutil
        for d in ("state", "snapshots", "diffs", "status"):
            shutil.rmtree(os.path.join(ROOT, d), ignore_errors=True)
        for f in ("CHANGELOG.md", "whitepaper.txt", "whitepaper.sentences.txt"):
            try:
                os.remove(os.path.join(ROOT, f))
            except FileNotFoundError:
                pass
        print("record reset")
        if not args.pdf:
            return 0
    changed = whitepaper(args)
    if not args.no_status:
        status_ledger()
    return 0 if True else 1


if __name__ == "__main__":
    sys.exit(main())
