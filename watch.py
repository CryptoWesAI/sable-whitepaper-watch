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
import sections

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
    # poppler on Linux renders the cover's dash as an em dash, on Windows as "--"
    m = re.search(r"(\d+\.\d+)\s*[-‐-―]+\s*([A-Z][a-z]+ 20\d\d)", text)
    return f"v{m.group(1)}, {m.group(2)}" if m else "version line not found"


def set_output(key, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def whitepaper(args):
    t = now()
    fail_path = os.path.join(STATE, "pdf_fetch_failures.txt")
    if args.pdf:
        with open(args.pdf, "rb") as f:
            pdf = f.read()
        source = f"{PDF_URL}, from a copy saved on {args.label or 'an earlier date'} and imported into this record"
    else:
        try:
            pdf = fetch(PDF_URL)
        except Exception as e:
            # Sable's site stalls now and then. One miss is not news; a day of
            # misses means the URL moved or the watch is broken, and then the
            # job must go red so a human gets GitHub's failure email.
            n = int(read(fail_path, "0").strip() or 0) + 1
            write(fail_path, f"{n}\n")
            print(f"whitepaper fetch failed ({type(e).__name__}: {e}); consecutive failures: {n}")
            set_output("changed", "false")
            if n >= 24:
                raise SystemExit(f"whitepaper unreachable for {n} consecutive runs; check {PDF_URL}")
            return False
        write(fail_path, "0\n")
        source = PDF_URL
    if not pdf.startswith(b"%PDF"):
        print("fetched something that is not a PDF; not recording it")
        set_output("changed", "false")
        return False
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

    material = (added + removed) > 0 or not prev_sent
    summary = f"whitepaper CHANGED: {version}; {len(pdf):,} bytes; +{added}/-{removed} sentences" + ("" if material else " (file re-rendered, no sentence changed)")
    print(summary)
    # "changed" drives the commit message and the alert. A re-rendered PDF with
    # identical sentences is recorded in the changelog but never announced,
    # so the alert channel only ever carries real changes.
    set_output("changed", "true" if material else "false")
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


def html_text(raw):
    """Visible text of an HTML page: no scripts, styles, tags or comments."""
    import html as htmlmod
    s = re.sub(r"(?is)<(script|style|noscript|svg|template)[^>]*>.*?</\1>", " ", raw)
    s = re.sub(r"(?s)<!--.*?-->", " ", s)
    s = re.sub(r"(?i)</(p|div|li|h[1-6]|tr|td|th|br|section|article|header|footer|dt|dd)>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    return htmlmod.unescape(s)


def peers_watch(label=None):
    """One canonical public page per project, diffed as sentences. Records
    only that a page changed and by how much, with the diff. Never what it
    means. Sable's own pages are on the list too."""
    cfg = json.loads(read(os.path.join(ROOT, "peers.json"), "[]"))
    rec_path = os.path.join(ROOT, "peers-record.json")
    rec = json.loads(read(rec_path, "{}"))
    t = now()
    label = label or stamp(t)
    ts = t.strftime("%Y-%m-%dT%H:%M:%SZ")
    for p in cfg:
        pid = p["id"]
        entry = rec.get(pid) or {"id": pid, "changes": []}
        entry["name"], entry["url"], entry["last_check"] = p["name"], p["url"], ts
        try:
            raw = fetch(p["url"], 25).decode("utf-8", "replace")
        except Exception as e:
            entry["ok"] = False
            entry["error"] = type(e).__name__
            rec[pid] = entry
            print(f"peer {pid}: unreachable ({type(e).__name__})")
            continue
        entry["ok"] = True
        entry.pop("error", None)
        sent = sentences(html_text(raw))
        if len(sent) < 200:
            # A page that renders only in the browser has almost no server-side
            # text. Record that honestly rather than diffing an empty shell.
            entry["thin"] = True
        prev_path = os.path.join(STATE, "peers", pid + ".txt")
        prev = read(prev_path)
        if prev == sent:
            rec[pid] = entry
            print(f"peer {pid}: unchanged")
            continue
        if prev:
            diff = list(difflib.unified_diff(prev.splitlines(), sent.splitlines(),
                                             fromfile="previous", tofile=label, lineterm="", n=1))
            added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
            removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
            diff_rel = f"diffs/peers/{pid}-{label}.diff"
            write(os.path.join(ROOT, diff_rel), "\n".join(diff) + "\n")
            entry["changes"] = ([{"label": label, "added": added, "removed": removed, "diff": diff_rel}] + entry.get("changes", []))[:30]
            entry["last_change"] = label
            print(f"peer {pid}: CHANGED +{added}/-{removed}")
        else:
            entry["first_seen"] = label
            print(f"peer {pid}: first snapshot")
        write(prev_path, sent)
        rec[pid] = entry
    rec["_generated_at"] = ts
    write(rec_path, json.dumps(rec, indent=1) + "\n")


def record_json():
    """Machine-readable summary for sable.primecircle.cloud, which reads it
    from the raw GitHub URL at page load. Built from CHANGELOG.md and the last
    ledger line, so it is always consistent with the human-readable record."""
    entries = []
    changelog = read(os.path.join(ROOT, "CHANGELOG.md"))
    for block in re.split(r"^## ", changelog, flags=re.M)[1:]:
        lines = block.strip().splitlines()
        label = lines[0].strip()
        e = {"label": label}
        for l in lines[1:]:
            m = re.search(r"Cover says: \*\*(.+?)\*\*", l)
            if m: e["cover"] = m.group(1)
            m = re.search(r"File: ([\d,]+) bytes, sha256 `([0-9a-f]+)`", l)
            if m: e["bytes"] = int(m.group(1).replace(",", "")); e["sha256"] = m.group(2)
            m = re.search(r"Snapshot: \[`([^`]+)`\]", l)
            if m: e["snapshot"] = m.group(1)
            m = re.search(r"\*\*(\d+) sentences added, (\d+) removed\*\* \(\[diff\]\(([^)]+)\)\)", l)
            if m: e["added"] = int(m.group(1)); e["removed"] = int(m.group(2)); e["diff"] = m.group(3)
            if "First snapshot" in l: e["first"] = True
        entries.append(e)
    last = None
    try:
        with open(os.path.join(STATUS, "log.jsonl"), encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last = json.loads(line)
    except FileNotFoundError:
        pass
    out = {
        "generated_at": now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pdf_url": PDF_URL,
        "repo": "https://github.com/CryptoWesAI/sable-whitepaper-watch",
        "raw_base": "https://github.com/CryptoWesAI/sable-whitepaper-watch/blob/main/",
        "cover": entries[0].get("cover") if entries else None,
        "entries": entries,
        "last_check": last,
    }
    write(os.path.join(ROOT, "record.json"), json.dumps(out, indent=1) + "\n")
    print(f"record.json: {len(entries)} entries")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", help="seed from a local PDF instead of fetching")
    ap.add_argument("--label", help="label for the snapshot (default: UTC timestamp)")
    ap.add_argument("--no-status", action="store_true")
    ap.add_argument("--peers", action="store_true", help="also check the per-project pages in peers.json (meant to run daily)")
    ap.add_argument("--whitepaper-json", action="store_true",
                    help="only rebuild whitepaper.json (sections and sentences, with the snapshot each first appeared in) from the PDFs in snapshots/")
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
    if args.whitepaper_json:
        sections.build(ROOT, pdftotext, sentences, cover_version, PDF_URL)
        return 0
    whitepaper(args)
    sections.build(ROOT, pdftotext, sentences, cover_version, PDF_URL)
    if not args.no_status:
        status_ledger()
    if args.peers:
        peers_watch(args.label)
    record_json()
    return 0


if __name__ == "__main__":
    sys.exit(main())
