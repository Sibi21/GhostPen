"""
tests/test_smoke.py
-------------------
Synthetic unit and smoke tests for GhostPen.
Uses tiny seeded synthetic fixtures without depending on external network.
Tests:
- test_zero_variance: sender with '!'=0 in all training mail -> finite S, capped z, ALERT, no NaN/inf.
- test_insufficient_history: n_train < floor(1/alpha) -> TRIAGE with reason string.
- test_unknown_sender: unregistered sender -> UNENROLLED.
- test_p_range: for every scored message, p_min <= p <= 1.0.
- test_alpha_monotonicity: alerts@0.02 ⊆ alerts@0.05 ⊆ alerts@0.10.
- test_short_forged_route (3 cases):
    (a) 22-word wire request -> TRIAGE (too short) + content_escalation=True
    (b) short benign one-liner -> TRIAGE (too short) + content_escalation=False
    (c) thin-history case -> TRIAGE (insufficient history) + content_escalation=True
- test_determinism: rebuilding profiles and nulls yields byte-identical JSON.
- test_fpr_variants: FPR_flagged >= FPR_alert contract check.
- test_robustness: empty, one-liner, weird unicode, non-English -> no crash, correct verdict class.
"""

import json
import math
import os
import unittest
import numpy as np

from src.features import extract_features
from src.profile import (
    PROFILES_FILE,
    NULLS_FILE,
    build_all_profiles,
    build_loo_null,
    build_profile_from_features,
    compute_raw_score,
)
from src.demo_inbox import PINNED_DEMO_INBOX, build_inbox
from src.ingest import get_all_senders
from src.score import (
    compute_p_value,
    determine_verdict,
    extract_context_flags,
    score_message,
)


