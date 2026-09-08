"""Pure-function tests for the watcher. Run with: python -m unittest test_watch"""
import unittest

import watch


class ClaimState(unittest.TestCase):
    def test_every_answer_404_is_absent(self):
        self.assertEqual(watch.claim_state({"POST /v1/a": 404, "POST /v1/b": 404}), "absent")

    def test_any_other_http_answer_is_present(self):
        for code in (200, 400, 401, 403, 405, 500):
            self.assertEqual(watch.claim_state({"POST /v1/a": 404, "POST /v1/b": code}), "present", code)

    def test_404_next_to_a_network_miss_is_absent(self):
        self.assertEqual(watch.claim_state({"POST /v1/a": 404, "POST /v1/b": "unreachable: URLError"}), "absent")

    def test_no_http_answer_at_all_is_unreachable(self):
        self.assertEqual(watch.claim_state({"POST /v1/a": "unreachable: URLError"}), "unreachable")
        self.assertEqual(watch.claim_state({}), "unreachable")


class ClaimTransition(unittest.TestCase):
    def test_absent_to_present_is_reachable(self):
        self.assertEqual(watch.claim_transition("absent", "present"), "reachable")

    def test_present_to_absent_is_gone(self):
        self.assertEqual(watch.claim_transition("present", "absent"), "gone")

    def test_same_state_is_no_flip(self):
        self.assertIsNone(watch.claim_transition("absent", "absent"))
        self.assertIsNone(watch.claim_transition("present", "present"))

    def test_unreachable_on_either_side_is_no_flip(self):
        self.assertIsNone(watch.claim_transition("unreachable", "present"))
        self.assertIsNone(watch.claim_transition("absent", "unreachable"))
        self.assertIsNone(watch.claim_transition(None, "absent"))


class ConfTransition(unittest.TestCase):
    def test_recovered_and_failed(self):
        prev = {"t": "2026-09-08T10:00:00Z", "conf_verified": False, "conf_failures": 7000}
        row = {"t": "2026-09-08T11:00:00Z", "conf_verified": True, "conf_backends": "1/1"}
        self.assertEqual(watch.conf_transition(prev, row)[0], "recovered")
        self.assertEqual(watch.conf_transition(row, dict(prev, t="2026-09-08T12:00:00Z"))[0], "failed")

    def test_unreachable_is_not_a_flip(self):
        prev = {"t": "2026-09-08T10:00:00Z", "conf_verified": None}
        row = {"t": "2026-09-08T11:00:00Z", "conf_verified": True}
        self.assertIsNone(watch.conf_transition(prev, row))


if __name__ == "__main__":
    unittest.main()
