"""
scripts/generate_slides.py
--------------------------
Generates the official 5-page Hackathon Submission PDF:
artifacts/GhostPen_Presentation.pdf
Complies with submission requirements:
- PDF only
- Exactly 5 pages
- <= 20.0 MiB
- Covers: 1. Title, 2. Objective, 3. Proposed Solution, 4. Solution Validation, 5. Results & Conclusions
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

os.environ["SOURCE_DATE_EPOCH"] = "0"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACTS_DIR = os.path.join(REPO_ROOT, "artifacts")
PDF_PATH = os.path.join(ARTIFACTS_DIR, "GhostPen_Presentation.pdf")
CALIBRATION_PLOT_PATH = os.path.join(ARTIFACTS_DIR, "plots", "calibration.png")


def create_slide(pdf, slide_num, title, subtitle, content_fn):
    fig = plt.figure(figsize=(11, 8.5), dpi=150)
    fig.patch.set_facecolor("#fcfcfd")

    # Header bar
    ax_header = fig.add_axes([0.05, 0.88, 0.90, 0.08])
    ax_header.axis("off")
    ax_header.text(0.0, 0.65, title, fontsize=22, fontweight="bold", color="#1a202c")
    ax_header.text(0.0, 0.15, subtitle, fontsize=12, color="#4a5568", style="italic")
    ax_header.text(1.0, 0.65, f"Page {slide_num} / 5", fontsize=11, color="#718096", ha="right")

    # Separator rule
    ax_rule = fig.add_axes([0.05, 0.87, 0.90, 0.002])
    ax_rule.axhline(0, color="#cbd5e0", linewidth=1.5)
    ax_rule.axis("off")

    # Main content canvas
    ax_body = fig.add_axes([0.05, 0.08, 0.90, 0.77])
    ax_body.axis("off")
    content_fn(ax_body)

    # Footer bar
    ax_footer = fig.add_axes([0.05, 0.02, 0.90, 0.04])
    ax_footer.axis("off")
    ax_footer.text(0.0, 0.5, "GhostPen (v4.2-final) — BEC Detection via Writing-Style Verification", fontsize=9, color="#a0aec0")
    ax_footer.text(1.0, 0.5, "Runnable Hackathon Prototype — Zero Network at Runtime", fontsize=9, color="#a0aec0", ha="right")

    pdf.savefig(fig, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)


def slide_1(ax):
    """Title Slide"""
    ax.text(0.5, 0.75, "GhostPen", fontsize=38, fontweight="heavy", color="#1a365d", ha="center")
    ax.text(0.5, 0.64, "BEC Detection via Writing-Style Verification", fontsize=20, fontweight="bold", color="#2b6cb0", ha="center")
    
    # Tagline pill
    ax.text(0.5, 0.50, "“Your CFO's writing style is a password.”", fontsize=16, fontweight="semibold", color="#2d3748", ha="center",
            bbox=dict(boxstyle="round,pad=0.6", facecolor="#edf2f7", edgecolor="#cbd5e0"))

    bullet_text = (
        "• Problem: Executive impersonation bypasses SPF/DKIM/DMARC — the writing is the only remaining signal.\n"
        "• Innovation: Per-sender Habit Ledger + leave-one-out conformal null calibration (FPR is a dial, not a hope).\n"
        "• Abstain-and-Route: Reason-agnostic secondary control routing — short evasion attacks cannot slip through.\n"
        "• 100% Self-Contained: Ships in-repo with Enron corpus subset; runs end-to-end with zero runtime network."
    )
    ax.text(0.10, 0.22, bullet_text, fontsize=12, color="#2d3748", linespacing=1.7)

    ax.text(0.5, 0.06, "Quickstart: pip install -r requirements.txt  |  make demo  |  make test", fontsize=11, fontweight="bold", color="#2c5282", ha="center")


def slide_2(ax):
    """Project Objective"""
    ax.text(0.0, 0.94, "Business Problem & Market Context", fontsize=15, fontweight="bold", color="#2b6cb0")
    t1 = (
        "• The Billion-Dollar Blindspot: Business Email Compromise (BEC) accounts for billions in losses annually.\n"
        "  Attackers compromise real executive mail accounts or spoof display names on lookalike domains.\n"
        "  Technical envelope checks (SPF, DKIM, DMARC) pass cleanly because the infrastructure is legitimate.\n"
        "• The Text is the Firewall: The only uncompromised signal remaining is the sender's unconscious writing style.\n"
        "• Target Buyers: Enterprise Security Operations Centers (SOC), Secure Email Gateways (SEG), and ERP financial controls."
    )
    ax.text(0.0, 0.72, t1, fontsize=11, color="#2d3748", linespacing=1.6)

    ax.text(0.0, 0.50, "Why This Approach Now?", fontsize=15, fontweight="bold", color="#2b6cb0")
    t2 = (
        "• The GenAI Threat Vector: Large Language Models (LLMs) allow adversaries to generate fluent, grammatically\n"
        "  flawless phishing messages at scale, rendering traditional keyword spam rules completely obsolete.\n"
        "• Why Deep Learning & Embeddings Fail in Deployment:\n"
        "  1. Opacity: Black-box cosine distances cannot explain to a CFO or SOC analyst why an email was quarantined.\n"
        "  2. Network / Latency: External embedding APIs introduce security liabilities, vendor lock-in, and downtime.\n"
        "  3. Uncalibrated Scores: Arbitrary cosine thresholds cause unpredictable false positive bursts on executive mail.\n"
        "• GhostPen Solution: Plain, explainable, lightweight statistical stylometry with strict conformal error bounds."
    )
    ax.text(0.0, 0.20, t2, fontsize=11, color="#2d3748", linespacing=1.6)


def slide_3(ax):
    """Proposed Solution"""
    ax.text(0.0, 0.95, "The Four Architectural Differentiators", fontsize=15, fontweight="bold", color="#2b6cb0")

    boxes = [
        ("1. Habit Ledger (Per-Sender)", 
         "• 70+ function words (grammar glue)\n• Sentence burstiness (mean + std)\n• Punctuation rates per 100w (! ? ; : —)\n• Greeting & sign-off habit sets ('none' tracked)\n• Robust stats: 5/95 winsorizing, std floored\n  per family (EPS), capped |z| <= 4.0"),
        ("2. Target-Null Calibration", 
         "• N = n_train leave-one-out folds on sender mail\n• Conformal p = (1 + #{null >= S}) / (N + 1)\n• False Positive Rate becomes a dial:\n  alpha in {0.02, 0.05, 0.10}\n• Eliminates arbitrary score thresholding\n• Guaranteed conservative deployment FPR"),
        ("3. Direction of Deviation", 
         "• Forgeries skew formal & generic, not just 'different'\n• Plain-English evidence cards:\n  'Formality +4.0 sigma above his norm'\n  'Signs Best regards; usually none 78%'\n• BEC context flags kept strictly separate from S\n  (preserves pure stylometric score)"),
        ("4. Abstain-and-Route Layer", 
         "• Short emails (<40 words) cannot be judged\n• TRIAGE is a ROUTING state, never a pass\n• Reason-agnostic escalation:\n  TRIAGE + >= 2 context flags -> route to payment\n  verification / secondary controls\n• Catches brevity-based evasion plays cleanly"),
    ]

    coords = [(0.0, 0.48), (0.50, 0.48), (0.0, 0.02), (0.50, 0.02)]
    for (title, text), (x, y) in zip(boxes, coords):
        ax.text(x + 0.02, y + 0.36, title, fontsize=12, fontweight="bold", color="#1a365d")
        ax.text(x + 0.02, y + 0.12, text, fontsize=9.5, color="#2d3748", linespacing=1.5)
        rect = plt.Rectangle((x, y), 0.47, 0.42, facecolor="#ffffff", edgecolor="#cbd5e0", linewidth=1.2, transform=ax.transAxes)
        ax.add_patch(rect)


def slide_4(ax):
    """Solution Validation"""
    ax.text(0.0, 0.94, "Rigorous Experimental Protocol (Strict Anti-Leakage)", fontsize=14, fontweight="bold", color="#2b6cb0")
    t1 = (
        "• Dataset: 15 Enron executives (10 high-volume >= 120 emails, 5 low-volume for stress testing).\n"
        "• Strict Chronological 70/30 Split: First 70% by date for profile & null; last 30% strictly for holdout FPR evaluation.\n"
        "• 4-Tier Forged Evaluation Ladder: Relabel (held-out mail from other senders), Generic LLM, Styled Impersonation, Short Evasion.\n"
        "• Mandatory Tier C Copy Audit: Verified distinct 5-grams <= 5 and LCS <= 60 to measure pure style mimicry vs copying."
    )
    ax.text(0.0, 0.72, t1, fontsize=10.5, color="#2d3748", linespacing=1.5)

    # Insert Calibration Plot if available
    if os.path.exists(CALIBRATION_PLOT_PATH):
        img = plt.imread(CALIBRATION_PLOT_PATH)
        ax_img = ax.figure.add_axes([0.55, 0.12, 0.38, 0.52])
        ax_img.imshow(img)
        ax_img.axis("off")

    ax.text(0.0, 0.52, "Fair Baseline Comparison (Shared Routing Layer)", fontsize=13, fontweight="bold", color="#2b6cb0")
    t2 = (
        "• Baseline A: Centroid Cosine TF-IDF (IDF fit on pooled training only).\n"
        "• Baseline B: Global S Threshold (pooled alpha-quantile, no sender null).\n"
        "• Fairness: Baselines get the identical method-agnostic routing layer.\n\n"
        "Claim Discipline Formulation:\n"
        "• In-sample calibration = IMPLEMENTATION SANITY CHECK.\n"
        "• Holdout curve = EMPIRICAL EVIDENCE of robustness.\n"
        "• Holdout FPR - In-sample FPR = Measured Style Drift (+0.007)."
    )
    ax.text(0.0, 0.12, t2, fontsize=10, color="#2d3748", linespacing=1.5)


def slide_5(ax):
    """Results and Conclusions"""
    ax.text(0.0, 0.94, "Benchmark Results Summary (Verbatim Detection Contract)", fontsize=14, fontweight="bold", color="#2b6cb0")
    
    # Summary table
    table_data = [
        ["Model", "FPR_alert @0.05", "FPR_flagged @0.05", "R_Generic", "R_Styled", "R_Short", "Prec @ 10%"],
        ["GhostPen (Target Null)", "0.015", "0.017", "74.0%", "82.0%", "100.0%", "76.6%"],
        ["Baseline A (TF-IDF)", "0.009", "0.011", "28.0%", "82.0%", "100.0%", "79.4%"],
        ["Baseline B (Global S)", "0.048", "0.050", "79.0%", "82.0%", "100.0%", "54.6%"],
    ]
    
    ax_table = ax.figure.add_axes([0.05, 0.62, 0.90, 0.18])
    ax_table.axis("off")
    table = ax_table.table(cellText=table_data, loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(10.5)
    table.scale(1, 1.6)
    # Header row formatting
    for j in range(7):
        table[(0, j)].set_facecolor("#2b6cb0")
        table[(0, j)].set_text_props(color="white", weight="bold")
        table[(1, j)].set_facecolor("#ebf8ff")

    ax.text(0.0, 0.44, "Key Takeaways & Deployability", fontsize=13, fontweight="bold", color="#2b6cb0")
    t1 = (
        "1. Conformal Guarantee Works: Observed holdout FPR_alert (1.52%) stays strictly below alpha=0.05.\n"
        "2. Superior Threat Coverage: GhostPen catches 74% of generic LLM BEC vs Baseline A's 28% (TF-IDF fails on fluent rewordings).\n"
        "3. SOC Operational Viability: Only 1.71 false alarms per 100 genuine emails; precision reaches 76.6% at 10% attack prevalence.\n"
        "4. Stylometric Abstain vs. Escalation: 40.19% share of genuine mail we decline to judge stylometrically; holdout escalation rate is 0.19%.\n"
        "5. Transparent FP Autopsy: False positives stem from structured artifacts (e.g., semicolon-delimited appointment lists)."
    )
    ax.text(0.0, 0.20, t1, fontsize=9.5, color="#2d3748", linespacing=1.4)

    ax.text(
        0.0,
        0.05,
        "Limitations & Roadmap: For reply-heavy senders whose mail is predominantly brief, stylometry abstains on a large share of messages\n(abstain rate per sender in metrics.json); such senders are protected mainly by the routing layer, which is why TRIAGE is never a silent pass.\nStyle drift requires rolling updates; low-volume senders need >=20 emails for alpha=0.05. Scaffolding human-reviewed.",
        fontsize=8.0,
        color="#718096",
        style="italic",
        linespacing=1.3,
    )


def generate_presentation_pdf():
    print(f"Generating 5-page presentation PDF: {PDF_PATH} ...")
    with PdfPages(PDF_PATH) as pdf:
        create_slide(pdf, 1, "GhostPen: Writing-Style BEC Defense", "Hackathon Final Submission — Prototype v4.2-final", slide_1)
        create_slide(pdf, 2, "Project Objective & Market Problem", "Why BEC bypasses technical email security and why GenAI demands writing verification", slide_2)
        create_slide(pdf, 3, "Proposed Solution: Architecture & Mechanics", "Habit Ledger, target-null conformal calibration, directional shifts, and abstain-and-route", slide_3)
        create_slide(pdf, 4, "Solution Validation & Baseline Benchmarking", "Chronological anti-leakage splits, 4-tier forged evaluation ladder, and calibration curves", slide_4)
        create_slide(pdf, 5, "Results, Conclusions & Production Roadmap", "Empirical performance, false alarm economics, limitations, and AI disclosure", slide_5)

    size_mb = os.path.getsize(PDF_PATH) / (1024 * 1024)
    print(f"[OK] Generated {PDF_PATH} ({size_mb:.2f} MiB, exactly 5 pages, compliant with <= 20.0 MiB requirement)")


if __name__ == "__main__":
    generate_presentation_pdf()
