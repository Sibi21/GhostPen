"""
src/profile.py
--------------
Habit Ledger construction and Leave-One-Out (LOO) target-null calibration.
Features:
- Winsorizing at 5th/95th percentiles
- Mean and standard deviation computation with EPS floors per feature family
- Individual |z| capped at 4.0 (flagged as '>= 4 sigma (capped)')
- Burrows' Delta on function words and character 3-grams
- Observed greeting and sign-off habit distributions (with 'none' tracked)
- Leave-One-Out (LOO) null score distribution computation
"""

import argparse
import collections
import json
import math
import os
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.features import (
    EPS_FLOORS,
    FUNCTION_WORDS,
    PUNCT_TARGETS,
    TOP_CHAR_3GRAMS,
    extract_features,
)
from src.ingest import get_all_senders, resolve_sender_id, split_sender_data

ARTIFACTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "artifacts")
PROFILES_FILE = os.path.join(ARTIFACTS_DIR, "profiles.json")
NULLS_FILE = os.path.join(ARTIFACTS_DIR, "nulls.json")

# Numeric feature keys for z-score calculations
NUMERIC_Z_KEYS = [
    ("punct_!", "rates_per_100w"),
    ("punct_?", "rates_per_100w"),
    ("punct_;", "rates_per_100w"),
    ("punct_:", "rates_per_100w"),
    ("punct_—", "rates_per_100w"),
    ("contraction_rate", "rates_per_100w"),
    ("formality_rate", "rates_per_100w"),
    ("sentence_len_mean", "sentence_len_mean"),
    ("sentence_len_std", "sentence_len_std"),
    ("avg_word_len", "avg_word_len"),
    ("ttr", "ttr"),
]


def extract_numeric_value(feat: Dict, key: str) -> float:
    """Extracts numeric feature value by flattened key."""
    if key.startswith("punct_"):
        p = key.split("_", 1)[1]
        return float(feat["punct_rates"].get(p, 0.0))
    return float(feat.get(key, 0.0))


def compute_robust_stat(values: List[float], floor_val: float) -> Tuple[float, float, float, float]:
    """
    Winsorizes values at 5/95 percentiles, then computes mean and floored sample std.
    Returns (mean, std, p5, p95).
    """
    arr = np.array(values, dtype=np.float64)
    if len(arr) == 0:
        return 0.0, floor_val, 0.0, 0.0
    if len(arr) == 1:
        return float(arr[0]), floor_val, float(arr[0]), float(arr[0])

    p5 = float(np.percentile(arr, 5))
    p95 = float(np.percentile(arr, 95))
    w_arr = np.clip(arr, p5, p95)
    mean_val = float(np.mean(w_arr))
    std_val = float(np.std(w_arr, ddof=1))
    std_val = max(std_val, floor_val)
    return mean_val, std_val, p5, p95


def build_profile_from_features(feature_list: List[Dict], sender_id: str) -> Dict:
    """
    Builds the complete Habit Ledger profile from precomputed feature dictionaries.
    """
    n = len(feature_list)
    if n == 0:
        raise ValueError(f"Cannot build profile for sender '{sender_id}' with 0 training emails.")

    # 1. Numeric Z-score features
    numeric_stats = {}
    for key, family in NUMERIC_Z_KEYS:
        vals = [extract_numeric_value(f, key) for f in feature_list]
        m, s, p5, p95 = compute_robust_stat(vals, EPS_FLOORS[family])
        numeric_stats[key] = {
            "mean": round(m, 4),
            "std": round(s, 4),
            "p5": round(p5, 4),
            "p95": round(p95, 4),
            "family": family,
            "floor": EPS_FLOORS[family],
        }

    # 2. Function word frequencies
    fw_stats = {}
    for fw in FUNCTION_WORDS:
        vals = [f["function_word_freqs"].get(fw, 0.0) for f in feature_list]
        m, s, p5, p95 = compute_robust_stat(vals, EPS_FLOORS["relative_freq"])
        fw_stats[fw] = {
            "mean": round(m, 6),
            "std": round(s, 6),
        }

    # 3. Char 3-gram frequencies
    cg_stats = {}
    for cg in TOP_CHAR_3GRAMS:
        vals = [f["char_3gram_freqs"].get(cg, 0.0) for f in feature_list]
        m, s, p5, p95 = compute_robust_stat(vals, EPS_FLOORS["relative_freq"])
        cg_stats[cg] = {
            "mean": round(m, 6),
            "std": round(s, 6),
        }

    # 4. Greeting & Sign-off habit frequencies
    greetings = collections.Counter(f["greeting"] for f in feature_list)
    signoffs = collections.Counter(f["signoff"] for f in feature_list)
    
    greeting_freqs = {k: round(v / n, 4) for k, v in greetings.items()}
    signoff_freqs = {k: round(v / n, 4) for k, v in signoffs.items()}

    # Dominant habit determination
    top_greet, top_greet_cnt = greetings.most_common(1)[0]
    top_sign, top_sign_cnt = signoffs.most_common(1)[0]

    return {
        "sender_id": sender_id,
        "n_train": n,
        "numeric_stats": numeric_stats,
        "function_words": fw_stats,
        "char_3grams": cg_stats,
        "greetings": greeting_freqs,
        "dominant_greeting": top_greet,
        "dominant_greeting_consistency": round(top_greet_cnt / n, 4),
        "signoffs": signoff_freqs,
        "dominant_signoff": top_sign,
        "dominant_signoff_consistency": round(top_sign_cnt / n, 4),
    }


