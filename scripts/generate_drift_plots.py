"""
scripts/generate_drift_plots.py
-------------------------------
Generates self-drift timeline visualizations (Patch P2 - A4):
1. artifacts/plots/drift_timeline.png
   Small multiples (10 panels, one per high-volume sender):
   LOO null scores of training emails against date, with rolling-MEDIAN line.
2. artifacts/plots/drift_timeline_demo.png
   Export of the demo sender's panel alone (Marcus Hale / Kevin Presto) for the PDF figure.

Caption (verbatim):
"his own mail drifting from his earlier self - the drift we report, made visible."

Pins metadata (SOURCE_DATE_EPOCH=0) for reproducibility.
"""

import datetime
import os
import sys

# Determinism contract: pin SOURCE_DATE_EPOCH for matplotlib exports
os.environ["SOURCE_DATE_EPOCH"] = "0"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.features import extract_features
from src.ingest import get_all_senders, split_sender_data
from src.profile import build_profile_from_features, compute_raw_score

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACTS_DIR = os.path.join(REPO_ROOT, "artifacts")
PLOTS_DIR = os.path.join(ARTIFACTS_DIR, "plots")
ROOT_PLOTS_DIR = os.path.join(REPO_ROOT, "plots")

CAPTION = "his own mail drifting from his earlier self - the drift we report, made visible."


def compute_sender_timeline(sender_id: str):
    """
    Extracts chronological training emails and calculates exact LOO null score for each.
    Returns DataFrame with columns ['date', 'loo_score', 'rolling_median'].
    """
    train_emails, _ = split_sender_data(sender_id)
    n = len(train_emails)
    if n == 0:
        return pd.DataFrame()

    feat_vecs = [extract_features(e["body"]) for e in train_emails]

    records = []
    for i in range(n):
        # Leave out email i
        train_sub = feat_vecs[:i] + feat_vecs[i + 1:]
        sub_prof = build_profile_from_features(train_sub, sender_id)
        score_i, _ = compute_raw_score(feat_vecs[i], sub_prof)

        # Parse date
        raw_date = train_emails[i].get("date", "")
        dt = pd.to_datetime(raw_date, utc=True)
        records.append({"date": dt, "loo_score": score_i})

    df = pd.DataFrame(records)
    df = df.sort_values("date").reset_index(drop=True)
    df["rolling_median"] = df["loo_score"].rolling(window=10, min_periods=3, center=True).median()
    return df


def generate_drift_plots():
    os.makedirs(PLOTS_DIR, exist_ok=True)
    os.makedirs(ROOT_PLOTS_DIR, exist_ok=True)

    all_senders = get_all_senders()
    high_senders = [s for s in all_senders if s["volume_class"] == "high"]

    print(f"Generating Self-Drift Timelines for {len(high_senders)} high-volume senders...")

    # Data collection
    timelines = {}
    for s in high_senders:
        sid = s["sender_id"]
        print(f"  Computing LOO timeline for {sid}...")
        df = compute_sender_timeline(sid)
        timelines[sid] = {
            "df": df,
            "display_name": s["display_name"],
            "alias": s.get("alias"),
        }

    # -------------------------------------------------------------
    # 1. Small Multiples Grid (10 panels: 5 rows x 2 cols)
    # -------------------------------------------------------------
    fig, axes = plt.subplots(5, 2, figsize=(14, 16), dpi=150, sharex=False, sharey=True)
    axes = axes.flatten()

    for idx, s in enumerate(high_senders):
        ax = axes[idx]
        sid = s["sender_id"]
        info = timelines[sid]
        df = info["df"]

        dname = s["display_name"]
        if s.get("alias"):
            dname += f" ({s['alias']})"

        if not df.empty:
            ax.scatter(
                df["date"],
                df["loo_score"],
                color="#6baed6",
                alpha=0.55,
                s=20,
                label="LOO Null Score",
                edgecolors="none",
            )
            ax.plot(
                df["date"],
                df["rolling_median"],
                color="#08519c",
                linewidth=2.2,
                label="Rolling Median (w=10)",
            )

        ax.set_title(dname, fontsize=10, fontweight="bold", pad=4)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=8)
        ax.grid(True, linestyle=":", alpha=0.5)
        ax.set_ylabel("Score S", fontsize=8)

        if idx == 0:
            ax.legend(loc="upper right", fontsize=8, framealpha=0.8)

    fig.suptitle(
        f"GhostPen Self-Drift Timeline (10 High-Volume Senders)\n\"{CAPTION}\"",
        fontsize=13,
        fontweight="bold",
        y=0.995,
    )
    plt.tight_layout(rect=[0, 0.02, 1, 0.98])

    out_all_artifacts = os.path.join(PLOTS_DIR, "drift_timeline.png")
    out_all_root = os.path.join(ROOT_PLOTS_DIR, "drift_timeline.png")

    fig.savefig(
        out_all_artifacts,
        metadata={"CreationTime": "2000-01-01T00:00:00Z", "Software": "GhostPen"},
    )
    fig.savefig(
        out_all_root,
        metadata={"CreationTime": "2000-01-01T00:00:00Z", "Software": "GhostPen"},
    )
    plt.close(fig)
    print(f"[OK] Saved small multiples plot to: {out_all_artifacts}")

    # -------------------------------------------------------------
    # 2. Demo Persona Standalone Figure (presto-k / Marcus Hale)
    # -------------------------------------------------------------
    demo_sid = "presto-k"
    demo_info = timelines[demo_sid]
    df_demo = demo_info["df"]

    fig_demo, ax_demo = plt.subplots(figsize=(8, 4.8), dpi=150)
    ax_demo.scatter(
        df_demo["date"],
        df_demo["loo_score"],
        color="#3182bd",
        alpha=0.6,
        s=35,
        label="Training Email LOO Null Score",
    )
    ax_demo.plot(
        df_demo["date"],
        df_demo["rolling_median"],
        color="#de2d26",
        linewidth=2.5,
        label="Rolling Median (window=10)",
    )

    ax_demo.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax_demo.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.setp(ax_demo.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=9)
    ax_demo.set_ylabel("Stylometric Deviation Score (S)", fontsize=10)
    ax_demo.set_xlabel("Email Date", fontsize=10)
    ax_demo.set_title(
        f"Marcus Hale (CFO) — Self-Drift Timeline\n\"{CAPTION}\"",
        fontsize=11,
        fontweight="bold",
    )
    ax_demo.grid(True, linestyle=":", alpha=0.6)
    ax_demo.legend(loc="upper right", fontsize=9, framealpha=0.9)
    plt.tight_layout()

    out_demo_artifacts = os.path.join(PLOTS_DIR, "drift_timeline_demo.png")
    out_demo_root = os.path.join(ROOT_PLOTS_DIR, "drift_timeline_demo.png")

    fig_demo.savefig(
        out_demo_artifacts,
        metadata={"CreationTime": "2000-01-01T00:00:00Z", "Software": "GhostPen"},
    )
    fig_demo.savefig(
        out_demo_root,
        metadata={"CreationTime": "2000-01-01T00:00:00Z", "Software": "GhostPen"},
    )
    plt.close(fig_demo)
    print(f"[OK] Saved demo persona plot to:    {out_demo_artifacts}")


if __name__ == "__main__":
    generate_drift_plots()
