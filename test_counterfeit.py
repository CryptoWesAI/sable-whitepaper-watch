"""Pure-function tests for the counterfeit watch. Run with: python -m unittest test_counterfeit"""
import datetime
import unittest

import watch


class LooksLikeSabl(unittest.TestCase):
    def test_plain_forms(self):
        for name, sym in (("Sable", "SABLE"), ("Sable Network", "SABL"), ("x", "$SABL"), ("Wrapped SABL", "wSABL"),
                          ("sabl", ""), ("", "Sabl"), ("S.A.B.L", ""), ("SABL on Robinhood", "SBL")):
            self.assertTrue(watch.looks_like_sabl(name, sym), (name, sym))

    def test_look_alike_letters(self):
        self.assertTrue(watch.looks_like_sabl("SАBL", ""))       # Cyrillic capital A
        self.assertTrue(watch.looks_like_sabl("", "ＳＡＢＬ"))     # full-width letters
        self.assertTrue(watch.looks_like_sabl("sаblе", ""))      # Cyrillic a and e

    def test_unrelated_names(self):
        for name, sym in (("Global Dollar", "USDG"), ("Stable", "STABLE"), ("Sablier", "SABLIER"), ("Wrapped Ether", "WETH"),
                          ("Rapidly Reusable Reusable Rocket", "RRRR"), ("Usable Token", "USE"), ("Disable", "DIS"),
                          ("", ""), (None, None)):
            self.assertFalse(watch.looks_like_sabl(name, sym), (name, sym))

    def test_wrapper_prefixes(self):
        for name, sym in (("Wrapped SABL", "wSABL"), ("Staked Sable", "stSABL"), ("", "xSABL"), ("Sablecoin", "SABLC")):
            self.assertTrue(watch.looks_like_sabl(name, sym), (name, sym))


class CounterfeitHits(unittest.TestCase):
    def pair(self, chain, addr, name, sym, liq=None, pair="0xp", created=None):
        p = {"chainId": chain, "pairAddress": pair, "dexId": "uniswap", "url": "https://dexscreener.com/x",
             "baseToken": {"address": addr, "name": name, "symbol": sym},
             "quoteToken": {"address": "0xW", "name": "Wrapped Ether", "symbol": "WETH"},
             "liquidity": {"usd": liq}, "fdv": liq, "volume": {"h24": 9.02}}
        if created:
            p["pairCreatedAt"] = int(created.timestamp() * 1000)
        return p

    def test_only_robinhood_pairs_count_as_hits(self):
        opened = datetime.datetime(2026, 7, 26, 10, 31, 10, tzinfo=datetime.timezone.utc)
        pairs = [self.pair("robinhood", "0xA", "Sable", "SABLE", 3381.03, created=opened),
                 self.pair("bsc", "0xB", "Sable", "SABLE", 67164.59),
                 self.pair("robinhood", "0xU", "Global Dollar", "USDG", 1e6)]
        hits, other = watch.counterfeit_hits(pairs)
        self.assertEqual([h["address"] for h in hits], ["0xA"])
        self.assertEqual(hits[0]["pair_created"], "2026-07-26T10:31:10Z")
        self.assertEqual(hits[0]["liquidity_usd"], 3381.03)
        self.assertEqual(other, 1)

    def test_deepest_pool_wins_per_token(self):
        hits, _ = watch.counterfeit_hits([self.pair("robinhood", "0xA", "Sable", "SABLE", 10, pair="0x1"),
                                          self.pair("robinhood", "0xa", "Sable", "SABLE", 500, pair="0x2")])
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["pair"], "0x2")

    def test_quote_side_counts_too(self):
        p = self.pair("robinhood", "0xU", "Global Dollar", "USDG", 100)
        p["quoteToken"] = {"address": "0xS", "name": "Sable", "symbol": "SABLE"}
        hits, _ = watch.counterfeit_hits([p])
        self.assertEqual([h["address"] for h in hits], ["0xS"])

    def test_garbage_is_skipped(self):
        hits, other = watch.counterfeit_hits([None, "x", {}, {"chainId": "robinhood", "baseToken": None}])
        self.assertEqual(hits, [])
        self.assertEqual(other, 0)


if __name__ == "__main__":
    unittest.main()