def compute_raw_score(features: Dict, profile: Dict) -> Tuple[float, Dict]:
    """
    Computes deviation score S:
    S = 0.25*Delta(fw) + 0.25*Delta(cg) + 0.35*mean|z capped| + 0.15*habit_penalty
    Also returns diagnostic breakdown for explainability.
    """
    # 1. Delta Function Words (capped at 4.0)
    fw_deltas = []
    fw_profile = profile["function_words"]
    for fw in FUNCTION_WORDS:
        obs = features["function_word_freqs"].get(fw, 0.0)
        st = fw_profile[fw]
        z = abs(obs - st["mean"]) / st["std"]
        fw_deltas.append(min(z, 4.0))
    delta_fw = float(np.mean(fw_deltas))

    # 2. Delta Char 3-grams (capped at 4.0)
    cg_deltas = []
    cg_profile = profile["char_3grams"]
    for cg in TOP_CHAR_3GRAMS:
        obs = features["char_3gram_freqs"].get(cg, 0.0)
        st = cg_profile[cg]
        z = abs(obs - st["mean"]) / st["std"]
        cg_deltas.append(min(z, 4.0))
    delta_cg = float(np.mean(cg_deltas))

    # 3. Numeric Z-scores (capped at 4.0)
    z_scores = {}
    capped_z_abs = []
    for key, _ in NUMERIC_Z_KEYS:
        obs = extract_numeric_value(features, key)
        st = profile["numeric_stats"][key]
        raw_z = (obs - st["mean"]) / st["std"]
        is_capped = abs(raw_z) >= 4.0
        capped_z = max(-4.0, min(4.0, raw_z))
        z_scores[key] = {
            "obs": round(obs, 4),
            "mean": st["mean"],
            "std": st["std"],
            "z": round(raw_z, 2),
            "z_capped": round(capped_z, 2),
            "capped": is_capped,
        }
        capped_z_abs.append(abs(capped_z))
    mean_z_capped = float(np.mean(capped_z_abs))

    # 4. Habit penalty
    greeting_obs = features["greeting"]
    greet_freq = profile["greetings"].get(greeting_obs, 0.0)
    dom_greet_cons = profile["dominant_greeting_consistency"]
    dom_greet = profile["dominant_greeting"]
    
    # Breaking a consistent habit counts proportional to consistency
    greet_pen = 0.0
    broken_greet = None
    if greet_freq < 0.10 and dom_greet_cons >= 0.50 and greeting_obs != dom_greet:
        greet_pen = dom_greet_cons * (1.0 - greet_freq)
        broken_greet = f"Uses greeting '{greeting_obs}' (observed {int(greet_freq*100)}% in past mail; usually '{dom_greet}' {int(dom_greet_cons*100)}%)"

    signoff_obs = features["signoff"]
    sign_freq = profile["signoffs"].get(signoff_obs, 0.0)
    dom_sign_cons = profile["dominant_signoff_consistency"]
    dom_sign = profile["dominant_signoff"]

    sign_pen = 0.0
    broken_sign = None
    if sign_freq < 0.10 and dom_sign_cons >= 0.50 and signoff_obs != dom_sign:
        sign_pen = dom_sign_cons * (1.0 - sign_freq)
        broken_sign = f"Signs '{signoff_obs}' (observed {int(sign_freq*100)}% in past mail; usually '{dom_sign}' {int(dom_sign_cons*100)}%)"

    habit_penalty = greet_pen + sign_pen

    # Composite Score S
    raw_s = (
        0.25 * delta_fw
        + 0.25 * delta_cg
        + 0.35 * mean_z_capped
        + 0.15 * habit_penalty
    )

    breakdown = {
        "delta_fw": round(delta_fw, 4),
        "delta_cg": round(delta_cg, 4),
        "mean_z_capped": round(mean_z_capped, 4),
        "habit_penalty": round(habit_penalty, 4),
        "z_scores": z_scores,
        "broken_greeting": broken_greet,
        "broken_signoff": broken_sign,
    }
    return float(raw_s), breakdown


