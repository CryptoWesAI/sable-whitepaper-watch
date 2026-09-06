"""Cut the whitepaper into its numbered sections and sentences, and record the
snapshot in which each sentence first appeared and, for sentences that are
gone, the snapshot in which they disappeared.

Written for the Orrery on sable.primecircle.cloud, which reads whitepaper.json
at page load: every planet is a section, every dot a sentence, and a dot that
arrived after the first snapshot glows with its date.

Rebuilt from every PDF in snapshots/ on each run, so the file can never drift
from the record it is derived from.
"""
import datetime
import glob
import json
import os
import re

HEAD = re.compile(r"^\s*(0[1-9]|1[0-3])\s+(\S[^\n]*?)\s*$")
SECOND_COLUMN = re.compile(r"\s{2,}(0[1-9]|1[0-3]|A)\s+[A-Z]")
APPENDIX = re.compile(r"^\s*A\s+Appendix\b(.*)$")
FOOTER = re.compile(r"^\s*SABLE NETWORK\b.*BUILDSABLE\.COM\s*$", re.I)
MIN_WORDS = 3
ENDS = re.compile(r"[.!?\"”')\]]$")


def is_sentence(t):
    """Figure labels and table cells come out of the layout as short fragments
    without a full stop ("SABLE GATEWAY", "USDT deposits, x402 Built"). A
    sentence has at least three words and ends like one."""
    return len(t.split()) >= MIN_WORDS and bool(ENDS.search(t))


def clean_title(t):
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"^\W+", "", t)          # "-- API surface" -> "API surface"
    return t


def split_sections(text):
    """Return [{n, title, text}] in document order. The contents page lists the
    same headings, sometimes two per line; the body heading is the last line
    that is exactly "NN Title", so that one wins."""
    lines = text.splitlines()
    last = {}
    for i, line in enumerate(lines):
        m = HEAD.match(line)
        if m and not SECOND_COLUMN.search(m.group(2)):
            last[m.group(1)] = (i, m.group(2))
        m = APPENDIX.match(line)
        if m and not SECOND_COLUMN.search(m.group(1)):
            last["A"] = (i, "Appendix: " + clean_title(m.group(1)))
    order = sorted(last.items(), key=lambda kv: kv[1][0])
    out = []
    for k, (n, (i, title)) in enumerate(order):
        j = order[k + 1][1][0] if k + 1 < len(order) else len(lines)
        body = [l for l in lines[i + 1:j] if not FOOTER.match(l) and not re.match(r"^\s*\d{1,2}\s*$", l)]
        out.append({"n": n, "title": clean_title(title), "text": "\n".join(body)})
    return out


def label_of(pdf_path):
    return re.sub(r"^whitepaper-|\.pdf$", "", os.path.basename(pdf_path))


def build(root, pdftotext, sentences, cover_version, pdf_url):
    snaps = sorted(glob.glob(os.path.join(root, "snapshots", "whitepaper-*.pdf")), key=label_of)
    if not snaps:
        print("whitepaper.json: no snapshots yet")
        return None
    labels = [label_of(p) for p in snaps]
    seen = {}       # sentence -> {"first": label, "last": label, "n": section}
    latest = None
    for path, label in zip(snaps, labels):
        text = pdftotext(path)
        secs = split_sections(text)
        current = {}
        for s in secs:
            for t in sentences(s["text"]).splitlines():
                t = t.strip()
                if not is_sentence(t):
                    continue
                current.setdefault(s["n"], []).append(t)
                e = seen.get(t)
                if e:
                    e["last"] = label
                else:
                    seen[t] = {"first": label, "last": label, "n": s["n"]}
        latest = (label, secs, current, cover_version(text))
    label, secs, current, cover = latest
    first_label = labels[0]

    def removed_in(last_seen):
        i = labels.index(last_seen)
        return labels[i + 1] if i + 1 < len(labels) else None

    sections = []
    total = 0
    for s in secs:
        n = s["n"]
        sents = current.get(n, [])
        items = [{"t": t, "s": seen[t]["first"]} for t in sents]
        ghosts = [{"t": t, "s": e["first"], "gone": removed_in(e["last"])}
                  for t, e in seen.items() if e["n"] == n and e["last"] != label]
        dates = [i["s"] for i in items if i["s"] != first_label] + [g["gone"] for g in ghosts if g["gone"]]
        changed = max(dates) if dates else None
        total += len(items)
        sections.append({
            "n": n,
            "title": s["title"],
            "count": len(items),
            "words": sum(len(t.split()) for t in sents),
            "changed": changed,
            "added": sum(1 for i in items if changed and i["s"] == changed),
            "removed": sum(1 for g in ghosts if changed and g["gone"] == changed),
            "sentences": items,
            "ghosts": ghosts,
        })
    out = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pdf_url": pdf_url,
        "cover": cover,
        "snapshots": labels,
        "first": first_label,
        "latest": label,
        "sentence_count": total,
        "sections": sections,
    }
    path = os.path.join(root, "whitepaper.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=0)
        f.write("\n")
    changed_secs = [s["n"] for s in sections if s["changed"]]
    print(f"whitepaper.json: {len(sections)} sections, {total} sentences, {len(labels)} snapshots, changed: {', '.join(changed_secs) or 'none'}")
    return out
