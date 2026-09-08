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

The same line carries the SABL supply as Solana reports it (getTokenSupply on
the mint). status/supply.jsonl gets a line only when that supply changes, and
a fall gets a CHANGELOG entry: the whitepaper says paying in SABL burns it and
that the rail is not live yet, so the first fall of the mint supply is that
rail going live on-chain, whatever the announcements say.

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


def post_json(url, body, timeout=25):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


# The token, as the chain and the market report it. SABL's mint on Solana; the
# supply can only fall (no mint authority), so the row records it every hour
# next to the market figures, and the site draws the burn and the day-by-day
# movement from this ledger rather than from an API's own change field.
SABL_MINT = "DaPayqzdCXcrmvgz9Wx7MySipXxcSofGPtkMgVdqpump"
# A public read-only JSON-RPC node. Set SOLANA_RPC=https://... to read from
# another one. The watch only ever reads; it holds no key and signs nothing.
SOLANA_RPC = os.environ.get("SOLANA_RPC") or "https://api.mainnet-beta.solana.com"
DEXSCREENER = "https://api.dexscreener.com/latest/dex/tokens/" + SABL_MINT
SUPPLY_LEDGER = os.path.join(STATUS, "supply.jsonl")


def read_supply():
    """One getTokenSupply call. Raises on any failure; the callers decide what
    a miss means. The amount is kept as the integer string the node gave, so
    no float ever touches it, and the slot says when the answer was read."""
    r = post_json(SOLANA_RPC, {"jsonrpc": "2.0", "id": 1, "method": "getTokenSupply", "params": [SABL_MINT]}, 15)
    if "error" in r:
        raise RuntimeError(f"rpc error {r['error'].get('code')}: {r['error'].get('message')}")
    v = r["result"]["value"]
    amount = str(v["amount"])
    if not amount.isdigit():
        raise ValueError(f"amount is not an integer string: {amount!r}")
    dec = int(v["decimals"])
    ui = v.get("uiAmount")
    if not isinstance(ui, (int, float)):
        ui = int(amount) / (10 ** dec)
    return {"amount": amount, "decimals": dec, "ui_amount": float(ui), "slot": (r["result"].get("context") or {}).get("slot")}


def fmt_sabl(base_units, decimals):
    """'958,374,438.918883' from an integer number of base units, no float."""
    sign = "-" if base_units < 0 else ""
    q, r = divmod(abs(int(base_units)), 10 ** decimals)
    return f"{sign}{q:,}" + (f".{r:0{decimals}d}" if decimals else "")


def token_row(sup=None):
    """supply (whole tokens), mint authority, market cap, price, liquidity, 24 h volume.
    `sup` is the run's getTokenSupply answer (or the exception it raised), so
    the node is asked once per run."""
    out = {}
    try:
        if sup is None:
            sup = read_supply()
        if isinstance(sup, Exception):
            raise sup
        out["supply"] = round(int(sup["amount"]) / (10 ** int(sup["decimals"])), 6)
    except Exception as e:
        out["supply"] = f"unreachable: {type(e).__name__}"
    try:
        r = post_json(SOLANA_RPC, {"jsonrpc": "2.0", "id": 1, "method": "getAccountInfo", "params": [SABL_MINT, {"encoding": "jsonParsed"}]}, 20)
        info = r["result"]["value"]["data"]["parsed"]["info"]
        out["mint_authority"] = info.get("mintAuthority")
        out["freeze_authority"] = info.get("freezeAuthority")
    except Exception as e:
        out["mint_authority"] = f"unreachable: {type(e).__name__}"
    try:
        d = json.loads(fetch(DEXSCREENER, 20))
        pairs = d.get("pairs") or []
        pair = next((x for x in pairs if x.get("dexId") == "pumpswap"), pairs[0] if pairs else None)
        if pair:
            out["mcap"] = pair.get("marketCap")
            out["price_usd"] = float(pair["priceUsd"]) if pair.get("priceUsd") else None
            out["liq_usd"] = (pair.get("liquidity") or {}).get("usd")
            out["vol_24h"] = (pair.get("volume") or {}).get("h24")
            out["change_24h"] = (pair.get("priceChange") or {}).get("h24")
    except Exception as e:
        out["mcap"] = f"unreachable: {type(e).__name__}"
    return out


