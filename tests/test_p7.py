"""
tests/test_p7.py
----------------
Verification test suite for Patch P7:
- (a) For every sender, the set of names renderable by the attribution panel
      equals the set of names in the dropdown.
- (b) The aliased sender ID renders as "Marcus Hale (CFO)" on ALL surfaces,
      and "Kevin Presto" appears in NO UI string (assert absent).
- (c) Existing tests unchanged and green; metrics.json byte-identical.
"""

import json
import os
import subprocess
import sys
import unittest
from streamlit.testing.v1 import AppTest

from src.attribution import compute_attribution
from src.demo_inbox import build_inbox
from src.ingest import display_name, get_all_senders, resolve_sender_id
from src.score import score_message

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_FILE = os.path.join(REPO_ROOT, "app", "app.py")
METRICS_FILE = os.path.join(REPO_ROOT, "artifacts", "metrics.json")
SENDERS_FILE = os.path.join(REPO_ROOT, "data", "senders.json")


class TestPatchP7(unittest.TestCase):

    def setUp(self):
        self.assertTrue(os.path.exists(METRICS_FILE), "metrics.json must exist")
        self.senders = get_all_senders()

    def test_a_attribution_panel_names_equal_dropdown_names(self):
        """
        Test (a): For every sender, the set of names renderable by the
        attribution panel equals the set of names in the dropdown.
        """
        at = AppTest.from_file(APP_FILE)
        at.run(timeout=10)
        self.assertEqual(len(at.error), 0, f"AppTest produced errors: {[e.value for e in at.error]}")

        # Dropdown options from the sidebar selectbox
        profile_sb = None
        for sb in at.sidebar.selectbox:
            if "Active Executive Profile" in sb.label:
                profile_sb = sb
                break
        self.assertIsNotNone(profile_sb, "Active Executive Profile selectbox must exist")

        # Extract clean names from dropdown options (e.g. "Marcus Hale (CFO) (HIGH)" -> "Marcus Hale (CFO)")
        dropdown_names = {opt.rsplit(" (", 1)[0] for opt in profile_sb.options}

        # Expected: exactly 15 enrolled senders
        self.assertEqual(len(dropdown_names), 15, "Dropdown must contain exactly 15 sender names")

        # For every enrolled sender, the set of candidate names renderable across operating alphas
        # equals the set of names in the dropdown
        test_body = "Please review the attached invoice and confirm payment status. Thanks."
        for s in self.senders:
            sid = s["sender_id"]
            # At operating alpha 0.10, all 15 enrolled senders are calibrated
            att = compute_attribution(test_body, sid, alpha=0.10)
            panel_names = {c["display_name"] for c in att["all_ranked_candidates"]}

            self.assertEqual(
                panel_names,
                dropdown_names,
                f"Attribution panel candidate names do not match dropdown names for sender {sid}",
            )

    def test_b_aliased_sender_renders_as_marcus_hale_cfo_on_all_surfaces(self):
        """
        Test (b): The aliased sender ID renders as 'Marcus Hale (CFO)' on ALL surfaces,
        and 'Kevin Presto' appears in NO UI string (assert absent).
        """
        # 1. Resolver surface
        for query in ["presto-k", "Marcus Hale", "Marcus Hale (CFO)", "cfo", "Kevin Presto"]:
            self.assertEqual(
                display_name(query),
                "Marcus Hale (CFO)",
                f"Resolver display_name('{query}') must return 'Marcus Hale (CFO)'",
            )

        # 2. Dropdown selectbox options surface
        at = AppTest.from_file(APP_FILE)
        at.run(timeout=10)
        self.assertEqual(len(at.error), 0)

        profile_sb = [sb for sb in at.sidebar.selectbox if "Active Executive Profile" in sb.label][0]
        self.assertTrue(
            any("Marcus Hale (CFO)" in opt for opt in profile_sb.options),
            "'Marcus Hale (CFO)' must be an option in the profile selectbox",
        )
        for opt in profile_sb.options:
            self.assertNotIn("Kevin Presto", opt, f"Option '{opt}' must not mention Kevin Presto")

        # 3. Attribution candidate & claimed sender contrast surfaces
        sample_forged = (
            "Dear Finance Team,\nPlease wire $184,500 immediately to the updated account. Thanks."
        )
        att = compute_attribution(sample_forged, "presto-k", alpha=0.05)
        self.assertEqual(
            att["claimed_sender"]["display_name"],
            "Marcus Hale (CFO)",
            "Claimed sender in attribution must be 'Marcus Hale (CFO)'",
        )
        for cand in att["all_ranked_candidates"]:
            if cand["sender_id"] == "presto-k":
                self.assertEqual(
                    cand["display_name"],
                    "Marcus Hale (CFO)",
                    "presto-k candidate display_name must be 'Marcus Hale (CFO)'",
                )
            self.assertNotIn("Kevin Presto", cand["display_name"])

        # 4. Web UI text surfaces (audit inspection, captions, headers, markdown)
        all_ui_text = []
        for m in at.markdown:
            all_ui_text.append(m.value)
        for c in at.caption:
            all_ui_text.append(c.value)
        for inf in at.info:
            all_ui_text.append(inf.value)
        for sh in at.subheader:
            all_ui_text.append(sh.value)

        joined_ui = " ".join(all_ui_text)
        self.assertNotIn(
            "Kevin Presto",
            joined_ui,
            "Assert absent: 'Kevin Presto' must not appear in any Web UI text",
        )

        # Check msg_09 alert contrast line in Web UI
        audit_select = [sb for sb in at.selectbox if sb.key and "audit_select" in sb.key][0]
        audit_select.select_index(8).run(timeout=10)  # msg_09 is ALERT
        self.assertEqual(len(at.error), 0)

        alert_captions = [c.value for c in at.caption if "Claimed sender" in c.value]
        self.assertEqual(len(alert_captions), 1)
        self.assertIn("Marcus Hale (CFO)", alert_captions[0])
        self.assertNotIn("Kevin Presto", alert_captions[0])

        # 5. CLI surface (--demo and single-message evaluation)
        cli_result = subprocess.run(
            [sys.executable, "-m", "src.cli", "--demo"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        self.assertEqual(cli_result.returncode, 0)
        cli_out = cli_result.stdout
        self.assertIn("Marcus Hale (CFO)", cli_out)
        self.assertNotIn(
            "Kevin Presto",
            cli_out,
            "Assert absent: 'Kevin Presto' must not appear in CLI --demo output",
        )

    def test_c_regression_metrics_unaltered(self):
        """
        Test (c): Existing metrics.json is unaltered.
        """
        git_diff = subprocess.run(
            "git diff artifacts/metrics.json",
            shell=True,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        self.assertEqual(
            git_diff.stdout.strip(),
            "",
            "artifacts/metrics.json must be byte-identical and have no git diff",
        )


if __name__ == "__main__":
    unittest.main()
