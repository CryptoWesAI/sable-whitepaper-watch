# Sable whitepaper changelog

Newest first. Every entry is a snapshot of the PDF as served at buildsable.com/sable-whitepaper.pdf, with the extracted text diffed sentence by sentence so that line reflow does not count as a change. Since 8 September 2026 an entry is also written when the SABL supply on Solana falls: the whitepaper says paying in SABL burns it, so a fall of the mint supply is that rail live on-chain.

## 2026-09-12-1005: a token named like SABL appeared on Robinhood Chain

- **SABLE** (Sable) at `0x5d75E9aC6Af38fAB666c3BA31d00d0cA28047777`, flapsh pool `0x4860fbdA01C9F1AB9F63Ec6d62a1BCC641E92099` opened 2026-09-12T09:56:13Z, liquidity about $9,708: https://dexscreener.com/robinhood/0x4860fbda01c9f1ab9f63ec6d62a1bcc641e92099
- Seen at 2026-09-12T10:05:01Z through DexScreener's search for SABL, SABLE, Sable on chain 4663. Sable Network's token exists only on Solana (mint `DaPayqzdCXcrmvgz9Wx7MySipXxcSofGPtkMgVdqpump`); nothing on Robinhood Chain is it. Every change of the list is in [`status/counterfeit.jsonl`](status/counterfeit.jsonl).

## 2026-09-11-1905: SABL supply fell

- Supply fell by **10,517.475429 SABL** (10,517,475,429 base units), from 958,371,458.462027 to 958,360,940.986598.
- Seen at 2026-09-11T19:05:02Z, Solana slot 446,231,922, by `getTokenSupply` on https://api.mainnet-beta.solana.com for mint `DaPayqzdCXcrmvgz9Wx7MySipXxcSofGPtkMgVdqpump`.
- The whitepaper (section 06) says paying in SABL burns it. A fall of the mint supply is a burn; the chain does not say who burned it or why. Every change of the supply is in [`status/supply.jsonl`](status/supply.jsonl).

## 2026-09-11-1005: a token named like SABL appeared on Robinhood Chain

- **SABL** (Sable) at `0xE0A0c37605D5C4B4CDDc99E41B0F67664C155DAA`, uniswap pool `0x39dcd5a585ee016a10345ba4c846ce606a7bb162a89158a405bc26d66e9569f0` opened 2026-09-11T09:13:56Z, liquidity about $42: https://dexscreener.com/robinhood/0x39dcd5a585ee016a10345ba4c846ce606a7bb162a89158a405bc26d66e9569f0
- **SABL** (Sable) at `0x2E76bA826F3DaBE23a8844e3607ac9e912b3226a`, uniswap pool `0x2622e983b68539a1e5229ff77502e025ad474ba7af289014856624ab8c21bde8` opened 2026-09-11T09:20:17Z, liquidity about $19: https://dexscreener.com/robinhood/0x2622e983b68539a1e5229ff77502e025ad474ba7af289014856624ab8c21bde8
- Seen at 2026-09-11T10:05:01Z through DexScreener's search for SABL, SABLE, Sable on chain 4663. Sable Network's token exists only on Solana (mint `DaPayqzdCXcrmvgz9Wx7MySipXxcSofGPtkMgVdqpump`); nothing on Robinhood Chain is it. Every change of the list is in [`status/counterfeit.jsonl`](status/counterfeit.jsonl).

## 2026-09-11-0705: MCP Gateway reachable

- The routes the docs give for **MCP Gateway** answered something other than 404 for the first time: POST /v1/mcp-servers 401, POST /v1/mcp/servers/mcp_probe 401 (control route 401).
- Announced 2026-09-08 (Sable on X, 8 September 2026); docs: https://www.buildsable.com/docs/mcp-gateway. Every hourly answer had been 404 since 2026-09-08T14:52:27Z.
- An answer from outside says the route exists on the public gateway, not that the feature works; that needs a key. Every change of state is in [`status/claims.jsonl`](status/claims.jsonl).

## 2026-09-11-0604: SABL supply fell

- Supply fell by **2,979.416195 SABL** (2,979,416,195 base units), from 958,374,437.878222 to 958,371,458.462027.
- Seen at 2026-09-11T06:04:53Z, Solana slot 446,084,298, by `getTokenSupply` on https://api.mainnet-beta.solana.com for mint `DaPayqzdCXcrmvgz9Wx7MySipXxcSofGPtkMgVdqpump`.
- The whitepaper (section 06) says paying in SABL burns it. A fall of the mint supply is a burn; the chain does not say who burned it or why. Every change of the supply is in [`status/supply.jsonl`](status/supply.jsonl).

## 2026-09-10-1629: SABL supply fell

- Supply fell by **1.040661 SABL** (1,040,661 base units), from 958,374,438.918883 to 958,374,437.878222.
- Seen at 2026-09-10T16:29:52Z, Solana slot 445,929,743, by `getTokenSupply` on https://api.mainnet-beta.solana.com for mint `DaPayqzdCXcrmvgz9Wx7MySipXxcSofGPtkMgVdqpump`.
- The whitepaper (section 06) says paying in SABL burns it. A fall of the mint supply is a burn; the chain does not say who burned it or why. Every change of the supply is in [`status/supply.jsonl`](status/supply.jsonl).

## 2026-09-04

- Cover says: **v2.0, August 2026**
- File: 631,953 bytes, sha256 `72514487a320b46baeef84e58613dbbc9a4a41f8ef1235f23866feeb06f5c951`
- Source: https://www.buildsable.com/sable-whitepaper.pdf, from a copy saved on 2026-09-04 and imported into this record
- Snapshot: [`snapshots/whitepaper-2026-09-04.pdf`](snapshots/whitepaper-2026-09-04.pdf)
- Change vs previous text: **16 sentences added, 7 removed** ([diff](diffs/2026-09-04.diff))

## 2026-08-29

- Cover says: **v2.0, August 2026**
- File: 801,537 bytes, sha256 `eff475945b527b92ff07af29313f70116851e52f8ef5beb2395deea33c046e04`
- Source: https://www.buildsable.com/sable-whitepaper.pdf, from a copy saved on 2026-08-29 and imported into this record
- Snapshot: [`snapshots/whitepaper-2026-08-29.pdf`](snapshots/whitepaper-2026-08-29.pdf)
- First snapshot in this record; nothing to diff against.

