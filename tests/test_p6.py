"""
tests/test_p6.py
----------------
Verification test suite for Patch P6:
- P6.1: Attribution panel visibility rules:
  * OK verdict: ranking panel replaced with "Verified as {claimed sender}. Attribution ranking is shown only for rejected messages."
  * Plain TRIAGE (no escalation): "Stylometry abstained - no attribution suggested."
  * ALERT verdict: "Closest enrolled authors" ranking panel IS rendered.
  * Escalated TRIAGE: "Closest enrolled authors" ranking panel IS rendered.
- P6.2: Honest framing of the ranking text in tooltip/caption.
- P6.3: Verification across demo messages and senders.
- P6.4: Mailbox sorting without column menu or statistics, with selection synchronization.
"""

import json
import os
import unittest
from streamlit.testing.v1 import AppTest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_FILE = os.path.join(REPO_ROOT, "app", "app.py")
METRICS_FILE = os.path.join(REPO_ROOT, "artifacts", "metrics.json")


class TestPatchP6(unittest.TestCase):

    def setUp(self):
        self.assertTrue(os.path.exists(METRICS_FILE), "metrics.json must exist")
        with open(METRICS_FILE, "r", encoding="utf-8") as f:
            self.metrics = json.load(f)

    def test_attribution_visibility_and_framing(self):
        """
        P6.1 & P6.2: Test attribution panel visibility and exact framing across
        OK, plain TRIAGE, and ALERT messages.
        """
        at = AppTest.from_file(APP_FILE)
        at.run(timeout=10)
        self.assertEqual(len(at.error), 0, f"AppTest produced errors: {[e.value for e in at.error]}")

        # 1. Default message (msg_01) has verdict OK
        # Ranking panel must NOT be rendered; replacement line MUST be rendered
        ranking_headers = [
            m.value for m in at.markdown
            if "Closest enrolled authors" in m.value
        ]
        self.assertEqual(
            len(ranking_headers),
            0,
            "Attribution ranking header must NOT be rendered on OK verdict",
        )

        ok_replacement_lines = [
            info.value for info in at.info
            if "Verified as Marcus Hale. Attribution ranking is shown only for rejected messages." in info.value
        ]
        self.assertEqual(
            len(ok_replacement_lines),
            1,
            "Replacement line for OK message must be rendered exactly",
        )

        # 2. Select plain TRIAGE message (msg_07 in Marcus Hale inbox: short genuine holdout, no flags)
        audit_select = None
        for sb in at.selectbox:
            if "audit_select" in sb.key:
                audit_select = sb
                break
        self.assertIsNotNone(audit_select)

        # Find plain TRIAGE index (msg_13 short genuine is index 12)
        audit_select.select_index(12).run(timeout=10)
        self.assertEqual(len(at.error), 0)

        triage_lines = [
            info.value for info in at.info
            if "Stylometry abstained - no attribution suggested." in info.value
        ]
        self.assertEqual(
            len(triage_lines),
            1,
            "Plain TRIAGE message must show 'Stylometry abstained - no attribution suggested.'",
        )

        # 3. Select ALERT message (msg_09 at index 8: generic BEC wire transfer)
        audit_select.select_index(8).run(timeout=10)
        self.assertEqual(len(at.error), 0)

        # On ALERT, ranking panel MUST be rendered
        ranking_headers_alert = [
            m.value for m in at.markdown
            if "Closest enrolled authors" in m.value
        ]
        self.assertEqual(
            len(ranking_headers_alert),
            1,
            "Attribution ranking header MUST be rendered on ALERT verdict",
        )

        # Honest framing sentence must be present in caption/tooltip
        expected_framing = (
            "Cross-sender ranking is a forensic suggestion, not identification: a "
            "genuine message's p against its true author is uniform by construction, "
            "and boilerplate text (out-of-office, forwards) carries little personal "
            "signal, so ranks can shuffle on such mail. Measured top-1 accuracy on the "
            f"relabel tier: {self.metrics['attribution_top1_accuracy_relabel']}."
        )
        framing_captions = [
            c.value for c in at.caption
            if expected_framing in c.value
        ]
        self.assertEqual(
            len(framing_captions),
            1,
            "Honest framing caption must be rendered on ALERT message",
        )

    def test_lynn_blair_blair_03_ok_detail(self):
        """
        P6.1 & P6.3: Lynn Blair's blair-l_03 message (verdict OK) shows the replacement line
        and suppresses the ranking panel.
        """
        at = AppTest.from_file(APP_FILE)
        at.run(timeout=10)

        # Switch sender to Lynn Blair
        sender_select = at.sidebar.selectbox[0]
        blair_idx = None
        for i, opt in enumerate(sender_select.options):
            if "Lynn Blair" in opt:
                blair_idx = i
                break
        self.assertIsNotNone(blair_idx, "Lynn Blair profile must exist in sidebar")

        sender_select.select_index(blair_idx).run(timeout=10)
        self.assertEqual(len(at.error), 0)

        # Select blair-l_03 (index 2)
        audit_select = None
        for sb in at.selectbox:
            if "audit_select" in sb.key:
                audit_select = sb
                break
        self.assertIsNotNone(audit_select)
        audit_select.select_index(2).run(timeout=10)
        self.assertEqual(len(at.error), 0)

        # Verify ranking panel is absent
        ranking_headers = [
            m.value for m in at.markdown
            if "Closest enrolled authors" in m.value
        ]
        self.assertEqual(len(ranking_headers), 0)

        # Verify replacement line matches Lynn Blair exactly
        expected_line = "Verified as Lynn Blair. Attribution ranking is shown only for rejected messages."
        replacement_lines = [
            info.value for info in at.info
            if expected_line in info.value
        ]
        self.assertEqual(len(replacement_lines), 1, f"Expected '{expected_line}' in info messages")

    def test_mailbox_sorting_and_selection_sync(self):
        """
        P6.4: Sort control allows sorting by Date (ascending/descending) and Default order.
        Statistics panel and column menu remain absent.
        Row selection sync works after sort.
        """
        at = AppTest.from_file(APP_FILE)
        at.run(timeout=10)
        self.assertEqual(len(at.error), 0)

        # 1. Assert no st.dataframe exists (no Glide Data Grid column menu / statistics)
        self.assertEqual(len(at.dataframe), 0)

        # 2. Find sort selectbox
        sort_select = None
        for sb in at.selectbox:
            if "sort_order" in sb.key:
                sort_select = sb
                break
        self.assertIsNotNone(sort_select, "Mailbox sort order selectbox must exist")
        self.assertEqual(sort_select.options, ["Default order", "Date (ascending)", "Date (descending)"])

        # 3. Verify Default order selection highlighting
        table_html = [m.value for m in at.markdown if '<table class="mailbox-table">' in m.value][0]
        self.assertIn('data-idx="0"', table_html)
        self.assertIn("selected-row", table_html)
        self.assertIn("msg_01", table_html)

        # 4. Switch sort order to "Date (descending)"
        sort_select.select("Date (descending)").run(timeout=10)
        self.assertEqual(len(at.error), 0)

        table_desc = [m.value for m in at.markdown if '<table class="mailbox-table">' in m.value][0]
        # In descending order, msg_01 must still have .selected-row because audit_select is still msg_01
        self.assertIn('selected-row', table_desc)
        self.assertIn('data-idx="0"', table_desc)

        # 5. Switch audit selection to index 8 (msg_09) while still in Date (descending) sort
        audit_select = None
        for sb in at.selectbox:
            if "audit_select" in sb.key:
                audit_select = sb
                break
        self.assertIsNotNone(audit_select)
        audit_select.select_index(8).run(timeout=10)
        self.assertEqual(len(at.error), 0)

        table_desc_selected8 = [m.value for m in at.markdown if '<table class="mailbox-table">' in m.value][0]
        # msg_09 (orig idx 8) must now have selected-row
        self.assertIn('selected-row', table_desc_selected8)
        self.assertIn('data-idx="8"', table_desc_selected8)
        self.assertIn('<b>msg_09</b>', table_desc_selected8)


if __name__ == "__main__":
    unittest.main()