def supply_watch(t, sup, err):
    """The burn watch. status/supply.jsonl gets a line only when the raw amount
    differs from its last line (the first run writes the baseline), and a fall
    gets a CHANGELOG entry: the whitepaper says paying in SABL burns it, so the
    first fall of the mint supply is that rail live on-chain. Returns the
    fields for the hourly ledger row. Never raises: a miss is recorded, not
    fatal."""
    ts = t.strftime("%Y-%m-%dT%H:%M:%SZ")
    if sup is None:
        print(f"sabl supply: unreadable ({err})")
        return {"sabl_supply": None, "sabl_supply_error": err}
    fields = {"sabl_supply": {"amount": sup["amount"], "decimals": sup["decimals"], "ui_amount": sup["ui_amount"], "slot": sup["slot"]}}
    try:
        dec = sup["decimals"]
        cur = int(sup["amount"])
        slot_s = f"{sup['slot']:,}" if isinstance(sup["slot"], int) else str(sup["slot"])
        last = None
        for line in read(SUPPLY_LEDGER).splitlines():
            if line.strip():
                last = json.loads(line)
        if last is None:
            entry = {"t": ts, "slot": sup["slot"], "decimals": dec, "prev_amount": None, "amount": sup["amount"],
                     "delta": None, "ui_amount": sup["ui_amount"], "ui_delta": None, "baseline": True}
            write(SUPPLY_LEDGER, json.dumps(entry, separators=(",", ":")) + "\n", "a")
            print(f"sabl supply: baseline {fmt_sabl(cur, dec)} SABL at slot {slot_s}")
        elif str(last.get("amount")) != sup["amount"]:
            prev = int(last["amount"])
            delta = cur - prev
            entry = {"t": ts, "slot": sup["slot"], "decimals": dec, "prev_amount": str(prev), "amount": sup["amount"],
                     "delta": str(delta), "ui_amount": sup["ui_amount"], "ui_delta": delta / (10 ** dec)}
            write(SUPPLY_LEDGER, json.dumps(entry, separators=(",", ":")) + "\n", "a")
            if delta < 0:
                summary = f"SABL supply FELL by {fmt_sabl(-delta, dec)} SABL: {fmt_sabl(prev, dec)} -> {fmt_sabl(cur, dec)} at slot {slot_s}"
                print(summary)
                changelog_prepend([
                    f"## {stamp(t)}: SABL supply fell", "",
                    f"- Supply fell by **{fmt_sabl(-delta, dec)} SABL** ({-delta:,} base units), from {fmt_sabl(prev, dec)} to {fmt_sabl(cur, dec)}.",
                    f"- Seen at {ts}, Solana slot {slot_s}, by `getTokenSupply` on {SOLANA_RPC} for mint `{SABL_MINT}`.",
                    "- The whitepaper (section 06) says paying in SABL burns it. A fall of the mint supply is a burn; the chain does not say who burned it or why. Every change of the supply is in [`status/supply.jsonl`](status/supply.jsonl).",
                    "", ""])
                set_output("supply_fell", "true")
                set_output("supply_summary", summary)
            else:
                # The mint authority is revoked, so a rise cannot be a mint.
                # Recorded as read, flagged here, never announced.
                print(f"SABL SUPPLY ROSE by {fmt_sabl(delta, dec)}: {fmt_sabl(prev, dec)} -> {fmt_sabl(cur, dec)}; "
                      "impossible with the mint authority revoked, so suspect the node's answer")
        else:
            print(f"sabl supply: unchanged {fmt_sabl(cur, dec)} SABL (slot {slot_s})")
    except Exception as e:
        print(f"sabl supply ledger failed: {type(e).__name__}: {e}")
        fields["sabl_supply_error"] = f"ledger: {type(e).__name__}: {e}"
    return fields


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


CHANGELOG_HEAD = ("# Sable whitepaper changelog\n\n"
                  "Newest first. Every entry is a snapshot of the PDF as served at buildsable.com/sable-whitepaper.pdf, "
                  "with the extracted text diffed sentence by sentence so that line reflow does not count as a change. "
                  "Since 8 September 2026 an entry is also written when the SABL supply on Solana falls: the whitepaper "
                  "says paying in SABL burns it, so a fall of the mint supply is that rail live on-chain.\n\n")


def changelog_prepend(entry_lines):
    """Newest first. The head paragraph is rewritten on every entry, so it can
    change without leaving two copies of itself in the file."""
    path = os.path.join(ROOT, "CHANGELOG.md")
    old = read(path)
    m = re.search(r"(?m)^## ", old)
    body = old[m.start():] if m else ""
    write(path, CHANGELOG_HEAD + "\n".join(entry_lines) + body)


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
    changelog_prepend(entry)

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