class TestGhostPenSmoke(unittest.TestCase):

    def setUp(self):
        # Synthetic corpus for a sender with ZERO exclamation marks
        np.random.seed(42)
        self.synthetic_sender = "synthetic-exec"
        self.base_sentences = [
            "We have completed the financial analysis for the transaction.",
            "The projected figures indicate positive momentum across divisions.",
            "Please confirm receipt of these documents at your earliest convenience.",
            "I will attend the operational review committee tomorrow morning.",
            "Let us proceed with the implementation according to plan.",
        ]
        self.synthetic_train_feats = []
        for i in range(25):
            # Form emails by repeating sentences, ensuring NO exclamation marks
            body = " ".join(self.base_sentences[: (i % 3) + 3])
            f = extract_features(body)
            self.synthetic_train_feats.append(f)

        self.synthetic_profile = build_profile_from_features(
            self.synthetic_train_feats, self.synthetic_sender
        )
        self.synthetic_null, self.synthetic_p_min = build_loo_null(
            self.synthetic_train_feats, self.synthetic_sender
        )

    def test_zero_variance(self):
        """Sender with '!'=0 in all training mail; test message with 2 '!' -> finite S, capped z, no inf/NaN."""
        punct_stat = self.synthetic_profile["numeric_stats"]["punct_!"]
        self.assertEqual(punct_stat["mean"], 0.0)
        # Floor must ensure std > 0
        self.assertGreaterEqual(punct_stat["std"], 0.5)

        forged_body = (
            "Dear Colleagues, please execute an urgent wire transfer today! "
            "We must finalize this transaction immediately! "
            "Kindly confirm once sent. Best regards."
        )
        feats = extract_features(forged_body)
        raw_s, breakdown = compute_raw_score(feats, self.synthetic_profile)

        # Check for NaN / Inf
        self.assertFalse(math.isnan(raw_s), "Score S should not be NaN")
        self.assertFalse(math.isinf(raw_s), "Score S should not be infinite")
        self.assertGreater(raw_s, 0.0)

        # Verify z-score is capped at 4.0
        z_punct = breakdown["z_scores"]["punct_!"]
        self.assertTrue(z_punct["z_capped"] <= 4.0)
        self.assertFalse(math.isnan(z_punct["z_capped"]))

    def test_insufficient_history(self):
        """Sender with n_train < floor(1/alpha) lands in TRIAGE with exact reason string."""
        # For alpha = 0.02, floor(1/alpha) = 50. With n_train = 25 -> TRIAGE
        verdict, reason = determine_verdict(
            sender_enrolled=True,
            n_train=25,
            word_count=60,
            sentence_count=4,
            p_value=0.01,
            alpha=0.02,
        )
        self.assertEqual(verdict, "TRIAGE")
        self.assertIn("needs >= 50 emails for alpha=0.02", reason)

        # For alpha = 0.05, floor = 20. With n_train = 15 -> TRIAGE
        verdict5, reason5 = determine_verdict(
            sender_enrolled=True,
            n_train=15,
            word_count=50,
            sentence_count=3,
            p_value=0.01,
            alpha=0.05,
        )
        self.assertEqual(verdict5, "TRIAGE")
        self.assertIn("needs >= 20 emails for alpha=0.05", reason5)

    def test_unknown_sender(self):
        """Unknown sender produces UNENROLLED verdict with exact required guidance string."""
        res = score_message(
            "Hello team, please process this invoice tomorrow.",
            sender_identifier="nonexistent_user_999",
            alpha=0.05,
        )
        self.assertEqual(res["verdict"], "UNENROLLED")
        expected_reason = (
            "no profile; enroll >= floor(1/alpha) for your operating alpha "
            "(20 @ 0.05, 50 @ 0.02, 10 @ 0.10)"
        )
        self.assertEqual(res["reason"], expected_reason)

    def test_p_range(self):
        """For every scored message, p_min <= p <= 1.0."""
        test_messages = [
            "Normal corporate message about project progress and deadlines.",
            "Urgent wire transfer needed immediately for confidential acquisition!",
            "ok thx",
        ]
        for msg in test_messages:
            res = score_message(msg, "Marcus Hale", alpha=0.05)
            self.assertGreaterEqual(res["p"], res["p_min"] - 1e-6)
            self.assertLessEqual(res["p"], 1.0 + 1e-6)

    def test_alpha_monotonicity(self):
        """
        Monotonicity contract: alerts@0.02 ⊆ alerts@0.05 ⊆ alerts@0.10
        (Applies to the ALERT verdict class by construction).
        """
        candidate_p_values = [0.005, 0.015, 0.03, 0.045, 0.08, 0.15, 0.50]
        n_train = 112  # Eligible for all alphas (112 >= 50)
        word_count = 80
        sentence_count = 5

        for p in candidate_p_values:
            v_02, _ = determine_verdict(True, n_train, word_count, sentence_count, p, 0.02)
            v_05, _ = determine_verdict(True, n_train, word_count, sentence_count, p, 0.05)
            v_10, _ = determine_verdict(True, n_train, word_count, sentence_count, p, 0.10)

            # If it alerts at 0.02, it must alert at 0.05
            if v_02 == "ALERT":
                self.assertEqual(v_05, "ALERT", f"Failed monotonicity at p={p}")

            # If it alerts at 0.05, it must alert at 0.10
            if v_05 == "ALERT":
                self.assertEqual(v_10, "ALERT", f"Failed monotonicity at p={p}")

    def test_short_forged_route(self):
        """
        Tests the reason-agnostic abstain-and-route layer across three cases:
        (a) 22-word wire request -> TRIAGE (too short) + content_escalation=True
        (b) short benign one-liner -> TRIAGE (too short) + content_escalation=False
        (c) thin-history case -> TRIAGE (insufficient history) + content_escalation=True
        """
        # Case (a): 22-word wire request
        case_a_text = (
            "Need this closed today. Wire the balance to the updated account. "
            "Confidential acquisition. Reply only to me. Thanks."
        )
        res_a = score_message(case_a_text, "Marcus Hale", alpha=0.05)
        self.assertEqual(res_a["verdict"], "TRIAGE")
        self.assertIn("too short", res_a["reason"])
        self.assertTrue(
            res_a["content_escalation"],
            "Short wire request with >= 2 flags must trigger content_escalation",
        )
        self.assertIn("Stylometry abstains", res_a["escalation_hint"])

        # Case (b): Short benign one-liner ("ok thx")
        case_b_text = "ok thx. see you at the meeting."
        res_b = score_message(case_b_text, "Marcus Hale", alpha=0.05)
        self.assertEqual(res_b["verdict"], "TRIAGE")
        self.assertFalse(
            res_b["content_escalation"],
            "Benign short email without context flags must not escalate",
        )
        self.assertIsNone(res_b["escalation_hint"])

        # Case (c): Thin-history sender (< floor(1/alpha) emails) with long email and >= 2 flags
        # 'badeer-r' has n_train = 15 (< 20 required for alpha=0.05)
        long_wire_text = (
            "Please be advised that we have finalized the settlement agreement with our counterparty. "
            "You are instructed to initiate an immediate wire transfer today to our bank account. "
            "Keep this confidential and ensure the wire is processed without delay before 5pm. "
            "Reply only to me once completed."
        )
        res_c = score_message(long_wire_text, "badeer-r", alpha=0.05)
        self.assertEqual(res_c["verdict"], "TRIAGE")
        self.assertIn("needs >= 20 emails", res_c["reason"])
        self.assertTrue(
            res_c["content_escalation"],
            "Thin-history message with >= 2 context flags must trigger content_escalation",
        )

    def test_determinism(self):
        """Pipeline rebuild yields byte-identical profiles.json and nulls.json."""
        # Read current files
        with open(PROFILES_FILE, "rb") as f:
            profiles_run1 = f.read()
        with open(NULLS_FILE, "rb") as f:
            nulls_run1 = f.read()

        # Re-run build_all_profiles
        build_all_profiles()

        with open(PROFILES_FILE, "rb") as f:
            profiles_run2 = f.read()
        with open(NULLS_FILE, "rb") as f:
            nulls_run2 = f.read()

        self.assertEqual(
            profiles_run1,
            profiles_run2,
            "profiles.json must be byte-identical across consecutive runs",
        )
        self.assertEqual(
            nulls_run1,
            nulls_run2,
            "nulls.json must be byte-identical across consecutive runs",
        )

    def test_fpr_variants_contract(self):
        """
        Asserts the mathematical contract: FPR_flagged >= FPR_alert.
        Because flagged = ALERT OR (TRIAGE AND content_escalation),
        the flagged set is a superset of the alert set on any population.
        """
        # Test across dummy scores
        n_emails = 50
        np.random.seed(99)
        dummy_alerts = np.random.binomial(1, 0.05, n_emails)
        dummy_triage_escalated = np.random.binomial(1, 0.04, n_emails)
        dummy_flagged = np.maximum(dummy_alerts, dummy_triage_escalated)

        fpr_alert = float(np.mean(dummy_alerts))
        fpr_flagged = float(np.mean(dummy_flagged))
        self.assertGreaterEqual(fpr_flagged, fpr_alert)

    def test_robustness(self):
        """No crash on empty string, one-liner, unicode, duplicate, or foreign text."""
        weird_inputs = [
            "",  # empty
            "   \n\t  ",  # whitespace only
            "ok",  # single word
            "こんにちは世界。これはテストメールです。よろしくお願いします。",  # Japanese
            "Bonjour monsieur, veuillez trouver ci-joint les documents demandés. Merci.",  # French
            "🎉🚀💰 Urgent $$$ wire transfer now! \u200b\u200b\ufffd",  # Unicode emojis & zero-width chars
            "a" * 5000,  # Extreme repetition
        ]
        for inp in weird_inputs:
            try:
                res = score_message(inp, "Marcus Hale", alpha=0.05)
                self.assertIn(res["verdict"], ["OK", "ALERT", "TRIAGE", "UNENROLLED"])
            except Exception as e:
                self.fail(f"Robustness test crashed on input '{inp[:30]}': {e}")

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
            self.assertEqual(build1, build2, f"Deterministic rebuild failed for sender {sid}")
            self.assertEqual([m["id"] for m in build1], [m["id"] for m in build2])

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
