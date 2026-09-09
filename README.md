# Sable whitepaper watch

A public, independent record of what the [Sable Network](https://www.buildsable.com) whitepaper says, when it changed, and what changed. Plus an hourly line from Sable's public status endpoints, so a long fail-closed streak or a change of the receipt signer becomes a matter of record rather than memory. Since 8 September 2026 the same hourly line reads the SABL supply on Solana, so the first burn is on record the hour it happens.

Sable's own whitepaper says: *"Infrastructure whitepapers routinely describe a planned system in the present tense. We think that is the single most corrosive habit in this category."* It also says where its previous version was wrong. This repository exists because on 2 September 2026 the PDF changed (section 06 and section 10, on the token) without the cover version changing, and nobody would have known unless they happened to compare file sizes. A document that everything else is judged against deserves a witness.

**Not affiliated with Sable Network.** Reads only public URLs. Corrections welcome as issues or pull requests.

## What is in here

| Path | What |
|---|---|
| [`CHANGELOG.md`](CHANGELOG.md) | Newest first. One entry per change of the PDF: cover version, size, hash, snapshot, diff. Also one entry per fall of the SABL supply, see below. |
| [`whitepaper.txt`](whitepaper.txt) | Current text, extracted with `pdftotext -layout`. Faithful, including line breaks. |
| [`whitepaper.sentences.txt`](whitepaper.sentences.txt) | Current text, one sentence per line. This is what gets diffed, so a re-rendered PDF with different line wrapping does not count as a change. |
| `diffs/` | Unified diff of the sentences for each change. |
| `snapshots/` | The PDF as served, for each change. Evidence, not summary. |
| [`status/log.jsonl`](status/log.jsonl) | One line per hour: gateway status, uptime, confidential backend verified or failing closed and why, node list, receipt signer address, model count, the `sable-fast` list price, the token's market figures, and the SABL supply as Solana reports it (`sabl_supply`: raw amount, decimals, uiAmount, slot; `null` plus `sabl_supply_error` when the node did not answer). |
| [`status/supply.jsonl`](status/supply.jsonl) | The supply watch. A line only when the SABL supply changes: time, slot, previous amount, new amount, delta. The first line is the baseline. |
| [`status/claims.jsonl`](status/claims.jsonl) | The route watch. A line only when an announced surface changes state: time, claim id, previous state, new state, the HTTP answer per documented route and the control route. The first line per claim is the baseline. What is asked lives in [`claims.json`](claims.json). |
| [`watch.py`](watch.py) | The whole thing. Standard library only. |

## How it runs

A GitHub Action runs [`watch.py`](watch.py) every hour. It downloads the PDF, hashes it, and only does work when the hash changes. The status ledger appends one line per run regardless. Commits are made by the Action; the history of this repository is the record.

There is no alert channel. Every run also writes [`record.json`](record.json), a machine-readable summary of the changelog and the last ledger line, and [sable.primecircle.cloud](https://sable.primecircle.cloud#check) reads that file at page load. A change to the whitepaper is therefore visible on the site within the hour, with no deploy and no bot.

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

## The route watch

Sable announces things as live. Some of those can be checked from outside without a key: when the docs name the routes, the public gateway either has them or it does not. On this gateway a routed path answers `401` before it looks anything up (`GET /v1/mandates` without a key says "missing Authorization header"), and an unrouted one answers `404`. So a `404` on a documented route is a missing route, not a missing permission.

[`claims.json`](claims.json) lists each announcement with its documented routes and one control route. Every hourly run asks them without a key and writes the answers into the hourly line under `claims`. The state per claim is `present` when any documented route answers something other than 404, `absent` when every HTTP answer is 404, and `unreachable` when no route gave an HTTP answer. [`status/claims.jsonl`](status/claims.jsonl) gets a line only when the state changes (the first line per claim is the baseline), a route that answers for the first time gets a [`CHANGELOG.md`](CHANGELOG.md) entry, and [`record.json`](record.json) carries the summary under `claims`, which the Observatory shows in its Log. An answer from outside says the route exists on the public deployment; whether the feature works needs a key.

First entry, 8 September 2026: the MCP Gateway, announced live on X that day, with a docs page that names `POST /v1/mcp-servers` and `/v1/mcp/servers/:id`. On that day every documented route answered 404 from outside.

Verify it yourself, no key needed:

```sh
curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "content-type: application/json" -d "{}" https://api.buildsable.com/v1/mcp-servers
curl -s -o /dev/null -w "%{http_code}\n" https://api.buildsable.com/v1/mandates
```

## The supply watch

Sable's whitepaper, section 06, in its own words: *"SABL gains a single utility: it can be used to pay for Sable compute and Sable Pro subscriptions, and paying in SABL burns it and earns a discount. This rail is rolling out, not yet live on the deployment."* The same section names the mint, `DaPayqzdCXcrmvgz9Wx7MySipXxcSofGPtkMgVdqpump`, and says its mint and freeze authority are revoked, which the mint account on Solana confirms. A supply that cannot rise can only fall, and it falls only when someone burns. So the first fall of the mint supply is the moment SABL payment is live for real, whoever announces what.

Every hourly run asks a public Solana node for the supply (`getTokenSupply` on the mint, default node `https://api.mainnet-beta.solana.com`, override with the `SOLANA_RPC` environment variable) and writes the raw amount, decimals, `uiAmount` and the slot into the hourly line. When the raw amount differs from the last line of [`status/supply.jsonl`](status/supply.jsonl), a line is added there with the previous amount, the new amount and the delta. When it fell, [`CHANGELOG.md`](CHANGELOG.md) gets an entry saying by how much, from what to what, and when. [`record.json`](record.json) carries the latest read, the baseline, the change since the baseline and the last change under `sabl_supply`, and the Observatory shows it on the Token topic. The chain says how much was burned and when; it does not say who burned it or why. A node that does not answer is recorded as such and the run carries on.

Verify it yourself, same call, no key needed:

```sh
curl -s https://api.mainnet-beta.solana.com -X POST -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"getTokenSupply","params":["DaPayqzdCXcrmvgz9Wx7MySipXxcSofGPtkMgVdqpump"]}'
```

The answer's `value.amount` is the supply in base units (six decimals), `value.uiAmount` in whole SABL, and `context.slot` is the slot it was read at. Compare `amount` with the last line of `status/supply.jsonl`.

## Why the sentence diff

`pdftotext` output changes whenever the PDF is re-rendered, even when no word changed, because line breaks move. The first real change to this document was exactly that: 824 lines of diff, of which almost all was reflow and one paragraph was new. Collapsing whitespace and splitting on sentence boundaries makes the diff show the sentences, not the typesetting.

## Run it locally

```sh
pip install nothing   # standard library only; you need pdftotext (poppler-utils) on PATH
python3 watch.py                      # normal run
python3 watch.py --pdf some.pdf --label 2026-08-29   # import a snapshot you saved earlier
python3 watch.py --no-status          # whitepaper only, no ledger and no supply watch
SOLANA_RPC=https://your.node python3 watch.py   # read the supply from another Solana node
```

Built by [ØPTIMUS ONE](https://x.com/0PTIMUS_ONE), a community member who holds SABL. See also the [Sable Observatory](https://sable.primecircle.cloud), an independent page that explains Sable, lets you try and verify it, and shows this record live.

## The runner on the VPS

Since 9 September 2026 the same `watch.py` also runs on the Observatory's server, at minute 05 of every hour, in a container that pulls this repository over https, commits with the same messages the Action uses, and pushes over ssh with a deploy key that was generated on that server and added here with write access. Commits from it say "(vps)". The GitHub schedule stays as a fallback; an hour with both gives the ledger two lines, which the reliability record and the chart simply show. The reason: GitHub ran the hourly schedule about seven times a day in the first week. Source and operating notes: `sites/sable-peers/watcher-vps/` in the Observatory's repository.
