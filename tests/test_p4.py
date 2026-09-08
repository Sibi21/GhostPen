"""
tests/test_p4.py
----------------
Verification test suite for Patch P4 (abstain-rate reporting):
- test_abstain_fields:
  * Three new fields exist in metrics.json:
    - abstain_rate_genuine_holdout_pooled
    - abstain_rate_genuine_holdout_per_sender
    - abstain_rate_demo_inbox
  * All values are in [0, 1].
  * Each field equals the recomputed share from holdout verdict lists.
  * Per-sender objects keep the reason split (too_short vs insufficient_history).
- test_preexisting_metrics_integrity:
  * All 14 pre-existing keys in metrics.json are preserved with matching structure and types.
"""

import json
import math
import os
import unittest

from src.ingest import get_all_senders, split_sender_data
from src.score import score_message

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
METRICS_FILE = os.path.join(REPO_ROOT, "artifacts", "metrics.json")
DEMO_INBOX_FILE = os.path.join(REPO_ROOT, "data", "demo_inbox.json")

PREEXISTING_KEYS = [
    "attribution_no_match_rate_generic",
    "attribution_no_match_rate_styled",
    "attribution_top1_accuracy_relabel",
    "baseline_comparison_table",
    "bayesian_precision",
    "claim_discipline",
    "copy_audit_summary",
    "detection_definition",
    "evaluation_summary",
    "fpr_variants",
    "per_sender_breakdown",
    "recall_by_tier",
    "routing_layer_cost",
    "worst_sender",
]


class TestPatchP4Abstain(unittest.TestCase):

    def setUp(self):
        self.assertTrue(os.path.exists(METRICS_FILE), f"metrics.json missing at {METRICS_FILE}")
        with open(METRICS_FILE, "r", encoding="utf-8") as f:
            self.metrics = json.load(f)

    def test_abstain_fields(self):
        """
        P4.4: The three new fields exist, are in [0, 1], and equal
        the recomputed share from the holdout verdict lists.
        """
        # 1. Existence of top-level fields
        self.assertIn("abstain_rate_genuine_holdout_pooled", self.metrics)
        self.assertIn("abstain_rate_genuine_holdout_per_sender", self.metrics)
        self.assertIn("abstain_rate_demo_inbox", self.metrics)

        pooled_val = self.metrics["abstain_rate_genuine_holdout_pooled"]
        demo_val = self.metrics["abstain_rate_demo_inbox"]
        per_sender = self.metrics["abstain_rate_genuine_holdout_per_sender"]

        # 2. Value range [0, 1]
        self.assertIsInstance(pooled_val, float)
        self.assertGreaterEqual(pooled_val, 0.0)
        self.assertLessEqual(pooled_val, 1.0)

        self.assertIsInstance(demo_val, float)
        self.assertGreaterEqual(demo_val, 0.0)
        self.assertLessEqual(demo_val, 1.0)

        self.assertIsInstance(per_sender, dict)

        # 3. Recompute from genuine holdout verdict lists
        senders = get_all_senders()
        self.assertEqual(len(per_sender), len(senders), "All enrolled senders must be present")

        total_holdout_count = 0
        total_too_short_count = 0

        for s in senders:
            sid = s["sender_id"]
            self.assertIn(sid, per_sender, f"Sender {sid} missing from per-sender abstain metrics")
            s_obj = per_sender[sid]

            self.assertIn("abstain_rate", s_obj)
            self.assertIn("too_short", s_obj)
            self.assertIn("insufficient_history", s_obj)
            self.assertIn("split_by_triage_reason", s_obj)

            # Check ranges in [0, 1]
            self.assertTrue(0.0 <= s_obj["abstain_rate"] <= 1.0)
            self.assertTrue(0.0 <= s_obj["too_short"] <= 1.0)
            self.assertTrue(0.0 <= s_obj["insufficient_history"] <= 1.0)

            train, holdout = split_sender_data(sid)
            n_train = len(train)
            n_holdout = len(holdout)
            total_holdout_count += n_holdout

            recomp_too_short = 0
            recomp_thin = 0
            for e in holdout:
                res = score_message(e["body"], sid, alpha=0.05)
                wc = res["word_count"]
                sc = res["sentence_count"]
                if wc < 40 or sc < 3:
                    recomp_too_short += 1
                elif n_train < int(math.floor(1.0 / 0.05)):
                    recomp_thin += 1

            total_too_short_count += recomp_too_short

            expected_too_short_rate = round(recomp_too_short / max(n_holdout, 1), 4)
            expected_thin_rate = round(recomp_thin / max(n_holdout, 1), 4)

            self.assertEqual(s_obj["too_short"], expected_too_short_rate)
            self.assertEqual(s_obj["insufficient_history"], expected_thin_rate)
            self.assertEqual(s_obj["abstain_rate"], expected_too_short_rate)

        # Recomputed pooled share
        expected_pooled = round(total_too_short_count / max(total_holdout_count, 1), 4)
        self.assertEqual(pooled_val, expected_pooled)
        self.assertEqual(pooled_val, 0.4019)

        # 4. Recompute canonical demo inbox
        self.assertTrue(os.path.exists(DEMO_INBOX_FILE), "Demo inbox file must exist")
        with open(DEMO_INBOX_FILE, "r", encoding="utf-8") as f:
            demo_msgs = json.load(f)

        recomp_demo_triage = 0
        for m in demo_msgs:
            res = score_message(m["body"], "presto-k", alpha=0.05)
            if res["verdict"] == "TRIAGE":
                recomp_demo_triage += 1

        expected_demo_rate = round(recomp_demo_triage / max(len(demo_msgs), 1), 4)
        self.assertEqual(demo_val, expected_demo_rate)
        self.assertEqual(demo_val, 0.2143)

    def test_preexisting_metrics_integrity(self):
        """
        All 14 pre-existing keys in metrics.json must exist with intact values and types.
        """
        for k in PREEXISTING_KEYS:
            self.assertIn(k, self.metrics, f"Pre-existing key '{k}' must exist in metrics.json")

        # Verify key baseline values are intact
        self.assertEqual(self.metrics["bayesian_precision"]["FPR_flagged_at_005"], 0.0171)
        self.assertEqual(self.metrics["bayesian_precision"]["flags_per_100_genuine_emails"], 1.71)
        self.assertEqual(self.metrics["evaluation_summary"]["total_senders"], 15)
        self.assertEqual(self.metrics["evaluation_summary"]["total_holdout_emails"], 525)
        self.assertEqual(self.metrics["routing_layer_cost"]["split_by_triage_reason"]["too_short"]["total_messages"], 211)
        self.assertEqual(self.metrics["routing_layer_cost"]["split_by_triage_reason"]["insufficient_history"]["total_messages"], 11)


if __name__ == "__main__":
    unittest.main()
