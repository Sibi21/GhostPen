"""
app/app.py
----------
GhostPen Streamlit Interactive Demonstration Dashboard.
Demonstrates:
- 14-message CFO Inbox for Marcus Hale (8 genuine, 2 generic forged, 2 styled forged, 1 short benign, 1 short forged wire evasion)
- Live alpha slider {0.02, 0.05, 0.10} with instant reactive re-verdicting
- Reason-specific TRIAGE wording and red-bordered abstain-and-route escalation hints
- Broken habits cards, directional shift analysis, and him-vs-this comparative stats
- 100% theme-adaptive (works seamlessly in both Light and Dark mode)
"""

import json
import os
import sys

# Ensure repository root is on sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import pandas as pd
import streamlit as st

from src.demo_inbox import build_inbox
from src.features import extract_features
from src.ingest import get_all_senders, resolve_sender_id
from src.profile import load_null, load_profile
from src.score import score_message

# Streamlit Page Config
st.set_page_config(
    page_title="GhostPen — BEC Writing-Style Verification",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Theme-Adaptive Styling (Works in both Dark & Light themes)
st.markdown(
    """
    <style>
    .verdict-alert {
        background-color: rgba(207, 34, 46, 0.15);
        color: #ff6b6b;
        padding: 8px 14px;
        border-radius: 6px;
        font-weight: bold;
        border: 1px solid #cf222e;
        display: inline-block;
        font-size: 1.05em;
    }
    .verdict-ok {
        background-color: rgba(46, 160, 67, 0.15);
        color: #3fb950;
        padding: 8px 14px;
        border-radius: 6px;
        font-weight: bold;
        border: 1px solid #2ea043;
        display: inline-block;
        font-size: 1.05em;
    }
    .verdict-triage {
        background-color: rgba(210, 153, 34, 0.15);
        color: #e3b341;
        padding: 8px 14px;
        border-radius: 6px;
        font-weight: bold;
        border: 1px solid #d29922;
        display: inline-block;
        font-size: 1.05em;
    }
    .escalation-banner {
        background-color: rgba(207, 34, 46, 0.18);
        color: #ff7b72;
        border: 2px solid #f85149;
        padding: 14px;
        border-radius: 8px;
        margin-top: 12px;
        margin-bottom: 16px;
        font-weight: 600;
        line-height: 1.5;
    }
    .broken-habit-pill {
        background-color: rgba(207, 34, 46, 0.10);
        border-left: 4px solid #f85149;
        padding: 9px 13px;
        margin: 7px 0;
        border-radius: 0 6px 6px 0;
        font-size: 0.95em;
    }
    </style>
    """,
    unsafe_allow_html=True,
)




def main():
    st.title("GhostPen")
    st.markdown(
        "**BEC Detection via Writing-Style Verification** — *'Your CFO's writing style is a password.'*"
    )

    # -------------------------------------------------------------
    # Sidebar Controls
    # -------------------------------------------------------------
    st.sidebar.header("Control Panel")

    senders_list = get_all_senders()
    sender_options = {
        "Marcus Hale (CFO)": "Marcus Hale",
    }
    for s in senders_list:
        if s["sender_id"] != "presto-k":
            dname = f"{s['display_name']} ({s['volume_class'].upper()})"
            sender_options[dname] = s["sender_id"]

    selected_label = st.sidebar.selectbox("Active Executive Profile", list(sender_options.keys()), index=0)
    active_sender_id = sender_options[selected_label]

    alpha = st.sidebar.select_slider(
        "Operating Alpha Dial (FPR Target)",
        options=[0.02, 0.05, 0.10],
        value=0.05,
        help="Controls the statistical confidence threshold. Cranking to 0.02 enforces stricter evidence requirements.",
    )

    reveal_truth = st.sidebar.checkbox(
        "Reveal ground truth (demo only)",
        value=False,
        help="Shows authorial ground-truth tier per message for demonstration evaluation.",
    )

    # Load Active Profile Metadata
    active_profile = load_profile(active_sender_id)
    active_null = load_null(active_sender_id)
    if active_profile and active_null:
        st.sidebar.info(
            f"**Enrolled History:** {active_profile['n_train']} emails\n\n"
            f"**Minimum achievable p-value ($p_{{\\min}}$):** `{active_null['p_min']:.4f}`\n\n"
            f"**Operating Enrollment Floor:** $\ge {int(1.0/alpha)}$ emails"
        )
    else:
        st.sidebar.warning("Selected profile is unenrolled.")

    st.sidebar.markdown(
        """
        ---
        **Detection Contract:**  
        `flagged = ALERT ∨ (TRIAGE ∧ content_escalation)`
        """
    )

    # -------------------------------------------------------------
    # Load Inbox & Score Messages
    # -------------------------------------------------------------
    raw_messages = build_inbox(active_sender_id)
    if not raw_messages:
        st.error("Demo inbox data not found. Please run scripts or forge.")
        return

    # Score all messages reactively with current alpha
    scored_inbox = []
    for m in raw_messages:
        score_res = score_message(m["body"], active_sender_id, alpha=alpha)
        scored_inbox.append({**m, "res": score_res})

    # Summary metric counts
    total_cnt = len(scored_inbox)
    ok_cnt = sum(1 for m in scored_inbox if m["res"]["verdict"] == "OK")
    alert_cnt = sum(1 for m in scored_inbox if m["res"]["verdict"] == "ALERT")
    triage_cnt = sum(1 for m in scored_inbox if m["res"]["verdict"] == "TRIAGE")
    escalated_cnt = sum(1 for m in scored_inbox if m["res"]["content_escalation"])

    col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
    col_m1.metric("Inbox Messages", total_cnt)
    col_m2.metric("OK (Verified)", ok_cnt)
    col_m3.metric("ALERT (Anomalous)", alert_cnt)
    col_m4.metric("TRIAGE (Abstained)", triage_cnt)
    col_m5.metric("Content Escalated", escalated_cnt)

    st.markdown("---")

    # -------------------------------------------------------------
    # Two-Column Layout: Message List vs Message Inspection
    # -------------------------------------------------------------
    col_list, col_detail = st.columns([5, 7])

    with col_list:
        display_name = getattr(raw_messages, "display_name", selected_label)
        name_clean = display_name.split(" (")[0]
        st.subheader(f"Incoming mail claiming to be {display_name}")
        st.caption(f"These messages arrived with {name_clean}'s name on the From line. GhostPen checks whether the writing actually matches their enrolled history.")

        if getattr(raw_messages, "genuine_only", False):
            st.warning("Low-volume sender: no forged demo messages authored; see evaluation stress table. Expect TRIAGE (insufficient history) at strict alpha here — this reflects the enrollment floor working as designed.")
        elif not getattr(raw_messages, "has_short_genuine", True):
            st.info("Note: No genuine holdout messages under 40 words exist for this sender; short genuine slot omitted (13 messages total).")

        # Create interactive selection radio
        options = []
        for m in scored_inbox:
            v = m["res"]["verdict"]
            esc_tag = " [ESCALATED] " if m["res"]["content_escalation"] else ""
            tier_tag = f" | [{m['category']}]" if reveal_truth else ""
            options.append(f"{m['id']} | [{v}]{esc_tag}{tier_tag} | {m['subject'][:30]}...")

        selected_idx = st.selectbox(
            "Select email to audit:",
            range(len(options)),
            format_func=lambda i: options[i],
            key=f"audit_select_{active_sender_id}",
        )
        selected_item = scored_inbox[selected_idx]

        # Display table of inbox overview
        overview_data = []
        for m in scored_inbox:
            row = {
                "ID": m["id"],
                "Date": m["date"],
                "Subject": m["subject"],
                "Verdict": m["res"]["verdict"],
                "Score S": f"{m['res']['deviation_score']:.3f}",
                "Escalated": "YES" if m["res"]["content_escalation"] else "-",
            }
            if reveal_truth:
                row["Ground Truth Tier"] = m["category"]
            overview_data.append(row)
        st.dataframe(pd.DataFrame(overview_data), hide_index=True, use_container_width=True)

    # -------------------------------------------------------------
    # Message Detail Inspector
    # -------------------------------------------------------------
    with col_detail:
        st.subheader(f"Audit Inspection: {selected_item['id']}")
        if reveal_truth:
            st.info(f"**Ground Truth Tier (Demo Mode):** `{selected_item['category']}`")
        res = selected_item["res"]
        verdict = res["verdict"]

        # 1. Verdict Banner
        if verdict == "ALERT":
            st.markdown(f'<div class="verdict-alert">VERDICT: ALERT — Anomaly Detected (p={res["p"]:.3f} &lt; α={alpha})</div>', unsafe_allow_html=True)
        elif verdict == "OK":
            st.markdown(f'<div class="verdict-ok">VERDICT: OK — Stylometrically Verified (p={res["p"]:.3f} &ge; α={alpha})</div>', unsafe_allow_html=True)
        elif verdict == "TRIAGE":
            st.markdown(f'<div class="verdict-triage">VERDICT: TRIAGE — Stylometry Abstained</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="verdict-triage">VERDICT: UNENROLLED</div>', unsafe_allow_html=True)

        # 2. Reason-Agnostic Escalation Banner
        if res["content_escalation"]:
            st.markdown(
                f"""
                <div class="escalation-banner">
                    <b>ROUTING ACTION:</b> {res['escalation_hint']}<br>
                    <small><b>Detected High-Risk Context Flags:</b> {', '.join(res['context_flags'])}</small>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # 3. Key Metrics: Score S, p-value, word count
        col_g1, col_g2, col_g3 = st.columns(3)
        col_g1.metric("Deviation Score S", f"{res['deviation_score']:.4f}")

        # Gauge rendering rule: when TRIAGE, render as "abstained (n/a)" with reason-specific line
        if verdict == "TRIAGE":
            if res["word_count"] < 40 or res["sentence_count"] < 3:
                gauge_subtext = "text too thin to judge reliably — routed to content controls"
            else:
                gauge_subtext = "not enough of his past mail to calibrate at this alpha"
            col_g2.metric("Conformal p-value", "abstained (n/a)", help=gauge_subtext)
            st.caption(f"*{gauge_subtext}* (raw score S={res['deviation_score']:.4f})")
        else:
            col_g2.metric("Conformal p-value", f"{res['p']:.4f}", help=f"Operating alpha: {alpha}")
            st.caption(f"Minimum achievable p-value: p_min={res['p_min']:.4f}")

        col_g3.metric("Length", f"{res['word_count']} words", f"{res['sentence_count']} sents")

        # 4. Broken Habits Cards
        st.markdown("#### Stylometric Deviations & Evidence")
        if res["broken_habits"]:
            for bh in res["broken_habits"]:
                st.markdown(f'<div class="broken-habit-pill">• {bh}</div>', unsafe_allow_html=True)
        else:
            st.success("All observed writing habits match the enrolled executive baseline.")

        # 5. Directional Shift
        if res["direction"] != "Style variation within normal baseline":
            st.info(f"**Direction of Shift:** {res['direction']}")

        # 6. Him-vs-This Comparative Stats Table
        if active_profile:
            with st.expander("Him-vs-This Comparative Ledger", expanded=False):
                comp_rows = []
                feats = extract_features(selected_item["body"])

                # Punctuation
                for p in ["!", "?", ";", ":", "—"]:
                    obs = feats["punct_rates"].get(p, 0.0)
                    stat = active_profile["numeric_stats"][f"punct_{p}"]
                    z = (obs - stat["mean"]) / stat["std"]
                    comp_rows.append({
                        "Feature": f"Punctuation '{p}' (per 100w)",
                        "This Message": f"{obs:.2f}",
                        "Executive Norm": f"{stat['mean']:.2f}",
                        "Spread (Std)": f"{stat['std']:.2f}",
                        "z-score": f"{z:+.2f}{' (capped)' if abs(z)>=4 else ''}",
                    })

                # Contraction rate
                stat = active_profile["numeric_stats"]["contraction_rate"]
                z = (feats["contraction_rate"] - stat["mean"]) / stat["std"]
                comp_rows.append({
                    "Feature": "Contraction Rate (/100w)",
                    "This Message": f"{feats['contraction_rate']:.2f}",
                    "Executive Norm": f"{stat['mean']:.2f}",
                    "Spread (Std)": f"{stat['std']:.2f}",
                    "z-score": f"{z:+.2f}{' (capped)' if abs(z)>=4 else ''}",
                })

                # Formality rate
                stat = active_profile["numeric_stats"]["formality_rate"]
                z = (feats["formality_rate"] - stat["mean"]) / stat["std"]
                comp_rows.append({
                    "Feature": "Formality Rate (/100w)",
                    "This Message": f"{feats['formality_rate']:.2f}",
                    "Executive Norm": f"{stat['mean']:.2f}",
                    "Spread (Std)": f"{stat['std']:.2f}",
                    "z-score": f"{z:+.2f}{' (capped)' if abs(z)>=4 else ''}",
                })

                # Sentence Burstiness
                stat = active_profile["numeric_stats"]["sentence_len_std"]
                z = (feats["sentence_len_std"] - stat["mean"]) / stat["std"]
                comp_rows.append({
                    "Feature": "Sentence Burstiness (std)",
                    "This Message": f"{feats['sentence_len_std']:.2f}",
                    "Executive Norm": f"{stat['mean']:.2f}",
                    "Spread (Std)": f"{stat['std']:.2f}",
                    "z-score": f"{z:+.2f}{' (capped)' if abs(z)>=4 else ''}",
                })

                st.table(pd.DataFrame(comp_rows))

        # 7. Raw Email Body
        with st.expander("Raw Message Body", expanded=True):
            st.text(selected_item["body"])

        # 8. Technical JSON
        with st.expander("SOC Diagnostic JSON", expanded=False):
            st.json(res)


if __name__ == "__main__":
    main()
