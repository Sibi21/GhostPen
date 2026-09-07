"""
src/baselines.py
----------------
Benchmark baselines evaluated against GhostPen on identical splits, holdouts, and tiers:
A. Centroid-Cosine TF-IDF:
   - IDF fit on pooled TRAINING mail only (strict anti-leakage).
   - Sender centroid computed from training mail.
   - Distance = 1.0 - cosine_similarity(email, centroid).
   - Threshold tuned on train-only 80/20 inner slice to target FPR = alpha (0.05).
B. Global Threshold:
   - GhostPen's raw score S with ONE pooled global threshold (alpha-quantile across all senders)
     instead of per-sender nulls — isolates the value of per-sender conformal calibration.

Fairness Guarantee:
Both baselines share the SAME method-agnostic routing layer:
Short messages (<40 words or <3 sentences) are TRIAGE with identical content_escalation rules.
"""

from typing import Dict, List, Optional, Tuple
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.features import extract_features
from src.ingest import get_all_senders, split_sender_data
from src.profile import compute_raw_score, load_profile
from src.score import extract_context_flags


class BaselineCentroidCosine:
    """Baseline A: Per-sender TF-IDF centroid with cosine distance."""

    def __init__(self, alpha: float = 0.05):
        self.alpha = alpha
        self.vectorizer = TfidfVectorizer(max_features=500, stop_words="english", sublinear_tf=True)
        self.centroids = {}
        self.threshold = 0.5

    def fit(self, senders: List[Dict]):
        # 1. Pool all training emails to fit IDF
        pooled_train_texts = []
        sender_train_slices = {}

        for s in senders:
            sid = s["sender_id"]
            train_emails, _ = split_sender_data(sid)
            # 80/20 inner chronological split for tuning
            n_inner = int(len(train_emails) * 0.8)
            inner_train = train_emails[:n_inner]
            inner_val = train_emails[n_inner:]

            sender_train_slices[sid] = (inner_train, inner_val)
            for e in train_emails:
                pooled_train_texts.append(e["body"])

        # Fit IDF strictly on pooled training mail
        self.vectorizer.fit(pooled_train_texts)

        # 2. Compute per-sender centroids from inner_train
        inner_val_distances = []
        for sid, (inner_train, inner_val) in sender_train_slices.items():
            if not inner_train:
                continue
            train_mat = self.vectorizer.transform([e["body"] for e in inner_train])
            centroid = np.asarray(train_mat.mean(axis=0))
            # Normalize centroid
            norm = np.linalg.norm(centroid)
            if norm > 0:
                centroid = centroid / norm
            self.centroids[sid] = centroid

            # Compute distances on inner_val for threshold tuning
            if inner_val:
                val_mat = self.vectorizer.transform([e["body"] for e in inner_val])
                sims = cosine_similarity(val_mat, centroid.reshape(1, -1)).flatten()
                for sim in sims:
                    inner_val_distances.append(1.0 - float(sim))

        # Tune threshold on inner_val to achieve target FPR = alpha
        if inner_val_distances:
            target_quantile = 100.0 * (1.0 - self.alpha)
            self.threshold = float(np.percentile(inner_val_distances, target_quantile))
        else:
            self.threshold = 0.85

    def score_email(self, text: str, sender_id: str) -> Dict:
        """Evaluates message with Baseline A + shared routing layer."""
        features = extract_features(text)
        context_flags = extract_context_flags(text)
        wc = features["word_count"]
        sc = features["sentence_count"]

        # Shared method-agnostic routing rule
        if wc < 40 or sc < 3:
            is_escalated = len(context_flags) >= 2
            return {
                "score": 0.0,
                "is_alert": False,
                "verdict": "TRIAGE",
                "content_escalation": is_escalated,
                "flagged": is_escalated,
            }

        centroid = self.centroids.get(sender_id)
        if centroid is None:
            return {
                "score": 1.0,
                "is_alert": False,
                "verdict": "UNENROLLED",
                "content_escalation": False,
                "flagged": False,
            }

        vec = self.vectorizer.transform([text])
        sim = float(cosine_similarity(vec, centroid.reshape(1, -1))[0, 0])
        dist = 1.0 - sim
        is_alert = dist > self.threshold

        return {
            "score": round(dist, 4),
            "threshold": round(self.threshold, 4),
            "is_alert": is_alert,
            "verdict": "ALERT" if is_alert else "OK",
            "content_escalation": False,
            "flagged": is_alert,
        }


class BaselineGlobalThreshold:
    """Baseline B: GhostPen raw score S with ONE pooled global threshold."""

    def __init__(self, alpha: float = 0.05):
        self.alpha = alpha
        self.threshold = 1.0

    def fit(self, senders: List[Dict]):
        # Collect raw S scores on inner_val to tune one global threshold
        inner_val_scores = []
        for s in senders:
            sid = s["sender_id"]
            train_emails, _ = split_sender_data(sid)
            n_inner = int(len(train_emails) * 0.8)
            inner_train = train_emails[:n_inner]
            inner_val = train_emails[n_inner:]

            if not inner_train:
                continue
            profile = load_profile(sid)
            for e in inner_val:
                f = extract_features(e["body"])
                raw_s, _ = compute_raw_score(f, profile)
                inner_val_scores.append(raw_s)

        if inner_val_scores:
            target_quantile = 100.0 * (1.0 - self.alpha)
            self.threshold = float(np.percentile(inner_val_scores, target_quantile))
        else:
            self.threshold = 0.75

    def score_email(self, text: str, sender_id: str) -> Dict:
        """Evaluates message with Baseline B + shared routing layer."""
        features = extract_features(text)
        context_flags = extract_context_flags(text)
        wc = features["word_count"]
        sc = features["sentence_count"]

        # Shared method-agnostic routing rule
        if wc < 40 or sc < 3:
            is_escalated = len(context_flags) >= 2
            return {
                "score": 0.0,
                "is_alert": False,
                "verdict": "TRIAGE",
                "content_escalation": is_escalated,
                "flagged": is_escalated,
            }

        profile = load_profile(sender_id)
        if not profile:
            return {
                "score": 0.0,
                "is_alert": False,
                "verdict": "UNENROLLED",
                "content_escalation": False,
                "flagged": False,
            }

        raw_s, _ = compute_raw_score(features, profile)
        is_alert = raw_s > self.threshold

        return {
            "score": round(raw_s, 4),
            "threshold": round(self.threshold, 4),
            "is_alert": is_alert,
            "verdict": "ALERT" if is_alert else "OK",
            "content_escalation": False,
            "flagged": is_alert,
        }