def build_loo_null(feature_list: List[Dict], sender_id: str) -> Tuple[List[float], float]:
    """
    Computes full leave-one-out (LOO) null scores across training emails.
    Returns (sorted_null_scores, p_min).
    """
    n = len(feature_list)
    if n <= 1:
        return [0.0], 1.0

    null_scores = []
    for i in range(n):
        # Leave out email i
        train_sub = feature_list[:i] + feature_list[i + 1:]
        sub_profile = build_profile_from_features(train_sub, sender_id)
        score_i, _ = compute_raw_score(feature_list[i], sub_profile)
        null_scores.append(round(score_i, 6))

    null_scores.sort()
    p_min = round(1.0 / (n + 1), 6)
    return null_scores, p_min


def build_all_profiles() -> Tuple[Dict, Dict]:
    """
    Builds Habit Ledgers and LOO nulls for all 15 senders.
    Saves to artifacts/profiles.json and artifacts/nulls.json.
    """
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    senders = get_all_senders()

    all_profiles = {}
    all_nulls = {}

    print(f"Building Habit Ledgers and LOO Nulls for {len(senders)} senders...")
    for s in senders:
        sid = s["sender_id"]
        train_emails, _ = split_sender_data(sid)
        n_train = len(train_emails)

        # Precompute feature vectors
        feat_vecs = [extract_features(e["body"]) for e in train_emails]

        # Full profile
        profile = build_profile_from_features(feat_vecs, sid)
        all_profiles[sid] = profile

        # Full leave-one-out null
        null_scores, p_min = build_loo_null(feat_vecs, sid)
        all_nulls[sid] = {
            "sender_id": sid,
            "n_train": n_train,
            "p_min": p_min,
            "null_scores": null_scores,
            "median_null": round(float(np.median(null_scores)), 4),
            "q95_null": round(float(np.percentile(null_scores, 95)), 4),
            "max_null": round(float(np.max(null_scores)), 4),
        }
        print(f"  [Profile] {sid:12s} (n={n_train:3d}): null median={all_nulls[sid]['median_null']:.3f}, p_min={p_min:.4f}")

    # Write profiles.json
    with open(PROFILES_FILE, "w", encoding="utf-8") as f:
        json.dump(all_profiles, f, indent=2, sort_keys=True)

    # Write nulls.json
    with open(NULLS_FILE, "w", encoding="utf-8") as f:
        json.dump(all_nulls, f, indent=2, sort_keys=True)

    print(f"\nSaved profiles to: {PROFILES_FILE}")
    print(f"Saved nulls to:    {NULLS_FILE}")
    return all_profiles, all_nulls


def load_profile(sender_id: str) -> Optional[Dict]:
    """Loads a sender profile from artifacts/profiles.json."""
    canon_id = resolve_sender_id(sender_id)
    if not canon_id:
        return None
    if not os.path.exists(PROFILES_FILE):
        build_all_profiles()
    with open(PROFILES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get(canon_id)


def load_null(sender_id: str) -> Optional[Dict]:
    """Loads a sender LOO null from artifacts/nulls.json."""
    canon_id = resolve_sender_id(sender_id)
    if not canon_id:
        return None
    if not os.path.exists(NULLS_FILE):
        build_all_profiles()
    with open(NULLS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get(canon_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build GhostPen sender profiles and null distributions.")
    parser.add_argument("--rebuild", action="store_true", help="Force rebuild profiles and nulls from data/prepared/")
    args = parser.parse_args()
    build_all_profiles()
