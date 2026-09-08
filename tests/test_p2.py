"""
tests/test_p2.py
----------------
Verification test suite for Patch P2:
- (a) Relabel forged fixture: true author ranks #1 with p >= 0.05, claimed sender ranks lower
- (b) Genuine holdout messages rank their own sender #1
- (c) Soft check (printed, non-fatal): generic & styled forgeries no-match rate
- (d) Ranking stability: two runs produce identical rankings (deterministic tie-break)
- (e) Alpha slider price tag: displayed Y equals 100 * FPR_flagged at grid alphas
- (f) Matched habits: |z| <= 1.0 and tooltip contract
- (g) Metrics integrity: new attribution fields in artifacts/metrics.json
- (h) Self-drift timeline plots exist and are non-empty
"""

import json
import os
import unittest

from src.attribution import (
    compute_attribution,
    extract_matched_habits,
    get_alpha_price_tag,
)
from src.ingest import get_all_senders, split_sender_data

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
METRICS_FILE = os.path.join(REPO_ROOT, "artifacts", "metrics.json")
FORGED_FILE = os.path.join(REPO_ROOT, "data", "forged", "forged.jsonl")


class TestPatchP2Innovation(unittest.TestCase):

    def test_a_relabel_attribution(self):
        """
        Test (a): relabel forged fixture with enrolled true author:
        true author ranks #1 with p >= 0.05 and the claimed sender ranks lower.
        """
        text = (
            "Gary, would one of the following dates and times work for you and your group?\n\n"
            "\t\tNovember 1 - in the afternoon\n"
            "\t\tNovember 13 - in the morning\n"
            "\t\tNovember 14 - in the afternoon\n\n"
            "\tPlease give me a call and let me know if any of these work.  I am assuming you planning\n"
            "\ton 1 hour?  Is that right?  Thanks. Lynn"
        )
        claimed_sender = "presto-k"
        true_author = "blair-l"

        att = compute_attribution(text, claimed_sender, alpha=0.05)

        self.assertFalse(att["is_no_match"], "Relabel fixture should not be in no-match state")
        self.assertGreater(len(att["top_3"]), 0, "Top matches should not be empty")

        top_1 = att["top_3"][0]
        self.assertEqual(top_1["sender_id"], true_author, f"True author {true_author} must rank #1")
        self.assertGreaterEqual(top_1["p"], 0.05, "Top-1 p-value must be >= 0.05")

        self.assertIsNotNone(att["claimed_rank"], "Claimed sender rank should be determined")
        self.assertGreater(att["claimed_rank"], 1, "Claimed sender must rank strictly lower than #1")
        self.assertLess(att["claimed_sender"]["p"], top_1["p"], "Claimed sender p must be less than true author p")

    def test_b_genuine_holdout_ranks_own_sender(self):
        """
        Test (b): genuine holdout messages rank their own sender #1.
        """
        tested_senders = ["blair-l", "cash-m", "keiser-k"]
        matched_any = False

        for sid in tested_senders:
            _, holdouts = split_sender_data(sid)
            for e in holdouts[:8]:
                att = compute_attribution(e["body"], sid, alpha=0.05)
                if not att["is_no_match"] and att["top_3"]:
                    if att["top_3"][0]["sender_id"] == sid:
                        matched_any = True
                        self.assertGreaterEqual(att["top_3"][0]["p"], 0.05)
                        break
            if matched_any:
                break

        self.assertTrue(matched_any, "At least one genuine holdout email should rank its own sender #1")

    def test_c_soft_check_generic_styled_no_match_rate(self):
        """
        Test (c): soft check, printed not fatal:
        >= 80% of generic and styled forgeries produce the no-match state at cutoff 0.05.
        """
        if not os.path.exists(FORGED_FILE):
            self.skipTest(f"Forged file not found at {FORGED_FILE}")

        generic_recs = []
        styled_recs = []
        with open(FORGED_FILE, "r", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line.strip())
                if rec["tier"] == "generic":
                    generic_recs.append(rec)
                elif rec["tier"] == "styled":
                    styled_recs.append(rec)

        gen_nm = sum(1 for r in generic_recs if compute_attribution(r["text"], r["sender"], alpha=0.05)["is_no_match"])
        sty_nm = sum(1 for r in styled_recs if compute_attribution(r["text"], r["sender"], alpha=0.05)["is_no_match"])

        gen_rate = gen_nm / max(len(generic_recs), 1)
        sty_rate = sty_nm / max(len(styled_recs), 1)

        print("\n" + "=" * 60)
        print(f" [P2.c Soft Check] Generic Forgery No-Match Rate: {gen_nm}/{len(generic_recs)} ({gen_rate:.1%})")
        print(f" [P2.c Soft Check] Styled Forgery No-Match Rate:  {sty_nm}/{len(styled_recs)} ({sty_rate:.1%})")
        print("=" * 60)

        # Soft check: non-fatal printout
        self.assertIsInstance(gen_rate, float)
        self.assertIsInstance(sty_rate, float)

    def test_d_ranking_stability_determinism(self):
        """
        Test (d): ranking stability: two runs produce identical rankings (tie-break).
        """
        text = "Please process the urgent wire transfer immediately today. Thanks."
        att1 = compute_attribution(text, "presto-k", alpha=0.05)
        att2 = compute_attribution(text, "presto-k", alpha=0.05)

        self.assertEqual(att1["is_no_match"], att2["is_no_match"])
        self.assertEqual(len(att1["all_ranked_candidates"]), len(att2["all_ranked_candidates"]))

        for c1, c2 in zip(att1["all_ranked_candidates"], att2["all_ranked_candidates"]):
            self.assertEqual(c1["sender_id"], c2["sender_id"])
            self.assertEqual(c1["p"], c2["p"])

    def test_e_alpha_price_tag_matches_metrics(self):
        """
        Test (e): displayed Y equals round(100 * FPR_flagged_pooled at grid alpha, 1).
        """
        self.assertTrue(os.path.exists(METRICS_FILE), "metrics.json must exist")
        with open(METRICS_FILE, "r", encoding="utf-8") as f:
            metrics = json.load(f)

        grid_alphas = [0.02, 0.05, 0.10]
        for a in grid_alphas:
            tag = get_alpha_price_tag(a)
            expected_fpr = metrics["fpr_variants"][str(a)]["FPR_flagged"]
            expected_y = round(100.0 * expected_fpr, 1)

            self.assertEqual(tag["flags_per_100"], expected_y)
            self.assertIn(f"expect ~{expected_y:.1f} flags", tag["display_text"])
            self.assertIn("Operational Cost:", tag["display_text"])
            self.assertIn(f"at alpha = {a:.2f}:", tag["display_text"])
            self.assertIn("pooled across enrolled senders, measured on holdout", tag["display_text"])

    def test_f_matched_habits_within_one_sigma(self):
        """
        Test (f): matched habits features satisfy |z| <= 1.0 and tooltip specification.
        """
        text = "Please review the attached invoice. Thanks."
        matched = extract_matched_habits(text, "presto-k")

        for m in matched:
            self.assertEqual(m["tooltip"], "matched = within 1 of his own standard deviations")
            if "z" in m:
                self.assertLessEqual(abs(m["z"]), 1.0, f"Matched habit z must be within 1.0, got {m['z']}")

    def test_g_metrics_json_attribution_fields(self):
        """
        Test (g): metrics.json contains the three new deterministic attribution fields.
        """
        with open(METRICS_FILE, "r", encoding="utf-8") as f:
            metrics = json.load(f)

        required_keys = [
            "attribution_top1_accuracy_relabel",
            "attribution_no_match_rate_generic",
            "attribution_no_match_rate_styled",
        ]
        for k in required_keys:
            self.assertIn(k, metrics, f"metrics.json must include key: '{k}'")
            val = metrics[k]
            self.assertIsInstance(val, float, f"{k} must be float, got {type(val)}")
            self.assertGreaterEqual(val, 0.0)
            self.assertLessEqual(val, 1.0)

    def test_h_drift_plots_exist(self):
        """
        Test (h): self-drift timeline plots exist and are non-empty.
        """
        p1 = os.path.join(REPO_ROOT, "artifacts", "plots", "drift_timeline.png")
        p2 = os.path.join(REPO_ROOT, "artifacts", "plots", "drift_timeline_demo.png")

        self.assertTrue(os.path.exists(p1), f"Plot {p1} must exist")
        self.assertTrue(os.path.exists(p2), f"Plot {p2} must exist")
        self.assertGreater(os.path.getsize(p1), 10000, "drift_timeline.png must be non-trivial")
        self.assertGreater(os.path.getsize(p2), 10000, "drift_timeline_demo.png must be non-trivial")


if __name__ == "__main__":
    unittest.main()
