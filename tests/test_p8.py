"""
tests/test_p8.py
----------------
Verification test suite for Patch P8:
- (a) Dual-signal alerting: content_caution == True on OK messages with >= 2 BEC context flags
      (specifically verifying Michelle Cash cash-m_09 and Marcus Hale msg_11).
- (b) content_escalation remains False on OK messages, and content_caution is False on TRIAGE messages.
- (c) Borderline card criteria: verdict == OK and p < 0.20 and broken_habits.
- (d) Gender-neutral terminology: "baseline norm" used instead of gendered pronouns.
- (e) UI verification: badge-caution, CONTENT RISK ADVISORY, and borderline warning render properly.
"""

import json
import os
import unittest
from streamlit.testing.v1 import AppTest

from src.demo_inbox import build_inbox
from src.ingest import get_all_senders
from src.score import score_message

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_FILE = os.path.join(REPO_ROOT, "app", "app.py")
METRICS_FILE = os.path.join(REPO_ROOT, "artifacts", "metrics.json")


class TestPatchP8(unittest.TestCase):

    def setUp(self):
        self.assertTrue(os.path.exists(METRICS_FILE), "metrics.json must exist")

    def test_cash_m09_dual_signal(self):
        """
        Michelle Cash generic Apple gift card forgery (cash-m_09):
        Stylometry yields OK due to null variance, but contains BEC flags ('apple', 'gift card', 'urgent').
        Must receive verdict='OK', content_caution=True, and qualify for borderline warning.
        """
        inbox = build_inbox("cash-m")
        target_msg = next((m for m in inbox if m["id"] == "cash-m_09"), None)
        self.assertIsNotNone(target_msg, "cash-m_09 must exist in cash-m demo inbox")

        res = score_message(target_msg["body"], "cash-m", alpha=0.05)
        self.assertEqual(res["verdict"], "OK")
        self.assertTrue(res["content_caution"], "cash-m_09 must trigger content_caution=True")
        self.assertFalse(res["content_escalation"], "content_escalation must remain False for OK messages")
        self.assertGreaterEqual(len(res["context_flags"]), 2)
        self.assertLess(res["p"], 0.20, "p-value should be borderline (< 0.20)")
        self.assertGreater(len(res["broken_habits"]), 0, "broken_habits must be detected")

    def test_msg11_marcus_hale_dual_signal(self):
        """
        Marcus Hale styled wire transfer forgery (msg_11):
        Stylometry yields OK (S=0.4124, p=0.5929), but contains wire & confidential context flags.
        Must receive verdict='OK', content_caution=True.
        """
        inbox = build_inbox("presto-k")
        target_msg = next((m for m in inbox if m["id"] == "msg_11"), None)
        self.assertIsNotNone(target_msg, "msg_11 must exist in Marcus Hale demo inbox")

        res = score_message(target_msg["body"], "presto-k", alpha=0.05)
        self.assertEqual(res["verdict"], "OK")
        self.assertTrue(res["content_caution"], "msg_11 must trigger content_caution=True")
        self.assertFalse(res["content_escalation"])
        self.assertIn("wire", res["context_flags"])

    def test_benign_email_no_caution(self):
        """Genuine email with no BEC flags must have content_caution=False."""
        inbox = build_inbox("presto-k")
        target_msg = next((m for m in inbox if m["id"] == "msg_01"), None)
        self.assertIsNotNone(target_msg)

        res = score_message(target_msg["body"], "presto-k", alpha=0.05)
        self.assertEqual(res["verdict"], "OK")
        self.assertFalse(res["content_caution"], "Benign email must not have content_caution")
        self.assertFalse(res["content_escalation"])

    def test_short_bec_triage_escalation_not_caution(self):
        """
        Short email with context flags gets TRIAGE:
        content_escalation=True, content_caution=False (caution is strictly for OK messages).
        """
        short_bec = "Please wire transfer the balance today."
        res = score_message(short_bec, "presto-k", alpha=0.05)
        self.assertEqual(res["verdict"], "TRIAGE")
        self.assertTrue(res["content_escalation"])
        self.assertFalse(res["content_caution"])

    def test_gender_neutrality_direction(self):
        """Check that direction strings and broken habits do not contain 'his norm' or 'her norm'."""
        inbox = build_inbox("presto-k")
        for m in inbox:
            res = score_message(m["body"], "presto-k", alpha=0.05)
            direction = res.get("direction", "")
            self.assertNotIn("his norm", direction.lower())
            self.assertNotIn("her norm", direction.lower())
            for bh in res.get("broken_habits", []):
                self.assertNotIn("his norm", bh.lower())
                self.assertNotIn("her norm", bh.lower())

    def test_app_ui_caution_and_borderline_rendering(self):
        """
        App UI rendering test:
        Selecting Michelle Cash and auditing cash-m_09 should render:
        - badge-caution in table
        - CAUTION in verdict banner
        - CONTENT RISK ADVISORY banner
        - Borderline Stylometric Drift warning
        """
        at = AppTest.from_file(APP_FILE)
        at.run(timeout=15)
        self.assertEqual(len(at.error), 0)

        # Switch sender dropdown to Michelle Cash
        profile_sb = None
        for sb in at.sidebar.selectbox:
            if "Active Executive Profile" in sb.label:
                profile_sb = sb
                break
        self.assertIsNotNone(profile_sb)

        cash_opt_idx = next(
            (i for i, opt in enumerate(profile_sb.options) if "Michelle Cash" in opt),
            None,
        )
        self.assertIsNotNone(cash_opt_idx)
        profile_sb.select_index(cash_opt_idx).run(timeout=15)

        # Select cash-m_09 in audit selectbox
        audit_sb = None
        for sb in at.selectbox:
            if "Select email to audit" in sb.label:
                audit_sb = sb
                break
        self.assertIsNotNone(audit_sb)

        m09_idx = next(
            (i for i, opt in enumerate(audit_sb.options) if "cash-m_09" in opt),
            None,
        )
        self.assertIsNotNone(m09_idx)
        # Ensure the audit option contains [CAUTION]
        self.assertIn("[CAUTION]", audit_sb.options[m09_idx])

        audit_sb.select_index(m09_idx).run(timeout=15)
        self.assertEqual(len(at.error), 0)

        # Verify markdown elements contain badge-caution, CONTENT RISK ADVISORY, and Borderline
        all_md = " ".join(m.value for m in at.markdown)
        self.assertIn("badge-caution", all_md)
        self.assertIn("CONTENT RISK ADVISORY", all_md)
        self.assertIn("VERDICT: OK", all_md)
        self.assertIn("CAUTION (High-Risk Content)", all_md)

        # Verify warnings contain the borderline diagnostic card
        borderline_found = any("Borderline Stylometric Drift" in w.value for w in at.warning)
        self.assertTrue(borderline_found, "Borderline Stylometric Drift warning card must be present")


if __name__ == "__main__":
    unittest.main()
