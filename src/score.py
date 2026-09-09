"""
src/score.py
------------
Scoring engine, conformal p-value calibration, pure verdict function,
and display-layer abstain-and-route escalation logic.

Detection Definition (Verbatim):
flagged = ALERT OR (TRIAGE AND content_escalation); caught = flagged.
"""

import math
import re
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.features import extract_features
from src.profile import (
    compute_raw_score,
    load_null,
    load_profile,
)

CONTEXT_FLAG_PATTERNS = [
    (r"\burgent\b", "urgent"),
    (r"\basap\b", "asap"),
    (r"\bwire\b", "wire"),
    (r"\btransfer\b", "transfer"),
    (r"\bbank\b", "bank"),
    (r"\binvoice\b", "invoice"),
    (r"\bconfidential\b", "confidential"),
    (r"\bgift\s*cards?\b", "gift card"),
    (r"\bpayroll\b", "payroll"),
    (r"\breply\s+only\s+to\s+me\b", "reply only to me"),
    (r"\btoday\b", "today"),
]


def extract_context_flags(text: str) -> List[str]:
    """Identifies BEC context flags in the message text."""
    lower_text = text.lower()
    flags = []
    for pattern, name in CONTEXT_FLAG_PATTERNS:
        if re.search(pattern, lower_text):
            flags.append(name)
    return sorted(list(set(flags)))


def compute_p_value(raw_s: float, null_scores: List[float]) -> Tuple[float, float]:
    """
    Computes exact empirical p-value from leave-one-out null distribution:
    p = (1 + #{null >= S}) / (N + 1)
    p_min = 1 / (N + 1)
    """
    n = len(null_scores)
    if n == 0:
        return 1.0, 1.0

    count_ge = sum(1 for s in null_scores if s >= raw_s)
    p = (1.0 + count_ge) / (n + 1.0)
    p_min = 1.0 / (n + 1.0)
    return float(p), float(p_min)


def determine_verdict(
    sender_enrolled: bool,
    n_train: int,
    word_count: int,
    sentence_count: int,
    p_value: float,
    alpha: float,
) -> Tuple[str, str]:
    """
    Pure verdict function evaluated in strict order:
    1. sender has no profile -> UNENROLLED
    2. word count < 40 or sentence count < 3 -> TRIAGE (message too short)
    3. n_train < floor(1/alpha) -> TRIAGE (insufficient history)
    4. p < alpha -> ALERT
    5. otherwise -> OK
    """
    if not sender_enrolled:
        return (
            "UNENROLLED",
            "no profile; enroll >= floor(1/alpha) for your operating alpha (20 @ 0.05, 50 @ 0.02, 10 @ 0.10)",
        )

    if word_count < 40 or sentence_count < 3:
        return (
            "TRIAGE",
            "message too short (<40 words or <3 sentences)",
        )

    min_required_train = int(math.floor(1.0 / alpha))
    if n_train < min_required_train:
        return (
            "TRIAGE",
            f"needs >= {min_required_train} emails for alpha={alpha}",
        )

    if p_value < alpha:
        return (
            "ALERT",
            f"Stylometric deviation exceeds threshold (p={p_value:.3f} < alpha={alpha})",
        )

    return (
        "OK",
        f"Style aligns with enrolled profile (p={p_value:.3f} >= alpha={alpha})",
    )


