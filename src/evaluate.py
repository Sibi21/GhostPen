"""
src/evaluate.py
---------------
Complete benchmark evaluation harness for GhostPen and comparison baselines.
Generates:
1. artifacts/metrics.json
   - Stated verbatim: flagged = ALERT OR (TRIAGE AND content_escalation); caught = flagged.
   - Dual FPR variants: FPR_alert (calibration claim) and FPR_flagged (operational false alarms)
   - Recall across all 4 forged tiers (alert-only and flagged)
   - Tier C copy-audit reporting (with and without copy_based attacks)
   - Bayesian precision at pi in {1%, 10%}
   - Routing layer costs on genuine holdout
   - Baseline comparison table (GhostPen, Baseline A Centroid, Baseline B Global Threshold)
   - Per-sender breakdown with worst-sender highlighted
2. artifacts/fp_autopsy.json (top-5 flagged genuine holdout emails + drift notes)
3. artifacts/plots/calibration.png (labeled sanity vs evidence calibration curves)
"""

import collections
import json
import math
import os
import sys

# Determinism contract: pin SOURCE_DATE_EPOCH for matplotlib exports
os.environ["SOURCE_DATE_EPOCH"] = "0"

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from src.baselines import BaselineCentroidCosine, BaselineGlobalThreshold
from src.features import extract_features
from src.ingest import get_all_senders, resolve_sender_id, split_sender_data
from src.profile import load_profile
from src.score import score_message
from src.attribution import compute_attribution

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACTS_DIR = os.path.join(REPO_ROOT, "artifacts")
PLOTS_DIR = os.path.join(ARTIFACTS_DIR, "plots")
METRICS_FILE = os.path.join(ARTIFACTS_DIR, "metrics.json")
AUTOPSY_FILE = os.path.join(ARTIFACTS_DIR, "fp_autopsy.json")
CALIBRATION_PLOT_FILE = os.path.join(PLOTS_DIR, "calibration.png")
DATA_DIR = os.path.join(REPO_ROOT, "data")
FORGED_FILE = os.path.join(DATA_DIR, "forged", "forged.jsonl")
DEMO_INBOX_FILE = os.path.join(DATA_DIR, "demo_inbox.json")

DETECTION_DEFINITION_VERBATIM = (
    "flagged = ALERT OR (TRIAGE AND content_escalation); caught = flagged."
)

CLAIM_DISCIPLINE_VERBATIM = (
    "the in-sample calibration line is an IMPLEMENTATION SANITY CHECK — the plug-in p-value is "
    "approximately rank-uniform for ANY exchangeable score function, so it verifies arithmetic, "
    "not the model. The HOLDOUT line is the evidence; holdout FPR − in-sample FPR = measured style drift, "
    "reported as a finding. Never claim 'holdout FPR = alpha by construction.' "
    "LOO nulls are built on n−1-email profiles, which inflates them slightly relative to a new message scored "
    "against the full n-email profile, so deployment p-values are mildly conservative (FPR <= alpha)."
)

ALPHA_GRID = [0.02, 0.05, 0.10]


def safe_rate(num, denom):
    return round(num / max(denom, 1), 4)


