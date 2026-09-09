"""
tests/test_p10.py
-----------------
Verification test suite for Patch P10: Context-aware explanation wording (UI strings ONLY).
- (a) For an OK demo message, the string "attacker" appears nowhere in the rendered detail view,
      and the panel title is "Habits matching the baseline" with prefix "matched:".
- (b) For an ALERT demo message, "What the disguise got right" and "attacker matched:" render,
      and "attacker" appears.
- (c) For plain TRIAGE mail (e.g. heard-m_01), "attacker" appears nowhere, and the panel title
      is "Habits within normal range (low confidence - N words)" with prefix "within range:".
- (d) For TRIAGE with content escalation, the disguise/attacker framing is preserved.
"""

import os
import unittest
from streamlit.testing.v1 import AppTest

from src.attribution import extract_matched_habits

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_FILE = os.path.join(REPO_ROOT, "app", "app.py")


class TestPatchP10(unittest.TestCase):

    def test_extract_matched_habits_prefixes(self):
        """extract_matched_habits supports default and custom prefixes."""
        text = "Please review the attached invoice. Thanks."
        # Default
        matched_default = extract_matched_habits(text, "presto-k")
        self.assertTrue(len(matched_default) > 0)
        self.assertTrue(all(m["title"].startswith("attacker matched:") for m in matched_default))

        # Custom 'matched:'
        matched_ok = extract_matched_habits(text, "presto-k", prefix="matched:")
        self.assertTrue(len(matched_ok) > 0)
        self.assertTrue(all(m["title"].startswith("matched:") for m in matched_ok))

        # Custom 'within range:'
        matched_range = extract_matched_habits(text, "presto-k", prefix="within range:")
        self.assertTrue(len(matched_range) > 0)
        self.assertTrue(all(m["title"].startswith("within range:") for m in matched_range))

    def test_ok_demo_message_no_attacker_wording(self):
        """For an OK demo message, 'attacker' appears nowhere in the rendered detail view."""
        at = AppTest.from_file(APP_FILE)
        at.run(timeout=15)
        self.assertEqual(len(at.error), 0)

        # Audit inspection detail for default msg_01 (OK)
        all_md = " ".join(m.value for m in at.markdown)
        self.assertIn("Habits matching the baseline", all_md)
        self.assertIn("matched:", all_md)
        self.assertNotIn("attacker", all_md.lower(), "String 'attacker' must not appear anywhere in OK detail view")
        self.assertNotIn("disguise", all_md.lower(), "String 'disguise' must not appear in OK detail view")

    def test_alert_demo_message_has_attacker_wording(self):
        """For an ALERT demo message, 'attacker' and 'What the disguise got right' appear."""
        at = AppTest.from_file(APP_FILE)
        at.run(timeout=15)
        self.assertEqual(len(at.error), 0)

        # Select msg_09 (ALERT)
        audit_sb = next(sb for sb in at.selectbox if "Select email to audit" in sb.label)
        msg09_idx = next(i for i, opt in enumerate(audit_sb.options) if "msg_09" in opt)
        audit_sb.select_index(msg09_idx).run(timeout=15)

        all_md = " ".join(m.value for m in at.markdown)
        self.assertIn("What the disguise got right", all_md)
        self.assertIn("attacker matched:", all_md)
        self.assertIn("attacker", all_md.lower())

    def test_heard_m01_triage_view_no_attacker_wording(self):
        """heard-m_01 (plain TRIAGE) must have no 'attacker' wording and show 'Habits within normal range'."""
        at = AppTest.from_file(APP_FILE)
        at.run(timeout=15)
        self.assertEqual(len(at.error), 0)

        # Select Marie Heard
        profile_sb = next(sb for sb in at.sidebar.selectbox if "Active Executive Profile" in sb.label)
        heard_idx = next(i for i, opt in enumerate(profile_sb.options) if "Marie Heard" in opt)
        profile_sb.select_index(heard_idx).run(timeout=15)

        # Select heard-m_01
        audit_sb = next(sb for sb in at.selectbox if "Select email to audit" in sb.label)
        h01_idx = next(i for i, opt in enumerate(audit_sb.options) if "heard-m_01" in opt)
        audit_sb.select_index(h01_idx).run(timeout=15)

        all_md = " ".join(m.value for m in at.markdown)
        self.assertIn("Habits within normal range (low confidence - 19 words)", all_md)
        self.assertIn("within range:", all_md)
        self.assertNotIn("attacker", all_md.lower(), "String 'attacker' must not appear anywhere in plain TRIAGE detail view")
        self.assertNotIn("disguise", all_md.lower(), "String 'disguise' must not appear in plain TRIAGE detail view")

    def test_triage_with_escalation_has_attacker_wording(self):
        """TRIAGE with content_escalation (e.g. msg_14 short wire evasion) retains disguise framing."""
        at = AppTest.from_file(APP_FILE)
        at.run(timeout=15)
        self.assertEqual(len(at.error), 0)

        audit_sb = next(sb for sb in at.selectbox if "Select email to audit" in sb.label)
        msg14_idx = next(i for i, opt in enumerate(audit_sb.options) if "msg_14" in opt)
        audit_sb.select_index(msg14_idx).run(timeout=15)

        all_md = " ".join(m.value for m in at.markdown)
        self.assertIn("What the disguise got right", all_md)
        self.assertIn("attacker matched:", all_md)
        self.assertIn("attacker", all_md.lower())


if __name__ == "__main__":
    unittest.main()
