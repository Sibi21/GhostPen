"""
app/app.py
----------
GhostPen Streamlit Interactive Demonstration Dashboard.
Demonstrates:
- 14-message CFO Inbox for Marcus Hale (8 genuine, 2 generic forged, 2 styled forged, 1 short benign, 1 short forged wire evasion)
- Live alpha slider {0.02, 0.05, 0.10} with instant reactive re-verdicting
- Reason-specific TRIAGE wording and red-bordered abstain-and-route escalation hints
- Broken habits cards, directional shift analysis, and baseline-vs-this comparative stats
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

from src.attribution import (
    compute_attribution,
    extract_matched_habits,
    get_alpha_price_tag,
)
from src.demo_inbox import build_inbox
from src.features import extract_features
from src.ingest import display_name, get_all_senders, resolve_sender_id
from src.profile import load_null, load_profile
from src.score import score_message

METRICS_FILE = os.path.join(REPO_ROOT, "artifacts", "metrics.json")


def load_metrics_cache():
    if os.path.exists(METRICS_FILE):
        try:
            with open(METRICS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


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
    .matched-habit-pill {
        background-color: rgba(46, 160, 67, 0.10);
        border-left: 4px solid #2ea043;
        padding: 8px 12px;
        margin: 6px 0;
        border-radius: 0 6px 6px 0;
        font-size: 0.93em;
    }
    /* P5: Mailbox table styling & column-menu suppression */
    .mailbox-table-container {
        width: 100%;
        overflow-x: auto;
        border-radius: 8px;
        border: 1px solid rgba(226, 232, 240, 0.4);
        background: transparent;
        margin-top: 12px;
        margin-bottom: 16px;
    }
    .mailbox-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.82rem;
        text-align: left;
    }
    .mailbox-table th {
        background-color: rgba(247, 250, 252, 0.08);
        font-weight: 700;
        padding: 9px 8px;
        border-bottom: 2px solid rgba(226, 232, 240, 0.3);
        white-space: nowrap;
        user-select: none;
    }
    .mailbox-table td {
        padding: 8px 8px;
        border-bottom: 1px solid rgba(226, 232, 240, 0.15);
        vertical-align: middle;
    }
    .mailbox-row {
        transition: background-color 0.15s ease;
    }
    .mailbox-row:hover {
        background-color: rgba(49, 130, 206, 0.08);
    }
    .mailbox-row.selected-row {
        background-color: rgba(49, 130, 206, 0.18) !important;
        border-left: 4px solid #3182ce !important;
        font-weight: 600;
    }
    .badge {
        display: inline-block;
        padding: 2px 7px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.02em;
    }
    .badge-ok {
        background-color: rgba(46, 160, 67, 0.2);
        color: #3fb950;
        border: 1px solid rgba(46, 160, 67, 0.4);
    }
    .badge-alert {
        background-color: rgba(207, 34, 46, 0.2);
        color: #ff7b72;
        border: 1px solid rgba(207, 34, 46, 0.4);
    }
    .badge-triage {
        background-color: rgba(210, 153, 34, 0.2);
        color: #e3b341;
        border: 1px solid rgba(210, 153, 34, 0.4);
    }
    .badge-esc {
        background-color: rgba(207, 34, 46, 0.25);
        color: #ff7b72;
        font-weight: 800;
        padding: 2px 6px;
        border-radius: 3px;
    }
    .badge-caution {
        background-color: rgba(210, 153, 34, 0.25);
        color: #e3b341;
        font-weight: 800;
        padding: 2px 6px;
        border-radius: 3px;
        border: 1px solid rgba(210, 153, 34, 0.4);
    }
    .verdict-caution {
        background-color: rgba(210, 153, 34, 0.15);
        color: #e3b341;
        padding: 8px 14px;
        border-radius: 6px;
        font-weight: bold;
        border: 1px solid #d29922;
        display: inline-block;
        font-size: 1.05em;
    }
    .caution-banner {
        background-color: rgba(210, 153, 34, 0.15);
        color: #e3b341;
        border: 2px solid #d29922;
        padding: 14px;
        border-radius: 8px;
        margin-top: 12px;
        margin-bottom: 16px;
        font-weight: 600;
        line-height: 1.5;
    }
    .badge-tier {
        background-color: rgba(113, 128, 150, 0.2);
        color: #a0aec0;
        font-family: monospace;
        font-size: 0.72rem;
    }
    /* Safety rule: ensure no column menu or statistics popovers ever render */
    div[data-testid="stDataFrameColumnMenu"],
    div[data-testid="stDataFrameColumnMenuTarget"],
    .stDataFrameStatisticsMenu,
    div[data-testid="stDataFrameStatisticsChart"] {
        display: none !important;
        visibility: hidden !important;
        pointer-events: none !important;
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
    sender_options = {}
    option_tooltips = {}
    vol_map = {}
    for s in senders_list:
        sid = s["sender_id"]
        dname = display_name(sid)
        vclass = s.get("volume_class", "high").upper()
        vol_map[dname] = vclass
        sender_options[dname] = sid
        prof = load_profile(sid)
        n_tr = prof["n_train"] if prof else s.get("total_emails", 0)
        option_tooltips[dname] = f"{dname}: {n_tr} enrolled emails ({s.get('volume_class', 'high')})"

    default_sender_idx = 0
    query_sender = st.query_params.get("sender", "")
    if query_sender:
        for idx, lbl in enumerate(sender_options.keys()):
            if query_sender.lower() in lbl.lower():
                default_sender_idx = idx
                break

    selected_label = st.sidebar.selectbox(
        "Active Executive Profile",
        list(sender_options.keys()),
        index=default_sender_idx,
        format_func=lambda name: name if name.endswith((" (HIGH)", " (LOW)")) else f"{name} ({vol_map.get(name, 'HIGH')})",
        key="active_sender_select",
        help="Select an executive profile. Hover over options or see legend below for volume class and training history.",
    )
    active_sender_id = sender_options[selected_label]
    active_tooltip = option_tooltips.get(selected_label, "")

    # C1: Dropdown legend directly under the dropdown
    st.sidebar.caption("HIGH = high-volume sender (>= 120 enrolled emails) - LOW = low-volume (20-60) - expect TRIAGE at strict alpha from the enrollment floor.")
    st.sidebar.markdown(f"<div style='margin-top:-6px;margin-bottom:10px;'><small><b>Selected Profile:</b> <span title='{active_tooltip}'>{active_tooltip}</span></small></div>", unsafe_allow_html=True)

    # C1: Inject client-side option hover tooltips
    option_tooltips_full = {}
    for name, tt in option_tooltips.items():
        option_tooltips_full[name] = tt
        option_tooltips_full[f"{name} ({vol_map.get(name, 'HIGH')})"] = tt

    st.markdown(
        f"""
        <script>
        const optionTooltips = {json.dumps(option_tooltips_full)};
        const observer = new MutationObserver(() => {{
            const options = parent.document.querySelectorAll('li[role="option"], div[role="option"]');
            options.forEach(opt => {{
                const txt = opt.innerText ? opt.innerText.trim() : "";
                if (optionTooltips[txt]) {{
                    opt.setAttribute('title', optionTooltips[txt]);
                }}
            }});
        }});
        observer.observe(parent.document.body, {{ childList: true, subtree: true }});
        </script>
        """,
        unsafe_allow_html=True,
    )

    # C2: 3-point alpha dial with visible ticks, caption, and tooltip
    dial_caption_text = (
        "Three calibrated operating points. Each displays its measured holdout "
        "false-alarm price; intermediate settings are not offered because we do "
        "not display unmeasured rates."
    )

    alpha = st.sidebar.select_slider(
        "Operating Alpha Dial (FPR Target)",
        options=[0.02, 0.05, 0.10],
        value=0.05,
        format_func=lambda x: f"{x:.2f}",
        help=dial_caption_text,
    )

    # Visible tick labels at all three positions (0.02, 0.05, 0.10)
    col_t1, col_t2, col_t3 = st.sidebar.columns([1, 1, 1])
    col_t1.markdown("<small style='opacity:0.8;'><b>0.02</b><br>(strict)</small>", unsafe_allow_html=True)
    col_t2.markdown("<small style='opacity:0.8;text-align:center;display:block;'><b>0.05</b><br>(standard)</small>", unsafe_allow_html=True)
    col_t3.markdown("<small style='opacity:0.8;text-align:right;display:block;'><b>0.10</b><br>(relaxed)</small>", unsafe_allow_html=True)

    st.sidebar.caption(dial_caption_text)

    # C3: Operational cost line cleanup
    price_tag = get_alpha_price_tag(alpha)
    st.sidebar.markdown(
        f"**Operational Cost:** at alpha = {alpha:.2f}: expect ~{price_tag['flags_per_100']:.1f} flags per 100 genuine emails (pooled across enrolled senders, measured on holdout)"
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
            f"**Operating Enrollment Floor:** $\\ge {int(1.0/alpha)}$ emails"
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
    col_list, col_detail = st.columns([5.3, 6.7])

    with col_list:
        mailbox_display_name = display_name(active_sender_id)
        name_clean = mailbox_display_name.split(" (")[0]
        st.subheader(f"Incoming mail claiming to be {mailbox_display_name}")
        st.caption(f"These messages arrived with {name_clean}'s name on the From line. GhostPen checks whether the writing actually matches their enrolled history.")

        if getattr(raw_messages, "genuine_only", False):
            st.warning("Low-volume sender: no forged demo messages authored; see evaluation stress table. Expect TRIAGE (insufficient history) at strict alpha here — this reflects the enrollment floor working as designed.")
        elif not getattr(raw_messages, "has_short_genuine", True):
            st.info("Note: No genuine holdout messages under 40 words exist for this sender; short genuine slot omitted (13 messages total).")

        # Create interactive selection radio and sorting controls
        options = []
        for m in scored_inbox:
            v = m["res"]["verdict"]
            is_caution = m["res"].get("content_caution", False) or (v == "OK" and len(m["res"].get("context_flags", [])) >= 2)
            esc_tag = " [ESCALATED] " if m["res"]["content_escalation"] else (" [CAUTION] " if is_caution else "")
            tier_tag = f" | [{m['category']}]" if reveal_truth else ""
            options.append(f"{m['id']} | [{v}]{esc_tag}{tier_tag} | {m['subject'][:30]}...")

        default_audit_idx = 0
        query_audit = st.query_params.get("audit", "")
        if query_audit:
            for idx, m in enumerate(scored_inbox):
                if query_audit.lower() in m["id"].lower() or query_audit == str(idx):
                    default_audit_idx = idx
                    break

        col_audit, col_sort = st.columns([3, 2])
        with col_audit:
            selected_idx = st.selectbox(
                "Select email to audit:",
                range(len(options)),
                index=default_audit_idx,
                format_func=lambda i: options[i],
                key=f"audit_select_{active_sender_id}",
            )

        default_sort_idx = 0
        sort_opts = ["Default order", "Date (ascending)", "Date (descending)"]
        query_sort = st.query_params.get("sort", "")
        if query_sort:
            for idx, opt in enumerate(sort_opts):
                if query_sort.lower() in opt.lower():
                    default_sort_idx = idx
                    break

        with col_sort:
            sort_order = st.selectbox(
                "Sort table by:",
                options=sort_opts,
                index=default_sort_idx,
                key=f"sort_order_{active_sender_id}",
                help="Sort incoming messages without modifying the underlying audit selection.",
            )
        selected_item = scored_inbox[selected_idx]

        # Prepare sorted display list while preserving _orig_idx for selection sync
        indexed_inbox = [{**m, "_orig_idx": idx} for idx, m in enumerate(scored_inbox)]
        if sort_order == "Date (ascending)":
            display_inbox = sorted(indexed_inbox, key=lambda m: (m.get("date", ""), m["_orig_idx"]))
        elif sort_order == "Date (descending)":
            display_inbox = sorted(indexed_inbox, key=lambda m: (m.get("date", ""), m["_orig_idx"]), reverse=True)
        else:
            display_inbox = indexed_inbox

        # Plain display table (no column menu, no statistics bug)
        table_html = [
            '<div class="mailbox-table-container">',
            '<table class="mailbox-table">',
            '<thead><tr>',
            '<th>ID</th>',
            '<th>Date</th>',
            '<th>Subject</th>',
            '<th>Verdict</th>',
            '<th>Score S</th>',
            '<th>Escalated</th>',
        ]
        if reveal_truth:
            table_html.append('<th>Ground Truth Tier</th>')
        table_html.append('</tr></thead><tbody>')

        for m in display_inbox:
            orig_idx = m["_orig_idx"]
            is_selected = (orig_idx == selected_idx)
            row_class = "mailbox-row selected-row" if is_selected else "mailbox-row"
            v = m["res"]["verdict"]
            v_class = f"badge-{v.lower()}"
            if m["res"]["content_escalation"]:
                esc = '<span class="badge badge-esc">YES</span>'
            elif m["res"].get("content_caution", False) or (m["res"]["verdict"] == "OK" and len(m["res"].get("context_flags", [])) >= 2):
                esc = '<span class="badge badge-caution">CAUTION</span>'
            else:
                esc = '<span style="opacity: 0.5;">-</span>'
            s_score = f"{m['res']['deviation_score']:.3f}"
            subj = m["subject"]
            if len(subj) > 36:
                subj = subj[:36] + "..."

            active_pill = ' <span style="color:#3182ce; font-size:0.68rem; font-weight:700;">[SELECTED]</span>' if is_selected else ''

            row_html = [
                f'<tr class="{row_class}" data-idx="{orig_idx}">',
                f'<td class="cell-id"><b>{m["id"]}</b>{active_pill}</td>',
                f'<td class="cell-date">{m["date"]}</td>',
                f'<td class="cell-subject" title="{m["subject"]}">{subj}</td>',
                f'<td class="cell-verdict"><span class="badge {v_class}">{v}</span></td>',
                f'<td class="cell-score"><code>{s_score}</code></td>',
                f'<td class="cell-esc">{esc}</td>',
            ]
            if reveal_truth:
                tier = m.get("category", "-")
                row_html.append(f'<td class="cell-tier"><span class="badge badge-tier">{tier}</span></td>')
            row_html.append('</tr>')
            table_html.extend(row_html)

        table_html.append('</tbody></table></div>')

        # Add JavaScript to sync row click with audit selectbox
        row_click_js = """
        <script>
        (function() {
            function bindMailboxRows() {
                const rows = document.querySelectorAll('.mailbox-row');
                rows.forEach(row => {
                    if (row.dataset.bound) return;
                    row.dataset.bound = 'true';
                    row.style.cursor = 'pointer';
                    row.addEventListener('click', function() {
                        const targetIdx = parseInt(this.getAttribute('data-idx'));
                        const selectboxes = document.querySelectorAll('div[data-testid="stSelectbox"]');
                        let auditBox = null;
                        selectboxes.forEach(sb => {
                            if (sb.innerText.includes('Select email to audit:')) {
                                auditBox = sb;
                            }
                        });
                        if (!auditBox && selectboxes.length > 1) {
                            auditBox = selectboxes[selectboxes.length - 1];
                        }
                        if (auditBox) {
                            const trigger = auditBox.querySelector('div[role="combobox"], input, div[aria-haspopup="listbox"]');
                            if (trigger) {
                                trigger.click();
                                setTimeout(() => {
                                    const options = document.querySelectorAll('li[role="option"], div[role="option"]');
                                    if (options && options[targetIdx]) {
                                        options[targetIdx].click();
                                    }
                                }, 30);
                            }
                        }
                    });
                });
            }
            bindMailboxRows();
            const observer = new MutationObserver(bindMailboxRows);
            observer.observe(document.body, { childList: true, subtree: true });
        })();
        </script>
        """
        st.markdown("\n".join(table_html) + row_click_js, unsafe_allow_html=True)

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
        has_content_caution = res.get("content_caution", False) or (verdict == "OK" and len(res.get("context_flags", [])) >= 2)
        if verdict == "ALERT":
            st.markdown(f'<div class="verdict-alert">VERDICT: ALERT — Anomaly Detected (p={res["p"]:.3f} &lt; α={alpha})</div>', unsafe_allow_html=True)
        elif verdict == "OK":
            if has_content_caution:
                st.markdown(f'<div class="verdict-caution">VERDICT: OK (Style p={res["p"]:.3f} &ge; α={alpha}) | CAUTION (High-Risk Content)</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="verdict-ok">VERDICT: OK — Stylometrically Verified (p={res["p"]:.3f} &ge; α={alpha})</div>', unsafe_allow_html=True)
        elif verdict == "TRIAGE":
            st.markdown(f'<div class="verdict-triage">VERDICT: TRIAGE — Stylometry Abstained</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="verdict-triage">VERDICT: UNENROLLED</div>', unsafe_allow_html=True)

        # 2. Reason-Agnostic Escalation Banner / Content Risk Advisory
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
        elif has_content_caution:
            st.markdown(
                f"""
                <div class="caution-banner">
                    <b>CONTENT RISK ADVISORY:</b> Stylometric style matches baseline (p={res['p']:.3f} &ge; α={alpha}), but message contains high-risk BEC/financial keywords.<br>
                    <small><b>Action Required:</b> Perform out-of-band wire/payment authorization verification before acting on this request.<br>
                    <b>Detected High-Risk Context Flags:</b> {', '.join(res['context_flags'])}</small>
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
                gauge_subtext = "not enough past emails to calibrate at this alpha"
            col_g2.metric("Conformal p-value", "abstained (n/a)", help=gauge_subtext)
            st.caption(f"*{gauge_subtext}* (raw score S={res['deviation_score']:.4f})")
        else:
            col_g2.metric("Conformal p-value", f"{res['p']:.4f}", help=f"Operating alpha: {alpha}")
            st.caption(f"Minimum achievable p-value: p_min={res['p_min']:.4f}")

        col_g3.metric("Length", f"{res['word_count']} words", f"{res['sentence_count']} sents")

        # 4. Broken Habits Cards
        st.markdown("#### Stylometric Deviations & Evidence")
        if res["broken_habits"]:
            if verdict == "OK" and res.get("p", 1.0) < 0.20:
                st.warning(
                    f"**Borderline Stylometric Drift (p = {res['p']:.4f} vs threshold α = {alpha}):** "
                    f"Specific habits deviate from baseline norm (see below), but overall function-word distance "
                    f"remains within historical null variance (p >= α). Review habit evidence carefully."
                )
            for bh in res["broken_habits"]:
                st.markdown(f'<div class="broken-habit-pill">• {bh}</div>', unsafe_allow_html=True)
        else:
            st.success("All observed writing habits match the enrolled executive baseline.")

        # A2: Context-aware Matched Habits Panel (Patch P10)
        is_alert_or_esc = (verdict == "ALERT") or (verdict == "TRIAGE" and res.get("content_escalation", False))
        is_ok = (verdict == "OK")
        is_plain_triage = (verdict == "TRIAGE" and not res.get("content_escalation", False))

        if is_alert_or_esc:
            matched_title = "What the disguise got right"
            matched_prefix = "attacker matched:"
        elif is_ok:
            matched_title = "Habits matching the baseline"
            matched_prefix = "matched:"
        elif is_plain_triage:
            matched_title = f"Habits within normal range (low confidence - {res['word_count']} words)"
            matched_prefix = "within range:"
        else:
            matched_title = None
            matched_prefix = None

        if matched_title and matched_prefix:
            matched_cards = extract_matched_habits(selected_item["body"], active_sender_id, prefix=matched_prefix)
            if matched_cards:
                st.markdown(f"##### {matched_title}")
                for mc in matched_cards:
                    tt = mc["tooltip"]
                    title = mc["title"]
                    detail = mc["detail"]
                    st.markdown(
                        f'<div class="matched-habit-pill" title="{tt}">✔ <b>{title}</b> — <small>{detail}</small></div>',
                        unsafe_allow_html=True,
                    )

        # P6.1 Attribution panel visibility rule:
        # Show "Closest enrolled authors" ranking ONLY when verdict is ALERT,
        # or TRIAGE with content_escalation = true (claimed sender rejected or abstained-with-flags).
        is_alert = (verdict == "ALERT")
        is_escalated_triage = (verdict == "TRIAGE" and res["content_escalation"])

        if is_alert or is_escalated_triage:
            metrics_data = load_metrics_cache()
            relabel_acc = metrics_data.get("attribution_top1_accuracy_relabel", 0.03)

            # P6.2 Honest framing of the ranking (tooltip + caption):
            framing_text = (
                "Cross-sender ranking is a forensic suggestion, not identification: a "
                "genuine message's p against its true author is uniform by construction, "
                "and boilerplate text (out-of-office, forwards) carries little personal "
                f"signal, so ranks can shuffle on such mail. Measured top-1 accuracy on the "
                f"relabel tier: {relabel_acc}."
            )
            st.markdown(
                f'<div title="{framing_text}">'
                f'<h4>Closest enrolled authors (among 15 enrolled senders - suggestion, not identification; never affects S or the verdict)</h4>'
                f'</div>',
                unsafe_allow_html=True,
            )
            st.caption(f"💡 *{framing_text}*")

            att = compute_attribution(selected_item["body"], active_sender_id, alpha=alpha)
            if att["is_no_match"]:
                st.warning("No enrolled author's style matches this message.")
                st.caption(f"Claimed sender ({att['claimed_sender']['display_name']}): p = {att['claimed_sender']['p']:.4f}")
            else:
                cols = st.columns(len(att["top_3"]))
                for idx, m in enumerate(att["top_3"]):
                    with cols[idx]:
                        st.metric(
                            f"#{idx + 1} Match",
                            m["display_name"],
                            f"p = {m['p']:.4f}",
                            help=f"Deviation score S = {m['deviation_score']:.4f}",
                        )
                st.caption(
                    f"**Claimed sender contrast:** {att['claimed_sender']['display_name']} "
                    f"(p = `{att['claimed_sender']['p']:.4f}`, rank #{att['claimed_rank']})"
                )
        elif verdict == "OK":
            # On OK messages, replace the panel with one line:
            # "Verified as {claimed sender}. Attribution ranking is shown only for rejected messages."
            claimed_display = name_clean
            st.info(f"Verified as {claimed_display}. Attribution ranking is shown only for rejected messages.")
        elif verdict == "TRIAGE":
            # On plain TRIAGE (no escalation), show one line:
            # "Stylometry abstained - no attribution suggested."
            st.info("Stylometry abstained - no attribution suggested.")

        # 5. Directional Shift
        if res["direction"] != "Style variation within normal baseline":
            st.info(f"**Direction of Shift:** {res['direction']}")

        # 6. Baseline-vs-This Comparative Stats Table
        if active_profile:
            with st.expander("Baseline-vs-This Comparative Ledger", expanded=False):
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