def evaluate_system():
    os.makedirs(PLOTS_DIR, exist_ok=True)
    all_senders = get_all_senders()
    high_senders = [s for s in all_senders if s["volume_class"] == "high"]

    # Load forged corpus
    forged_records = []
    if os.path.exists(FORGED_FILE):
        with open(FORGED_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    forged_records.append(json.loads(line))
    else:
        print(f"Warning: {FORGED_FILE} not found. Run src.forge first.", file=sys.stderr)

    # -------------------------------------------------------------
    # 1. Evaluate Calibration (In-sample Sanity vs Holdout Evidence)
    # -------------------------------------------------------------
    print("Evaluating calibration curves across alpha grid...")
    calibration_data = {alpha: {"in_sample_alerts": 0, "in_sample_total": 0, "holdout_alerts": 0, "holdout_flagged": 0, "holdout_total": 0} for alpha in ALPHA_GRID}
    
    # Store holdout emails for FP autopsy
    all_holdout_scored = []

    # Escalation routing diagnostics
    routing_stats = {
        "too_short_escalated": 0,
        "too_short_total": 0,
        "thin_history_escalated": 0,
        "thin_history_total": 0,
        "holdout_len_40_60_flagged": 0,
        "holdout_len_40_60_total": 0,
        "holdout_len_60plus_flagged": 0,
        "holdout_len_60plus_total": 0,
    }

    per_sender_eval = {}
    per_sender_abstain = {}

    for s in all_senders:
        sid = s["sender_id"]
        train_emails, holdout_emails = split_sender_data(sid)
        n_train = len(train_emails)

        sender_entry = {
            "sender_id": sid,
            "volume_class": s["volume_class"],
            "n_train": n_train,
            "holdout_count": len(holdout_emails),
            "alphas": {},
        }

        s_too_short = 0
        s_thin = 0

        # Evaluate across alphas
        for alpha in ALPHA_GRID:
            # A. In-sample alerts (Sanity line)
            in_alerts = 0
            for e in train_emails:
                res = score_message(e["body"], sid, alpha=alpha)
                if res["verdict"] == "ALERT":
                    in_alerts += 1
            calibration_data[alpha]["in_sample_alerts"] += in_alerts
            calibration_data[alpha]["in_sample_total"] += len(train_emails)

            # B. Holdout evaluation (Evidence line)
            h_alerts = 0
            h_flagged = 0
            for e in holdout_emails:
                res = score_message(e["body"], sid, alpha=alpha)
                is_alert = res["verdict"] == "ALERT"
                is_flagged = is_alert or (res["verdict"] == "TRIAGE" and res["content_escalation"])
                if is_alert:
                    h_alerts += 1
                if is_flagged:
                    h_flagged += 1

                # Collect at alpha=0.05 for autopsy
                if alpha == 0.05:
                    all_holdout_scored.append({
                        "sender_id": sid,
                        "word_count": res["word_count"],
                        "body": e["body"],
                        "res": res,
                    })

                    # Routing layer diagnostics
                    wc = res["word_count"]
                    sc = res["sentence_count"]
                    if wc < 40 or sc < 3:
                        routing_stats["too_short_total"] += 1
                        s_too_short += 1
                        if res["content_escalation"]:
                            routing_stats["too_short_escalated"] += 1
                    elif n_train < int(math.floor(1.0 / alpha)):
                        routing_stats["thin_history_total"] += 1
                        s_thin += 1
                        if res["content_escalation"]:
                            routing_stats["thin_history_escalated"] += 1

                    if 40 <= wc <= 60:
                        routing_stats["holdout_len_40_60_total"] += 1
                        if is_flagged:
                            routing_stats["holdout_len_40_60_flagged"] += 1
                    elif wc > 60:
                        routing_stats["holdout_len_60plus_total"] += 1
                        if is_flagged:
                            routing_stats["holdout_len_60plus_flagged"] += 1

            n_h = max(len(holdout_emails), 1)
            fpr_alert_s = round(h_alerts / n_h, 4)
            fpr_flagged_s = round(h_flagged / n_h, 4)

            calibration_data[alpha]["holdout_alerts"] += h_alerts
            calibration_data[alpha]["holdout_flagged"] += h_flagged
            calibration_data[alpha]["holdout_total"] += len(holdout_emails)

            sender_entry["alphas"][str(alpha)] = {
                "FPR_alert": fpr_alert_s,
                "FPR_flagged": fpr_flagged_s,
            }

        per_sender_eval[sid] = sender_entry
        n_holdout = max(len(holdout_emails), 1)
        per_sender_abstain[sid] = {
            "abstain_rate": safe_rate(s_too_short, n_holdout),
            "insufficient_history": safe_rate(s_thin, n_holdout),
            "insufficient_history_count": s_thin,
            "split_by_triage_reason": {
                "insufficient_history": {
                    "count": s_thin,
                    "rate": safe_rate(s_thin, n_holdout),
                },
                "too_short": {
                    "count": s_too_short,
                    "rate": safe_rate(s_too_short, n_holdout),
                },
            },
            "too_short": safe_rate(s_too_short, n_holdout),
            "too_short_count": s_too_short,
            "total_holdout": len(holdout_emails),
            "triage_count": s_too_short + s_thin,
            "triage_rate": safe_rate(s_too_short + s_thin, n_holdout),
        }

    # -------------------------------------------------------------
    # 2. Evaluate Forged Recall (Flagged & Alert-Only across Tiers)
    # -------------------------------------------------------------
    print("Evaluating forged tiers and copy-audit...")
    forged_eval = {
        "relabel": {"total": 0, "alert": 0, "flagged": 0},
        "generic": {"total": 0, "alert": 0, "flagged": 0},
        "styled_all": {"total": 0, "alert": 0, "flagged": 0},
        "styled_clean_only": {"total": 0, "alert": 0, "flagged": 0},
        "short": {"total": 0, "alert": 0, "flagged": 0},
    }

    styled_copy_audit_records = []

    # Ground-truth mapping for relabel true authors
    sender_bodies = {}
    for s in all_senders:
        _, holdout = split_sender_data(s["sender_id"])
        for e in holdout:
            sender_bodies[e["body"]] = s["sender_id"]

    relabel_top1_count = 0
    generic_no_match_count = 0
    styled_no_match_count = 0

    for f_rec in forged_records:
        sid = f_rec["sender"]
        tier = f_rec["tier"]
        text = f_rec["text"]
        res = score_message(text, sid, alpha=0.05)
        
        is_alert = res["verdict"] == "ALERT"
        is_flagged = is_alert or (res["verdict"] == "TRIAGE" and res["content_escalation"])

        if tier == "relabel":
            forged_eval["relabel"]["total"] += 1
            if is_alert:
                forged_eval["relabel"]["alert"] += 1
            if is_flagged:
                forged_eval["relabel"]["flagged"] += 1

            # A1 Attribution check
            att = compute_attribution(text, sid, alpha=0.05)
            true_author = sender_bodies.get(text)
            if not att["is_no_match"] and att["top_3"] and att["top_3"][0]["sender_id"] == true_author:
                relabel_top1_count += 1

        elif tier == "generic":
            forged_eval["generic"]["total"] += 1
            if is_alert:
                forged_eval["generic"]["alert"] += 1
            if is_flagged:
                forged_eval["generic"]["flagged"] += 1

            # A1 Attribution check
            att = compute_attribution(text, sid, alpha=0.05)
            if att["is_no_match"]:
                generic_no_match_count += 1

        elif tier == "styled":
            forged_eval["styled_all"]["total"] += 1
            if is_alert:
                forged_eval["styled_all"]["alert"] += 1
            if is_flagged:
                forged_eval["styled_all"]["flagged"] += 1

            # A1 Attribution check
            att = compute_attribution(text, sid, alpha=0.05)
            if att["is_no_match"]:
                styled_no_match_count += 1

            is_copy = f_rec.get("copy_based", False)
            styled_copy_audit_records.append({
                "sender": sid,
                "copy_based": is_copy,
                "shared_5grams_count": f_rec.get("shared_5grams_count", 0),
                "max_lcs_len": f_rec.get("max_lcs_len", 0),
                "is_alert": is_alert,
                "is_flagged": is_flagged,
            })

            if not is_copy:
                forged_eval["styled_clean_only"]["total"] += 1
                if is_alert:
                    forged_eval["styled_clean_only"]["alert"] += 1
                if is_flagged:
                    forged_eval["styled_clean_only"]["flagged"] += 1

        elif tier == "short":
            forged_eval["short"]["total"] += 1
            if is_alert:
                forged_eval["short"]["alert"] += 1
            if is_flagged:
                forged_eval["short"]["flagged"] += 1

    # Calculate recall percentages
    recall_metrics = {
        "relabel": {
            "recall_flagged": safe_rate(forged_eval["relabel"]["flagged"], forged_eval["relabel"]["total"]),
            "recall_alert_only": safe_rate(forged_eval["relabel"]["alert"], forged_eval["relabel"]["total"]),
            "total": forged_eval["relabel"]["total"],
        },
        "generic": {
            "recall_flagged": safe_rate(forged_eval["generic"]["flagged"], forged_eval["generic"]["total"]),
            "recall_alert_only": safe_rate(forged_eval["generic"]["alert"], forged_eval["generic"]["total"]),
            "total": forged_eval["generic"]["total"],
        },
        "styled_all": {
            "recall_flagged": safe_rate(forged_eval["styled_all"]["flagged"], forged_eval["styled_all"]["total"]),
            "recall_alert_only": safe_rate(forged_eval["styled_all"]["alert"], forged_eval["styled_all"]["total"]),
            "total": forged_eval["styled_all"]["total"],
        },
        "styled_excluding_copy_based": {
            "recall_flagged": safe_rate(forged_eval["styled_clean_only"]["flagged"], forged_eval["styled_clean_only"]["total"]),
            "recall_alert_only": safe_rate(forged_eval["styled_clean_only"]["alert"], forged_eval["styled_clean_only"]["total"]),
            "total": forged_eval["styled_clean_only"]["total"],
        },
        "short_evasion": {
            "recall_flagged": safe_rate(forged_eval["short"]["flagged"], forged_eval["short"]["total"]),
            "recall_alert_only": safe_rate(forged_eval["short"]["alert"], forged_eval["short"]["total"]),
            "total": forged_eval["short"]["total"],
        },
    }

    # -------------------------------------------------------------
    # 3. Baselines Evaluation (Fit on Training Mail, Tested on Holdouts)
    # -------------------------------------------------------------
    print("Fitting and evaluating baselines A and B...")
    base_a = BaselineCentroidCosine(alpha=0.05)
    base_a.fit(all_senders)

    base_b = BaselineGlobalThreshold(alpha=0.05)
    base_b.fit(all_senders)

    # Evaluate Baselines on Holdouts & Forgeries
    def eval_baseline(model, name):
        h_alerts = 0
        h_flagged = 0
        h_total = 0
        for s in all_senders:
            sid = s["sender_id"]
            _, holdouts = split_sender_data(sid)
            for e in holdouts:
                res = model.score_email(e["body"], sid)
                h_total += 1
                if res["is_alert"]:
                    h_alerts += 1
                if res["flagged"]:
                    h_flagged += 1

        # Forged recall
        f_relabel_flag = sum(1 for r in forged_records if r["tier"] == "relabel" and model.score_email(r["text"], r["sender"])["flagged"])
        f_generic_flag = sum(1 for r in forged_records if r["tier"] == "generic" and model.score_email(r["text"], r["sender"])["flagged"])
        f_styled_flag = sum(1 for r in forged_records if r["tier"] == "styled" and model.score_email(r["text"], r["sender"])["flagged"])
        f_short_flag = sum(1 for r in forged_records if r["tier"] == "short" and model.score_email(r["text"], r["sender"])["flagged"])

        f_total_flag = f_relabel_flag + f_generic_flag + f_styled_flag + f_short_flag
        total_forged = max(len(forged_records), 1)
        r_pooled = f_total_flag / total_forged

        fpr_flag = h_flagged / max(h_total, 1)
        # Bayes precision at 1% and 10%
        p1 = (r_pooled * 0.01) / ((r_pooled * 0.01) + (fpr_flag * 0.99)) if (r_pooled * 0.01 + fpr_flag * 0.99) > 0 else 0.0
        p10 = (r_pooled * 0.10) / ((r_pooled * 0.10) + (fpr_flag * 0.90)) if (r_pooled * 0.10 + fpr_flag * 0.90) > 0 else 0.0

        return {
            "model": name,
            "FPR_alert_holdout": round(h_alerts / max(h_total, 1), 4),
            "FPR_flagged_holdout": round(fpr_flag, 4),
            "recall_relabel_flagged": safe_rate(f_relabel_flag, forged_eval["relabel"]["total"]),
            "recall_generic_flagged": safe_rate(f_generic_flag, forged_eval["generic"]["total"]),
            "recall_styled_flagged": safe_rate(f_styled_flag, forged_eval["styled_all"]["total"]),
            "recall_short_flagged": safe_rate(f_short_flag, forged_eval["short"]["total"]),
            "precision_at_1pct": round(p1, 4),
            "precision_at_10pct": round(p10, 4),
        }

    eval_base_a = eval_baseline(base_a, "Baseline A (Centroid Cosine TF-IDF)")
    eval_base_b = eval_baseline(base_b, "Baseline B (Global Threshold on S)")

    # GhostPen baseline row
    h_total = calibration_data[0.05]["holdout_total"]
    gp_fpr_alert = safe_rate(calibration_data[0.05]["holdout_alerts"], h_total)
    gp_fpr_flag = safe_rate(calibration_data[0.05]["holdout_flagged"], h_total)
    
    # GhostPen pooled flagged recall
    gp_flagged_total = (
        forged_eval["relabel"]["flagged"]
        + forged_eval["generic"]["flagged"]
        + forged_eval["styled_all"]["flagged"]
        + forged_eval["short"]["flagged"]
    )
    gp_r_pooled = gp_flagged_total / max(len(forged_records), 1)

    gp_p1 = (gp_r_pooled * 0.01) / ((gp_r_pooled * 0.01) + (gp_fpr_flag * 0.99)) if (gp_r_pooled * 0.01 + gp_fpr_flag * 0.99) > 0 else 0.0
    gp_p10 = (gp_r_pooled * 0.10) / ((gp_r_pooled * 0.10) + (gp_fpr_flag * 0.90)) if (gp_r_pooled * 0.10 + gp_fpr_flag * 0.90) > 0 else 0.0

    eval_ghostpen = {
        "model": "GhostPen (Per-Sender LOO Null)",
        "FPR_alert_holdout": gp_fpr_alert,
        "FPR_flagged_holdout": gp_fpr_flag,
        "recall_relabel_flagged": recall_metrics["relabel"]["recall_flagged"],
        "recall_generic_flagged": recall_metrics["generic"]["recall_flagged"],
        "recall_styled_flagged": recall_metrics["styled_all"]["recall_flagged"],
        "recall_short_flagged": recall_metrics["short_evasion"]["recall_flagged"],
        "precision_at_1pct": round(gp_p1, 4),
        "precision_at_10pct": round(gp_p10, 4),
    }

    baseline_table = [eval_ghostpen, eval_base_a, eval_base_b]

    # -------------------------------------------------------------
    # 4. Calibration Curve Plotting (Pinned Metadata)
    # -------------------------------------------------------------
    print("Generating deterministic calibration plot...")
    plt.figure(figsize=(6.5, 5.5), dpi=150)
    plt.plot([0, 0.12], [0, 0.12], "k--", label="Ideal Diagonal (y=x)", alpha=0.7)

    x_alphas = ALPHA_GRID
    y_insample = [safe_rate(calibration_data[a]["in_sample_alerts"], calibration_data[a]["in_sample_total"]) for a in ALPHA_GRID]
    y_holdout = [safe_rate(calibration_data[a]["holdout_alerts"], calibration_data[a]["holdout_total"]) for a in ALPHA_GRID]

    plt.plot(x_alphas, y_insample, "s-", color="#1f77b4", label="sanity (in-sample)", linewidth=2)
    plt.plot(x_alphas, y_holdout, "o-", color="#d62728", label="evidence (holdout)", linewidth=2)

    plt.xlabel("Significance Level Alpha (Operating Threshold)", fontsize=11)
    plt.ylabel("Observed False Alert Rate (FPR_alert)", fontsize=11)
    plt.title("GhostPen Conformal Calibration: Sanity vs. Holdout Evidence", fontsize=12, fontweight="bold")
    plt.grid(True, linestyle=":", alpha=0.6)
    plt.xlim([0.01, 0.11])
    plt.ylim([0.0, 0.15])
    plt.legend(loc="upper left", frameon=True)
    plt.tight_layout()

    # Save with metadata pinned and SOURCE_DATE_EPOCH=0
    plt.savefig(
        CALIBRATION_PLOT_FILE,
        metadata={"CreationTime": "2000-01-01T00:00:00Z", "Software": "GhostPen"},
    )
    plt.close()

    # -------------------------------------------------------------
    # 5. False Positive Autopsy (artifacts/fp_autopsy.json)
    # -------------------------------------------------------------
    print("Compiling False Positive Autopsy for genuine holdout mail...")
    # Find flagged genuine holdout emails
    flagged_genuine = [
        item for item in all_holdout_scored
        if item["res"]["verdict"] == "ALERT" or (item["res"]["verdict"] == "TRIAGE" and item["res"]["content_escalation"])
    ]

    # Sort by deviation score S descending
    flagged_genuine.sort(key=lambda x: x["res"]["deviation_score"], reverse=True)

    autopsy_records = []
    for item in flagged_genuine[:5]:
        res = item["res"]
        sid = item["sender_id"]
        # Generate informative drift diagnosis
        drift_reasons = []
        if res["verdict"] == "TRIAGE" and res["content_escalation"]:
            drift_reasons.append("Short message containing payment/urgency keywords triggered secondary content escalation")
        if res["broken_habits"]:
            drift_reasons.append(f"Broken habitual pattern: {res['broken_habits'][0]}")
        if res["direction"] != "Style variation within normal baseline":
            drift_reasons.append(f"Stylometric shift: {res['direction']}")
        if not drift_reasons:
            drift_reasons.append("Unusual phrasing density in holdout message relative to historical training corpus")

        autopsy_records.append({
            "sender_id": sid,
            "word_count": item["word_count"],
            "deviation_score": res["deviation_score"],
            "p_value": res["p"],
            "verdict": res["verdict"],
            "broken_habits": res["broken_habits"],
            "direction": res["direction"],
            "context_flags": res["context_flags"],
            "drift_note": "; ".join(drift_reasons),
            "snippet": item["body"][:160].replace("\n", " ") + "...",
        })

    with open(AUTOPSY_FILE, "w", encoding="utf-8") as f:
        json.dump(autopsy_records, f, indent=2)

    # -------------------------------------------------------------
    # 6. Assemble Full artifacts/metrics.json
    # -------------------------------------------------------------
    worst_sender_id = max(
        per_sender_eval.keys(),
        key=lambda k: per_sender_eval[k]["alphas"]["0.05"]["FPR_alert"],
    )

    # Canonical demo inbox abstain rate
    demo_inbox_file = os.path.join(REPO_ROOT, "data", "demo_inbox.json")
    demo_triage_count = 0
    demo_msgs_count = 0
    if os.path.exists(demo_inbox_file):
        with open(demo_inbox_file, "r", encoding="utf-8") as f:
            demo_msgs = json.load(f)
        demo_msgs_count = len(demo_msgs)
        for dm in demo_msgs:
            d_res = score_message(dm["body"], "presto-k", alpha=0.05)
            if d_res["verdict"] == "TRIAGE":
                demo_triage_count += 1
    abstain_rate_demo = safe_rate(demo_triage_count, demo_msgs_count)

    abstain_rate_pooled = safe_rate(
        routing_stats["too_short_total"],
        calibration_data[0.05]["holdout_total"],
    )

    metrics_payload = {
        "abstain_rate_demo_inbox": abstain_rate_demo,
        "abstain_rate_genuine_holdout_per_sender": per_sender_abstain,
        "abstain_rate_genuine_holdout_pooled": abstain_rate_pooled,
        "attribution_no_match_rate_generic": safe_rate(generic_no_match_count, forged_eval["generic"]["total"]),
        "attribution_no_match_rate_styled": safe_rate(styled_no_match_count, forged_eval["styled_all"]["total"]),
        "attribution_top1_accuracy_relabel": safe_rate(relabel_top1_count, forged_eval["relabel"]["total"]),
        "detection_definition": DETECTION_DEFINITION_VERBATIM,
        "claim_discipline": CLAIM_DISCIPLINE_VERBATIM,
        "evaluation_summary": {
            "total_senders": len(all_senders),
            "high_volume_senders": len(high_senders),
            "total_training_emails": calibration_data[0.05]["in_sample_total"],
            "total_holdout_emails": calibration_data[0.05]["holdout_total"],
            "total_forged_evaluation_records": len(forged_records),
        },
        "fpr_variants": {
            str(alpha): {
                "alpha": alpha,
                "FPR_alert": safe_rate(calibration_data[alpha]["holdout_alerts"], calibration_data[alpha]["holdout_total"]),
                "FPR_flagged": safe_rate(calibration_data[alpha]["holdout_flagged"], calibration_data[alpha]["holdout_total"]),
                "FPR_sanity_in_sample": safe_rate(calibration_data[alpha]["in_sample_alerts"], calibration_data[alpha]["in_sample_total"]),
                "measured_style_drift": round(
                    safe_rate(calibration_data[alpha]["holdout_alerts"], calibration_data[alpha]["holdout_total"])
                    - safe_rate(calibration_data[alpha]["in_sample_alerts"], calibration_data[alpha]["in_sample_total"]),
                    4,
                ),
            }
            for alpha in ALPHA_GRID
        },
        "recall_by_tier": recall_metrics,
        "bayesian_precision": {
            "description": "Calculated using flagged rule on both sides: Precision(pi) = R_flagged*pi / (R_flagged*pi + FPR_flagged*(1-pi))",
            "pooling_choice": "Pooled across all 4 forged tiers (relabel, generic, styled, short)",
            "R_flagged_pooled": round(gp_r_pooled, 4),
            "FPR_flagged_at_005": gp_fpr_flag,
            "precision_at_1pct_prevalence": round(gp_p1, 4),
            "precision_at_10pct_prevalence": round(gp_p10, 4),
            "flags_per_100_genuine_emails": round(gp_fpr_flag * 100.0, 2),
        },
        "routing_layer_cost": {
            "total_holdout_emails": calibration_data[0.05]["holdout_total"],
            "genuine_holdout_escalation_rate": safe_rate(calibration_data[0.05]["holdout_flagged"] - calibration_data[0.05]["holdout_alerts"], calibration_data[0.05]["holdout_total"]),
            "split_by_triage_reason": {
                "too_short": {
                    "total_messages": routing_stats["too_short_total"],
                    "escalated": routing_stats["too_short_escalated"],
                    "escalation_rate": safe_rate(routing_stats["too_short_escalated"], routing_stats["too_short_total"]),
                },
                "insufficient_history": {
                    "total_messages": routing_stats["thin_history_total"],
                    "escalated": routing_stats["thin_history_escalated"],
                    "escalation_rate": safe_rate(routing_stats["thin_history_escalated"], routing_stats["thin_history_total"]),
                },
            },
            "holdout_fpr_by_length_bucket": {
                "40_to_60_words": {
                    "total": routing_stats["holdout_len_40_60_total"],
                    "flagged": routing_stats["holdout_len_40_60_flagged"],
                    "FPR_flagged": safe_rate(routing_stats["holdout_len_40_60_flagged"], routing_stats["holdout_len_40_60_total"]),
                },
                "60_plus_words": {
                    "total": routing_stats["holdout_len_60plus_total"],
                    "flagged": routing_stats["holdout_len_60plus_flagged"],
                    "FPR_flagged": safe_rate(routing_stats["holdout_len_60plus_flagged"], routing_stats["holdout_len_60plus_total"]),
                },
            },
        },
        "worst_sender": {
            "sender_id": worst_sender_id,
            "highlight": "Highest individual FPR_alert rate; pooled averages conceal per-sender variance",
            "metrics": per_sender_eval[worst_sender_id],
        },
        "per_sender_breakdown": per_sender_eval,
        "baseline_comparison_table": baseline_table,
        "copy_audit_summary": {
            "total_styled": len(styled_copy_audit_records),
            "copy_based_count": sum(1 for a in styled_copy_audit_records if a["copy_based"]),
            "clean_imitation_count": sum(1 for a in styled_copy_audit_records if not a["copy_based"]),
            "per_record_audit": styled_copy_audit_records,
        },
    }

    with open(METRICS_FILE, "w", encoding="utf-8") as f:
        json.dump(metrics_payload, f, indent=2, sort_keys=True)

    print(f"\n[OK] Metrics persisted to:     {METRICS_FILE}")
    print(f"[OK] FP Autopsy persisted to:   {AUTOPSY_FILE}")
    print(f"[OK] Calibration plot saved to: {CALIBRATION_PLOT_FILE}")
    print("\nBenchmark Evaluation Complete!")


if __name__ == "__main__":
    evaluate_system()
