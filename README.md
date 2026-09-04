# Sable whitepaper watch

A public, independent record of what the [Sable Network](https://www.buildsable.com) whitepaper says, when it changed, and what changed. Plus an hourly line from Sable's public status endpoints, so a long fail-closed streak or a change of the receipt signer becomes a matter of record rather than memory.

Sable's own whitepaper says: *"Infrastructure whitepapers routinely describe a planned system in the present tense. We think that is the single most corrosive habit in this category."* It also says where its previous version was wrong. This repository exists because on 2 September 2026 the PDF changed (section 06 and section 10, on the token) without the cover version changing, and nobody would have known unless they happened to compare file sizes. A document that everything else is judged against deserves a witness.

**Not affiliated with Sable Network.** Reads only public URLs. Corrections welcome as issues or pull requests.

## What is in here

| Path | What |
|---|---|
| [`CHANGELOG.md`](CHANGELOG.md) | Newest first. One entry per change of the PDF: cover version, size, hash, snapshot, diff. |
| [`whitepaper.txt`](whitepaper.txt) | Current text, extracted with `pdftotext -layout`. Faithful, including line breaks. |
| [`whitepaper.sentences.txt`](whitepaper.sentences.txt) | Current text, one sentence per line. This is what gets diffed, so a re-rendered PDF with different line wrapping does not count as a change. |
| `diffs/` | Unified diff of the sentences for each change. |
| `snapshots/` | The PDF as served, for each change. Evidence, not summary. |
| [`status/log.jsonl`](status/log.jsonl) | One line per hour: gateway status, uptime, confidential backend verified or failing closed and why, node list, receipt signer address, model count and the `sable-fast` list price. |
| [`watch.py`](watch.py) | The whole thing. About 200 lines, standard library only. |

## How it runs

A GitHub Action runs [`watch.py`](watch.py) every hour. It downloads the PDF, hashes it, and only does work when the hash changes. The status ledger appends one line per run regardless. Commits are made by the Action; the history of this repository is the record.

If the whitepaper or the signer address changes and the repository has `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` secrets, it sends one message. Without them it stays quiet and just commits.

## Verify it yourself

Nothing here needs to be trusted. Fetch the PDF, hash it, compare with the newest entry in the changelog:

```sh
curl -sL https://www.buildsable.com/sable-whitepaper.pdf | sha256sum
```

Read the live status the ledger reads:

```sh
curl -s https://api.buildsable.com/v1/status
curl -s https://api.buildsable.com/v1/receipts/pubkey
```

Re-create any diff from two snapshots:

```sh
pdftotext -layout snapshots/A.pdf - > a.txt
pdftotext -layout snapshots/B.pdf - > b.txt
python3 -c "import sys,watch;print(watch.sentences(open('a.txt').read()))" > a.s
python3 -c "import sys,watch;print(watch.sentences(open('b.txt').read()))" > b.s
diff -u a.s b.s
```

## Why the sentence diff

`pdftotext` output changes whenever the PDF is re-rendered, even when no word changed, because line breaks move. The first real change to this document was exactly that: 824 lines of diff, of which almost all was reflow and one paragraph was new. Collapsing whitespace and splitting on sentence boundaries makes the diff show the sentences, not the typesetting.

## Run it locally

```sh
pip install nothing   # standard library only; you need pdftotext (poppler-utils) on PATH
python3 watch.py                      # normal run
python3 watch.py --pdf some.pdf --label 2026-08-29   # import a snapshot you saved earlier
python3 watch.py --no-status          # whitepaper only
```

Built by [ØPTIMUS ONE](https://x.com/0PTIMUS_ONE), a community member who holds SABL. See also [sable.primecircle.cloud](https://sable.primecircle.cloud), a plain-language explainer with an in-browser receipt verifier.
