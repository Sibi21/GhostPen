"""
tests/test_demo_inbox.py
------------------------
Unit tests for per-sender demonstration inbox builder (PATCH P1).
Tests:
- test_inbox_canonical: build_inbox(alias) == pinned ordered ID list
- test_inbox_determinism: two builds identical for every sender
- test_inbox_composition: high-volume -> 8 genuine + 2 generic + 2 styled + 1 short (+/- short genuine);
                          low-volume -> genuine-only flag true
"""

import json
import os
import unittest

from src.demo_inbox import PINNED_DEMO_INBOX, build_inbox
from src.ingest import get_all_senders


class TestDemoInbox(unittest.TestCase):

    def test_inbox_canonical(self):
        """Canonical aliased demo sender returns the pinned ordered ID list identically."""
        with open(PINNED_DEMO_INBOX, "r", encoding="utf-8") as f:
            pinned = json.load(f)

        for alias in ["Marcus Hale", "Marcus Hale (CFO)", "presto-k"]:
            inbox = build_inbox(alias)
            self.assertEqual(len(inbox), 14, f"Expected 14 messages for alias {alias}")
            self.assertEqual(
                [m["id"] for m in inbox],
                [m["id"] for m in pinned],
                f"Ordered IDs do not match pinned list for {alias}",
            )
            self.assertEqual(inbox, pinned, f"Message content does not match pinned list for {alias}")

    def test_inbox_determinism(self):
        """Two builds are byte-and-structure identical for every sender."""
        senders = get_all_senders()
        for s in senders:
            sid = s["sender_id"]
            build1 = build_inbox(sid)
            build2 = build_inbox(sid)
            self.assertEqual(
                build1,
                build2,
                f"Deterministic rebuild failed for sender {sid}",
            )
            self.assertEqual(
                [m["id"] for m in build1],
                [m["id"] for m in build2],
                f"IDs not identical on rebuild for sender {sid}",
            )

    def test_inbox_composition(self):
        """
        Composition contracts:
        - High-volume: 8 genuine + 2 generic + 2 styled + 1 short (+/- optional short genuine)
        - Low-volume: genuine-only flag True, all categories are genuine holdouts
        """
        senders = get_all_senders()
        for s in senders:
            sid = s["sender_id"]
            vclass = s["volume_class"]
            inbox = build_inbox(sid)

            if vclass == "high":
                self.assertFalse(inbox.genuine_only, f"{sid} should not be genuine-only")
                cats = [m["category"] for m in inbox]
                n_gen = sum(1 for c in cats if c == "genuine_holdout")
                n_generic = sum(1 for c in cats if c == "forged_generic")
                n_styled = sum(1 for c in cats if c == "forged_styled")
                n_short_forged = sum(1 for c in cats if c == "short_forged_evasion")
                n_short_gen = sum(1 for c in cats if c == "short_genuine")

                self.assertEqual(n_gen, 8, f"{sid} should have 8 genuine holdouts, got {n_gen}")
                self.assertEqual(n_generic, 2, f"{sid} should have 2 generic forgeries, got {n_generic}")
                self.assertEqual(n_styled, 2, f"{sid} should have 2 styled forgeries, got {n_styled}")
                self.assertEqual(n_short_forged, 1, f"{sid} should have 1 short forged evasion, got {n_short_forged}")
                self.assertIn(n_short_gen, [0, 1], f"{sid} short genuine should be 0 or 1, got {n_short_gen}")

                expected_len = 14 if inbox.has_short_genuine else 13
                self.assertEqual(len(inbox), expected_len, f"Unexpected inbox length for {sid}")
            else:
                self.assertTrue(inbox.genuine_only, f"{sid} must have genuine_only=True")
                cats = [m["category"] for m in inbox]
                self.assertTrue(
                    all(c in ["genuine_holdout", "short_genuine"] for c in cats),
                    f"{sid} low volume inbox must contain only genuine messages, got {cats}",
                )
                self.assertLessEqual(len(inbox), 8, f"{sid} low volume inbox should have <= 8 messages")


if __name__ == "__main__":
    unittest.main()