def build_direction_and_habits(
    breakdown: Dict, profile: Dict, features: Dict
) -> Tuple[str, List[str], List[Dict]]:
    """
    Produces plain-English broken habits and directional shift description.
    """
    broken_habits = []
    direction_notes = []
    feature_contributions = []

    # 1. Broken habits
    if breakdown.get("broken_greeting"):
        broken_habits.append(breakdown["broken_greeting"])
    if breakdown.get("broken_signoff"):
        broken_habits.append(breakdown["broken_signoff"])

    # 2. Punctuation abnormalities
    for p in ["!", "?", ";", ":", "—"]:
        z_info = breakdown["z_scores"].get(f"punct_{p}")
        if z_info:
            obs = z_info["obs"]
            m = z_info["mean"]
            if obs > 0 and m == 0:
                raw_cnt = int(round(obs * features["word_count"] / 100.0))
                broken_habits.append(
                    f"Punctuation '{p}': {max(raw_cnt, 1)} occurrences (0 observed in {profile['n_train']} past emails)"
                )

    # 3. Directional shifts (formality, contractions, sentence variance)
    form_z = breakdown["z_scores"]["formality_rate"]["z_capped"]
    if form_z >= 1.5:
        direction_notes.append(f"Formality +{form_z:.1f} sigma above baseline norm")

    contr_mean = profile["numeric_stats"]["contraction_rate"]["mean"]
    contr_obs = features["contraction_rate"]
    if contr_mean >= 1.0 and contr_obs == 0.0:
        direction_notes.append(f"Contractions {contr_mean:.1f}/100w -> 0.0")
    elif breakdown["z_scores"]["contraction_rate"]["z_capped"] <= -1.5:
        direction_notes.append(f"Contractions {breakdown['z_scores']['contraction_rate']['z_capped']:.1f} sigma below baseline norm")

    sent_std_z = breakdown["z_scores"]["sentence_len_std"]["z_capped"]
    if sent_std_z <= -1.5:
        direction_notes.append("Sentence rhythm unnaturally uniform (low burstiness)")

    # 4. Feature contributions for transparency (sorted descending)
    for key, z_info in breakdown["z_scores"].items():
        name = key.replace("punct_", "punctuation_")
        capped_flag = " (>= 4 sigma, capped)" if z_info["capped"] else ""
        feature_contributions.append({
            "feature": name,
            "observed": z_info["obs"],
            "profile_mean": z_info["mean"],
            "profile_std": z_info["std"],
            "z_score": z_info["z_capped"],
            "capped": z_info["capped"],
            "note": f"z={z_info['z_capped']:+.2f}{capped_flag}",
        })

    # Sort contributions by absolute z-score
    feature_contributions.sort(key=lambda x: abs(x["z_score"]), reverse=True)

    direction_str = "; ".join(direction_notes) if direction_notes else "Style variation within normal baseline"
    return direction_str, broken_habits, feature_contributions


def score_message(
    text: str,
    sender_identifier: str,
    alpha: float = 0.05,
) -> Dict:
    """
    Primary scoring endpoint returning complete structured verdict JSON.
    """
    profile = load_profile(sender_identifier)
    null_data = load_null(sender_identifier)
    features = extract_features(text)
    context_flags = extract_context_flags(text)

    word_count = features["word_count"]
    sentence_count = features["sentence_count"]

    if profile is None or null_data is None:
        verdict, reason = determine_verdict(
            sender_enrolled=False,
            n_train=0,
            word_count=word_count,
            sentence_count=sentence_count,
            p_value=1.0,
            alpha=alpha,
        )
        return {
            "sender": sender_identifier,
            "deviation_score": 0.0,
            "p": 1.0,
            "p_min": 1.0,
            "n_train": 0,
            "verdict": verdict,
            "reason": reason,
            "direction": "N/A (unenrolled)",
            "broken_habits": [],
            "context_flags": context_flags,
            "content_escalation": False,
            "content_caution": False,
            "escalation_hint": None,
            "feature_contributions": [],
            "word_count": word_count,
            "sentence_count": sentence_count,
        }

    raw_s, breakdown = compute_raw_score(features, profile)
    p_val, p_min = compute_p_value(raw_s, null_data["null_scores"])
    n_train = profile["n_train"]

    verdict, reason = determine_verdict(
        sender_enrolled=True,
        n_train=n_train,
        word_count=word_count,
        sentence_count=sentence_count,
        p_value=p_val,
        alpha=alpha,
    )

    # Reason-agnostic Abstain-and-Route Escalation Rule:
    # If verdict == TRIAGE (for ANY reason: too short OR insufficient history) AND >= 2 context flags:
    content_escalation = False
    escalation_hint = None
    if verdict == "TRIAGE" and len(context_flags) >= 2:
        content_escalation = True
        escalation_hint = "Stylometry abstains — route to content controls / payment verification."

    direction_str, broken_habits, feature_contributions = build_direction_and_habits(
        breakdown, profile, features
    )

    return {
        "sender": sender_identifier,
        "canonical_sender_id": profile["sender_id"],
        "deviation_score": round(raw_s, 4),
        "p": round(p_val, 4),
        "p_min": round(p_min, 4),
        "n_train": n_train,
        "verdict": verdict,
        "reason": reason,
        "direction": direction_str,
        "broken_habits": broken_habits,
        "context_flags": context_flags,
        "content_escalation": content_escalation,
        "content_caution": (verdict == "OK" and len(context_flags) >= 2),
        "escalation_hint": escalation_hint,
        "feature_contributions": feature_contributions[:5],
        "delta_breakdown": {
            "delta_fw": breakdown["delta_fw"],
            "delta_cg": breakdown["delta_cg"],
            "mean_z_capped": breakdown["mean_z_capped"],
            "habit_penalty": breakdown["habit_penalty"],
        },
        "word_count": word_count,
        "sentence_count": sentence_count,
    }
