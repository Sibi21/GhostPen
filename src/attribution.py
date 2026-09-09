"""
src/attribution.py
------------------
Display-layer innovation add-ons for GhostPen (Patch P2):
- A1: "Who actually wrote this?" Cross-profile attribution panel
- A2: "What the disguise got right" Matched habits cards (|z| <= 1.0)
- A3: Alpha-slider price tag (operational SOC cost from metrics.json)
"""

import json
import math
import os
from typing import Dict, List, Optional, Tuple

from src.features import extract_features
from src.ingest import display_name, get_all_senders, resolve_sender_id
from src.profile import compute_raw_score, load_null, load_profile
from src.score import compute_p_value, determine_verdict, score_message

METRICS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "artifacts", "metrics.json"
)

FEATURE_FRIENDLY_NAMES = {
    "sentence_len_mean": "Average sentence length normal",
    "sentence_len_std": "Sentence length variation normal",
    "avg_word_len": "Average word length normal",
    "contraction_rate": "Contraction rate normal",
    "formality_rate": "Formality rate normal",
    "ttr": "Vocabulary diversity (TTR) normal",
    "punct_!": "Exclamation mark rate normal",
    "punct_?": "Question mark rate normal",
    "punct_;": "Semicolon rate normal",
    "punct_:": "Colon rate normal",
    "punct_—": "Em-dash rate normal",
}


def compute_attribution(
    body: str,
    claimed_sender_id: str,
    alpha: float = 0.05,
) -> Dict:
    """
    Evaluates message body against ALL enrolled senders' profiles.
    Ranks candidates by p-value descending, tie-breaking by sender_id ascending.

    Candidates for style alignment are drawn from enrolled senders calibrated
    at significance alpha (n_train >= floor(1/alpha)).
    If top-1 candidate has p < alpha:
        NO-MATCH STATE: "No enrolled author's style matches this message."
    Otherwise:
        Top-3 matching senders are returned with their p-values, alongside
        the claimed sender's p-value for contrast.
    """
    all_senders = get_all_senders()
    sender_map = {s["sender_id"]: s for s in all_senders}
    canonical_claimed = resolve_sender_id(claimed_sender_id) or claimed_sender_id

    min_required_train = int(math.floor(1.0 / alpha)) if alpha > 0 else 1

    scored_candidates = []
    claimed_info = None

    feats = extract_features(body)
    word_count = feats["word_count"]
    sentence_count = feats["sentence_count"]

    for s in all_senders:
        sid = s["sender_id"]
        prof = load_profile(sid)
        null_data = load_null(sid)
        if prof and null_data:
            raw_s, _ = compute_raw_score(feats, prof)
            p_val, p_min = compute_p_value(raw_s, null_data["null_scores"])
            n_train = prof["n_train"]
            v, _ = determine_verdict(
                sender_enrolled=True,
                n_train=n_train,
                word_count=word_count,
                sentence_count=sentence_count,
                p_value=p_val,
                alpha=alpha,
            )
            entry = {
                "sender_id": sid,
                "display_name": display_name(sid),
                "volume_class": s.get("volume_class", "high"),
                "p": round(p_val, 4),
                "deviation_score": round(raw_s, 4),
                "n_train": n_train,
                "verdict": v,
            }
        else:
            res = score_message(body, sid, alpha=alpha)
            entry = {
                "sender_id": sid,
                "display_name": display_name(sid),
                "volume_class": s.get("volume_class", "high"),
                "p": res["p"],
                "deviation_score": res["deviation_score"],
                "n_train": res["n_train"],
                "verdict": res["verdict"],
            }
        if sid == canonical_claimed:
            claimed_info = entry

        # Candidate eligibility for style alignment at level alpha:
        # sender must have calibrated history at alpha (n_train >= floor(1/alpha))
        if entry["n_train"] >= min_required_train:
            scored_candidates.append(entry)

    # If no sender satisfies min_required_train, fallback to all scored senders
    if not scored_candidates:
        scored_candidates = [
            {
                "sender_id": s["sender_id"],
                "display_name": display_name(s["sender_id"]),
                "volume_class": s.get("volume_class", "high"),
                "p": score_message(body, s["sender_id"], alpha=alpha)["p"],
                "deviation_score": score_message(body, s["sender_id"], alpha=alpha)["deviation_score"],
                "n_train": s.get("total_emails", 0),
                "verdict": "TRIAGE",
            }
            for s in all_senders
        ]

    # Deterministic ranking: p-value descending, sender_id ascending
    scored_candidates.sort(key=lambda x: (-x["p"], x["sender_id"]))

    top_candidate = scored_candidates[0]
    is_no_match = top_candidate["p"] < alpha

    if claimed_info is None:
        claimed_res = score_message(body, canonical_claimed, alpha=alpha)
        claimed_info = {
            "sender_id": canonical_claimed,
            "display_name": display_name(canonical_claimed),
            "volume_class": sender_map.get(canonical_claimed, {}).get("volume_class", "high"),
            "p": claimed_res["p"],
            "deviation_score": claimed_res["deviation_score"],
            "n_train": claimed_res["n_train"],
            "verdict": claimed_res["verdict"],
        }

    # Find claimed sender rank among candidates
    claimed_rank = None
    for idx, c in enumerate(scored_candidates):
        if c["sender_id"] == canonical_claimed:
            claimed_rank = idx + 1
            break

    top_3 = scored_candidates[:3] if not is_no_match else []

    no_match_text = (
        "No enrolled author's style matches this message." if is_no_match else None
    )

    return {
        "is_no_match": is_no_match,
        "no_match_text": no_match_text,
        "top_3": top_3,
        "top_candidate": top_candidate,
        "claimed_sender": claimed_info,
        "claimed_rank": claimed_rank,
        "all_ranked_candidates": scored_candidates,
        "alpha": alpha,
        "total_enrolled_senders": len(all_senders),
    }


