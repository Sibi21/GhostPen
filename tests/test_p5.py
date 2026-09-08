"""
tests/test_p5.py
----------------
Verification test suite for Patch P5 (mailbox table column-menu statistics removal):
- test_no_column_stats:
  * Verifies that the demo page renders headlessly without any DataFrame grid column menu
    or statistics panel enablement (0 st.dataframe components mounted).
  * Verifies that the mailbox table renders as a clean plain display table.
  * Verifies selection sync: row highlighting tracks the audit selector dropdown.
  * Verifies verdict tags (OK, ALERT, TRIAGE) and jury-mode Ground Truth Tier tags.
"""

import os
import unittest
from streamlit.testing.v1 import AppTest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_FILE = os.path.join(REPO_ROOT, "app", "app.py")


class TestPatchP5MailboxTable(unittest.TestCase):

    def test_no_column_stats(self):
        """
        P5: The mailbox table exposes no column-header menu or statistics panel.
        Replaced with a plain display table that maintains selection sync, row
        highlighting, and verdict/tier tags.
        """
        at = AppTest.from_file(APP_FILE)
        at.run(timeout=10)

        # 1. No runtime errors
        self.assertEqual(len(at.error), 0, f"AppTest produced errors: {[e.value for e in at.error]}")

        # 2. Assert no Glide Data Grid with column menu/statistics is mounted
        self.assertEqual(
            len(at.dataframe),
            0,
            "Mailbox table must not use st.dataframe (which exposes column menu statistics)",
        )

        # 3. Find the rendered mailbox table markdown
        table_markdowns = [
            m.value for m in at.markdown
            if '<table class="mailbox-table">' in m.value
        ]
        self.assertEqual(len(table_markdowns), 1, "Exactly one mailbox table should be rendered")
        table_html = table_markdowns[0]

        # 4. Assert column headers exist without menu buttons
        self.assertIn("<th>ID</th>", table_html)
        self.assertIn("<th>Date</th>", table_html)
        self.assertIn("<th>Subject</th>", table_html)
        self.assertIn("<th>Verdict</th>", table_html)
        self.assertIn("<th>Score S</th>", table_html)
        self.assertIn("<th>Escalated</th>", table_html)

        # 5. Assert default selection (msg_01) is highlighted
        self.assertIn("selected-row", table_html)
        self.assertIn("msg_01", table_html)
        self.assertIn("[SELECTED]", table_html)

        # 6. Assert verdict badges are rendered
        self.assertIn("badge-ok", table_html)
        self.assertIn("badge-alert", table_html)
        self.assertIn("badge-triage", table_html)

        # 7. Test selection sync: change audit selectbox to index 8 (msg_09, forged_generic)
        audit_select = None
        for sb in at.selectbox:
            if "audit_select" in sb.key:
                audit_select = sb
                break
        self.assertIsNotNone(audit_select, "Audit selectbox must exist")

        audit_select.select_index(8).run(timeout=10)
        self.assertEqual(len(at.error), 0)

        # Re-check table markdown
        table_markdowns_after = [
            m.value for m in at.markdown
            if '<table class="mailbox-table">' in m.value
        ]
        self.assertEqual(len(table_markdowns_after), 1)
        table_html_after = table_markdowns_after[0]

        # Now msg_09 should be selected and highlighted
        self.assertIn('data-idx="8"', table_html_after)
        self.assertIn("<b>msg_09</b>", table_html_after)

        # 8. Test Ground Truth Reveal mode (Jury Mode)
        truth_cb = None
        for cb in at.checkbox:
            if "Reveal ground truth" in cb.label or (cb.key and "reveal_truth" in cb.key):
                truth_cb = cb
                break
        self.assertIsNotNone(truth_cb, "Ground truth reveal checkbox must exist")

        truth_cb.check().run(timeout=10)
        self.assertEqual(len(at.error), 0)

        table_markdowns_jury = [
            m.value for m in at.markdown
            if '<table class="mailbox-table">' in m.value
        ]
        self.assertEqual(len(table_markdowns_jury), 1)
        table_html_jury = table_markdowns_jury[0]
        self.assertIn("<th>Ground Truth Tier</th>", table_html_jury)
        self.assertIn("badge-tier", table_html_jury)
        self.assertIn("forged_generic", table_html_jury)


if __name__ == "__main__":
    unittest.main()