def conf_transition(prev, row):
    """A flip of the confidential tier between verified and failing closed,
    read from the previous ledger line and this one. Returns (kind, summary)
    with kind "recovered" or "failed", or None when nothing flipped. Either
    line without a boolean reading (an unreachable endpoint) is not a flip:
    a gateway that could not be asked has not recovered or failed."""
    if not prev or not isinstance(prev.get("conf_verified"), bool) or not isinstance(row.get("conf_verified"), bool):
        return None
    was, is_ok = prev["conf_verified"], row["conf_verified"]
    if was == is_ok:
        return None
    if is_ok:
        n = prev.get("conf_failures")
        after = f" after {n:,} consecutive refusals" if isinstance(n, int) else ""
        return ("recovered", f"Confidential tier verified again at {row['t']}{after}; last refusal seen {prev['t']}; backends {row.get('conf_backends')}")
    n = row.get("conf_failures")
    count = f", {n:,} consecutive refusals" if isinstance(n, int) else ""
    return ("failed", f"Confidential tier failing closed at {row['t']}: {row.get('conf_error') or 'unknown error'}{count}; last verified {prev['t']}")


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
    sup, sup_err = None, None
    try:
        sup = read_supply()
    except Exception as e:
        sup_err = f"{type(e).__name__}: {e}"[:200]
    row["token"] = token_row(sup if sup is not None else Exception(sup_err))
    row.update(supply_watch(t, sup, sup_err))
    # The previous line, so a flip of the confidential tier (failing closed to
    # verified, or the other way) gets its own commit message and a push to
    # the app. The ledger itself is the record; this only says when to look.
    prev_row = None
    try:
        lines = [l for l in read(os.path.join(STATUS, "log.jsonl")).splitlines() if l.strip()]
        if lines:
            prev_row = json.loads(lines[-1])
    except Exception:
        prev_row = None
    flip = conf_transition(prev_row, row)
    write(os.path.join(STATUS, "log.jsonl"), json.dumps(row, separators=(",", ":")) + "\n", "a")
    print("status:", json.dumps(row))
    if signer_flag:
        print(signer_flag)
        set_output("signer_changed", "true")
        set_output("signer_summary", signer_flag)
    if flip:
        print(flip[1])
        set_output("conf_flip", flip[0])
        set_output("conf_summary", flip[1])
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


def supply_summary(last_row, last_read):
    """record.json's view of the burn watch: the latest read, the baseline,
    the change since it, and the last change and last fall with their times.
    Absent until status/supply.jsonl has its first line, so the site shows
    nothing rather than a placeholder."""
    rows = [json.loads(l) for l in read(SUPPLY_LEDGER).splitlines() if l.strip()]
    if not rows:
        return None
    base, newest = rows[0], rows[-1]
    dec = int(newest.get("decimals", 6))
    latest = last_read or dict(newest, t=newest["t"])
    changes = [r for r in rows if not r.get("baseline")]
    falls = [r for r in changes if int(r["delta"]) < 0]
    since = int(latest["amount"]) - int(base["amount"])
    fallen = sum(-int(r["delta"]) for r in falls)

    def point(r):
        return {"t": r["t"], "amount": r["amount"], "ui_amount": r["ui_amount"], "slot": r.get("slot")}

    def change(r):
        return {"t": r["t"], "prev_amount": r["prev_amount"], "amount": r["amount"], "delta": r["delta"], "ui_delta": r["ui_delta"], "slot": r.get("slot")}

    out = {
        "mint": SABL_MINT,
        "rpc": SOLANA_RPC,
        "method": "getTokenSupply",
        "decimals": dec,
        "latest": point(latest),
        "baseline": point(base),
        "change_since_baseline": {"amount": str(since), "ui_amount": since / (10 ** dec)},
        "changes": len(changes),
        "last_change": change(changes[-1]) if changes else None,
        "falls": len(falls),
        "last_fall": change(falls[-1]) if falls else None,
        "total_fallen": {"amount": str(fallen), "ui_amount": fallen / (10 ** dec)},
        "ledger": "status/supply.jsonl",
    }
    if last_row and last_row.get("sabl_supply") is None and last_row.get("sabl_supply_error"):
        out["latest_error"] = {"t": last_row.get("t"), "error": last_row["sabl_supply_error"]}
    return out


def record_json():
    """Machine-readable summary for sable.primecircle.cloud, which reads it
    from the raw GitHub URL at page load. Built from CHANGELOG.md and the last
    ledger line, so it is always consistent with the human-readable record."""
    entries = []
    changelog = read(os.path.join(ROOT, "CHANGELOG.md"))
    for block in re.split(r"^## ", changelog, flags=re.M)[1:]:
        lines = block.strip().splitlines()
        label = lines[0].strip()
        if "SABL supply" in label:
            continue   # the burn entries are exposed under "sabl_supply" below, from status/supply.jsonl
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
    last_read = None   # the newest hourly line whose supply read succeeded
    try:
        with open(os.path.join(STATUS, "log.jsonl"), encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last = json.loads(line)
                    if isinstance(last.get("sabl_supply"), dict):
                        last_read = dict(last["sabl_supply"], t=last["t"])
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
    sup = supply_summary(last, last_read)
    if sup:
        out["sabl_supply"] = sup
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