def extract_matched_habits(text: str, sender_id: str, prefix: str = "attacker matched:") -> List[Dict]:
    """
    Identifies features where |z| <= 1.0 vs the sender profile.
    Returns plain-English green-card descriptors and tooltip metadata.
    """
    profile = load_profile(sender_id)
    if profile is None:
        return []

    features = extract_features(text)
    _, breakdown = compute_raw_score(features, profile)
    z_scores = breakdown.get("z_scores", {})

    matched_cards = []

    pfx = (prefix or "").strip()
    if pfx and not pfx.endswith(":"):
        pfx = f"{pfx}:"
    prefix_str = f"{pfx} " if pfx else ""

    # 1. Habitual sign-off match
    signoff_obs = features.get("signoff", "none")
    dom_sign = profile.get("dominant_signoff")
    dom_sign_cons = profile.get("dominant_signoff_consistency", 0.0)
    if signoff_obs and dom_sign and signoff_obs.lower() == dom_sign.lower() and signoff_obs != "none":
        matched_cards.append({
            "title": f"{prefix_str}signs '{signoff_obs}'",
            "detail": f"Matches habitual sign-off (observed {int(dom_sign_cons * 100)}% in enrolled mail)",
            "tooltip": "matched = within 1 of his own standard deviations",
            "category": "habit",
        })

    # 2. Habitual greeting match
    greet_obs = features.get("greeting", "none")
    dom_greet = profile.get("dominant_greeting")
    dom_greet_cons = profile.get("dominant_greeting_consistency", 0.0)
    if greet_obs and dom_greet and greet_obs.lower() == dom_greet.lower() and greet_obs != "none":
        matched_cards.append({
            "title": f"{prefix_str}greeting '{greet_obs}'",
            "detail": f"Matches habitual greeting (observed {int(dom_greet_cons * 100)}% in enrolled mail)",
            "tooltip": "matched = within 1 of his own standard deviations",
            "category": "habit",
        })

    # 3. Numeric features with |z| <= 1.0
    for key, info in z_scores.items():
        z_val = info.get("z", 0.0)
        if abs(z_val) <= 1.0:
            friendly = FEATURE_FRIENDLY_NAMES.get(key, f"Feature {key} normal")
            matched_cards.append({
                "title": f"{prefix_str}{friendly.lower()}",
                "detail": f"z = {z_val:+.2f} (profile mean: {info['mean']:.2f}, observed: {info['obs']:.2f})",
                "tooltip": "matched = within 1 of his own standard deviations",
                "category": "numeric",
                "feature": key,
                "z": z_val,
            })

    return matched_cards


def get_alpha_price_tag(alpha: float, metrics_file: str = METRICS_FILE) -> Dict:
    """
    Computes operational SOC cost indicator beside alpha slider:
    "at alpha = X: expect ~Y flags per 100 genuine emails (measured on holdout)"
    where Y = 100 * FPR_flagged at nearest grid alpha in {0.02, 0.05, 0.10},
    read from metrics.json.
    """
    grid_alphas = [0.02, 0.05, 0.10]
    nearest_alpha = min(grid_alphas, key=lambda a: abs(a - alpha))

    fpr_flagged = 0.0171  # fallback default @ 0.05
    if os.path.exists(metrics_file):
        try:
            with open(metrics_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            fpr_variants = data.get("fpr_variants", {})
            alpha_key = str(nearest_alpha)
            if alpha_key in fpr_variants:
                fpr_flagged = fpr_variants[alpha_key].get("FPR_flagged", fpr_flagged)
        except Exception:
            pass

    y_flags = round(100.0 * fpr_flagged, 1)
    display_text = (
        f"Operational Cost: at alpha = {alpha:.2f}: expect ~{y_flags:.1f} flags per 100 genuine emails (pooled across enrolled senders, measured on holdout)"
    )

    return {
        "alpha": alpha,
        "nearest_grid_alpha": nearest_alpha,
        "fpr_flagged": fpr_flagged,
        "flags_per_100": y_flags,
        "display_text": display_text,
    }
