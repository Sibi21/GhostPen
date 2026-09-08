# GhostPen
**Business Email Compromise (BEC) Detection via Writing-Style Verification**  
*(v4.2-final)*

> *"Your CFO's writing style is a password."*

---

## 1. Quickstart (One-Click Launchers)

GhostPen is 100% self-contained: all cleaned email profiles, null distributions, and forged evaluation benchmarks are pre-committed in-repo. No API keys, external models, or network connections are needed at runtime.

### One-Click Launch (Zero Manual Setup)

GhostPen includes automated startup scripts that handle everything automatically — creating an isolated virtual environment (`.venv`), installing required dependencies, running pre-flight verification, launching the Streamlit interface, and opening your browser.

- **Windows**: Double-click **`START_GHOSTPEN.bat`** (or run `.\START_GHOSTPEN.bat` in PowerShell/cmd).
- **macOS / Linux**: Run **`./start_ghostpen.sh`** (or `bash start_ghostpen.sh`).

*Subsequent launches skip dependency checks and start the dashboard in ~2 seconds.*

---

### How to Stop and Restart

- **To Stop**: Click into the terminal window running GhostPen and press **`Ctrl + C`**.
- **To Restart**: Simply double-click **`START_GHOSTPEN.bat`** (Windows) or run **`./start_ghostpen.sh`** (macOS/Linux) again.

---

### Manual Setup & Commands (Terminal Option)

If you prefer to run the commands manually or want to explore the benchmark evaluation:

```bash
# 1. Create and activate an isolated virtual environment
python -m venv .venv

# On Windows:
.venv\Scripts\activate

# On macOS/Linux:
source .venv/bin/activate

# 2. Install dependencies (supports Python 3.10 through 3.14)
pip install -r requirements.txt

# 3. Run pre-flight readiness check
python scripts/check_ready.py

# 4. Launch Interactive Streamlit Demo (14-message CFO Inbox)
python -m streamlit run app/app.py

# 5. Run Fast Terminal CLI Demo
python -m src.cli --demo

# 6. Run Full Benchmark Evaluation & Baselines
python -m src.evaluate

# 7. Run Unit and Sanity Test Suite
python -m unittest tests/test_smoke.py

# 8. Rebuild Profiles and LOO Nulls from Data
python -m src.profile --rebuild

# 9. Generate 5-Page Presentation PDF
python scripts/generate_slides.py
```

---

### Troubleshooting

- **Python Not Found / "The term 'python' is not recognized"**:
  - Install Python 3.10 or newer from [python.org/downloads](https://www.python.org/downloads/).
  - **Important for Windows:** During installation, check the box: **`[X] Add python.exe to PATH`**.
- **Port 8501 is already in use**:
  - If a previous Streamlit process is still running in the background, close that command window, or start GhostPen on a different port:
    ```bash
    python -m streamlit run app/app.py --server.port 8502
    ```
- **Permission Denied on macOS / Linux (`./start_ghostpen.sh`)**:
  - Make the script executable by running:
    ```bash
    chmod +x start_ghostpen.sh
    ./start_ghostpen.sh
    ```
- **PowerShell Execution Policy Restrictions**:
  - Running `START_GHOSTPEN.bat` bypasses PowerShell script execution policies because it runs through the standard Windows Command processor (`cmd.exe`).
- **Missing `make` on Windows**:
  - You do not need `make`. Simply use `START_GHOSTPEN.bat` or the direct `python -m ...` commands listed above.


---

## 2. The Problem & 60-Second Explanation

BEC attacks bypass technical filters (SPF/DKIM/DMARC) because attackers compromise legitimate accounts or use valid lookalike domains. The technical envelope looks genuine — but the **writing style is wrong**.

```
[Past Sent Mail] ──► Habit Ledger (winsorized stats, floored stds, habit sets)
                              │
[Incoming Email] ──► Feature Extraction ──► Deviation Score S
                              │
[Leave-One-Out Null] ─────────┴───────────► Conformal p-value
                                                    │
                                                    ▼
                               Verdict: OK / ALERT / TRIAGE / UNENROLLED
                               + Plain-English broken habits
                               + Directional shift ("formality +2.1 sigma")
                               + Secondary content control routing (if TRIAGE)
```

1. **Habit Ledger**: Profiles ~70 unconscious function words, sentence burstiness (length mean & variance), punctuation rates, greeting/sign-off habits, contraction rates, formality markers, word length, vocabulary richness (TTR), and character 3-grams.
2. **Leave-One-Out (LOO) Null Calibration**: Evaluates incoming mail against the sender's own empirical null distribution, turning the false positive rate (FPR) into a controllable dial ($\alpha \in \{0.02, 0.05, 0.10\}$).
3. **Direction of Deviation**: Identifies whether writing deviates toward formal, generic LLM phrasing or loses contractions.
4. **Abstain-and-Route**: Short emails (<40 words or <3 sentences) cannot be judged with stylometric confidence. Rather than giving attackers a silent pass on short evasion emails, GhostPen issues a `TRIAGE` verdict and automatically routes messages with $\ge 2$ BEC context flags to secondary payment controls.

---

## 3. Expected Output

### Sample Verdicts
In the demonstration dashboard (`make demo` or `START_GHOSTPEN.bat`), each executive profile features its own contextual mailbox: **"Incoming mail claiming to be {display name}"**. Switching the active executive profile in the sidebar dynamically switches to that sender's curated inbox.

Across the canonical Marcus Hale (CFO) demo inbox (also runnable directly via `make demo-cli`), you will observe all four verdict classes:

```json
/* 1. Genuine Email (Typical holdout message) */
{
  "sender": "Marcus Hale",
  "deviation_score": 0.3363,
  "p": 0.9558,
  "p_min": 0.0089,
  "n_train": 112,
  "verdict": "OK",
  "reason": "Style aligns with enrolled profile (p=0.956 >= alpha=0.05)",
  "broken_habits": [],
  "content_escalation": false
}

/* 2. Forged Email (Generic LLM BEC wire request) */
{
  "sender": "Marcus Hale",
  "deviation_score": 0.8562,
  "p": 0.0177,
  "p_min": 0.0089,
  "n_train": 112,
  "verdict": "ALERT",
  "reason": "Stylometric deviation exceeds threshold (p=0.018 < alpha=0.05)",
  "direction": "Formality +4.0 sigma above his norm",
  "broken_habits": [
    "Uses greeting 'dear' (observed 0% in past mail; usually 'none' 100%)",
    "Signs 'best_regards' (observed 0% in past mail; usually 'none' 77%)",
    "Punctuation '!': 1 occurrences (0 observed in 112 past emails)"
  ],
  "content_escalation": false
}

/* 3. Short Benign Email ("ok thx") */
{
  "sender": "Marcus Hale",
  "deviation_score": 0.5080,
  "p": 0.2124,
  "p_min": 0.0089,
  "n_train": 112,
  "verdict": "TRIAGE",
  "reason": "message too short (<40 words or <3 sentences)",
  "content_escalation": false
}

/* 4. Short Forged Wire Evasion Email (22 words, urgent payment) */
{
  "sender": "Marcus Hale",
  "deviation_score": 0.5702,
  "p": 0.0973,
  "p_min": 0.0089,
  "n_train": 112,
  "verdict": "TRIAGE",
  "reason": "message too short (<40 words or <3 sentences)",
  "context_flags": ["confidential", "reply only to me", "today", "wire"],
  "content_escalation": true,
  "escalation_hint": "Stylometry abstains — route to content controls / payment verification."
}
```

---

## 4. How Scoring Works

### Deviation Score $S$
$$S = 0.25 \cdot \Delta(\text{function words}) + 0.25 \cdot \Delta(\text{char 3-grams}) + 0.35 \cdot \text{mean}(|z_{\text{capped}}|) + 0.15 \cdot \text{habit penalty}$$
- **Burrows' Delta ($\Delta$)**: Classic distance across relative frequencies normalized by sender variation, with individual $|z| \le 4.0$.
- **Robust Z-scores**: All training distributions are winsorized at 5th/95th percentiles; standard deviations are floored per family (`EPS`: rates/100w = 0.5, sentence length = 1.0, TTR = 0.01, word length = 0.1, relative frequencies = 0.0005); individual $|z|$ capped at 4.0.
- **Habit Penalty**: Sum of consistency weights for violated greeting and sign-off habits.

### Conformal Null Calibration & Verdict Function
For sender with $N = n_{\text{train}}$ emails, leave-one-out scores yield null distribution $\{s_1, \dots, s_N\}$.
$$p = \frac{1 + |\{i : s_i \ge S\}|}{N + 1}, \quad p_{\min} = \frac{1}{N + 1}$$

**Verdict Evaluation Order**:
1. Sender not enrolled $\to$ `UNENROLLED` (`"no profile; enroll >= floor(1/alpha) for your operating alpha (20 @ 0.05, 50 @ 0.02, 10 @ 0.10)"`)
2. Word count $< 40$ OR sentence count $< 3$ $\to$ `TRIAGE` (`"message too short (<40 words or <3 sentences)"`)
3. $n_{\text{train}} < \lfloor 1/\alpha \rfloor$ $\to$ `TRIAGE` (`"needs >= X emails for alpha=Y"`)
4. $p < \alpha \to$ `ALERT`
5. Otherwise $\to$ `OK`

### Detection Definition & Dual FPR Variants
The detection definition used consistently across all benchmarks:
```text
flagged = ALERT OR (TRIAGE AND content_escalation); caught = flagged.
```

`metrics.json` reports two separate False Positive Rate (FPR) variants (never summed or averaged):
- **$\text{FPR}_{\text{alert}}$**: ALERT rate on genuine holdout emails (subject of the conformal calibration claim).
- **$\text{FPR}_{\text{flagged}}$**: Total flagged rate on genuine holdout (ALERT + escalated TRIAGE), representing the operational false-alarm burden on the SOC.

---

## 5. Statistical Claim Discipline

> The in-sample calibration line is an **IMPLEMENTATION SANITY CHECK** — the plug-in p-value is approximately rank-uniform for ANY exchangeable score function, so it verifies arithmetic, not the model. The **HOLDOUT** line is the evidence; holdout FPR − in-sample FPR = measured style drift, reported as a finding. Never claim "holdout FPR = alpha by construction."
>
> LOO nulls are built on $n-1$-email profiles, which inflates them slightly relative to a new message scored against the full $n$-email profile, so deployment p-values are mildly conservative ($\text{FPR} \le \alpha$).

---

## 6. Abstain-and-Route Policy

In deployment, `TRIAGE` mail falls through to secondary controls (content rules, payment-verification policy). Short messages cannot support statistical stylometry, but attackers attempting brevity-based evasion will not receive a pass: if $\ge 2$ context flags appear on a `TRIAGE` message, `content_escalation` is triggered immediately.

---

## 7. Data Provenance & Anti-Leakage Rules

- **Data Source**: 15 senders from the public Enron corpus (10 high-volume with 160 emails each, 5 low-volume with 20–50 emails). Cleaned subsets are committed under `data/prepared/` (1.63 MB total). `scripts/rebuild_from_enron.py` documents full upstream regeneration.
- **Strict Chronological Splits**: First 70% of emails by date form training; last 30% form genuine holdout used strictly for evaluation.
- **Baselines**:
  - Baseline A (Centroid Cosine TF-IDF): IDF fit on pooled training mail only.
  - Baseline B (Global Threshold): Raw $S$ with single pooled threshold.
  - Thresholds tuned only on an inner 80/20 train-only slice.
- **Shared Routing Layer**: Baselines share the identical method-agnostic routing layer for fair comparison.
- **Tier C Copy Audit**: Forged styled emails are audited for distinct shared 5-grams ($>5$) and longest common substrings ($>60$ chars) to prove style mimicry rather than verbatim memorization.

---

## 8. Benchmark Evaluation & Results

### Baseline Comparison Table (from `artifacts/metrics.json`)
```text
Method                                 | FPR_alert | FPR_flag | R_Generic | R_Styled | R_Short | Prec @ 10%
---------------------------------------+-----------+----------+-----------+----------+---------+------------
GhostPen (Per-Sender LOO Null)         |   0.015   |  0.017   |   74.0%   |  82.0%   | 100.0%  |   76.6%
Baseline A (Centroid Cosine TF-IDF)    |   0.009   |  0.011   |   28.0%   |  82.0%   | 100.0%  |   79.4%
Baseline B (Global Threshold on S)     |   0.048   |  0.050   |   79.0%   |  82.0%   | 100.0%  |   54.6%
```

### Key Performance Findings
- **Conformal Calibration**: Holdout $\text{FPR}_{\text{alert}} = 0.0152 \le 0.05$ at $\alpha=0.05$ (conservative bound satisfied).
- **Style Drift**: In-sample $\text{FPR} = 0.0082$, holdout $\text{FPR} = 0.0152 \implies$ measured style drift $= +0.0070$.
- **SOC False Alarms**: Only **1.71 flags per 100 genuine emails**.
- **Tier C Copy Audit**: 46 of 50 styled impersonations (92.0%) are verified clean style mimics without text copying. Recall is 82.0% across all styled attacks, and 84.8% excluding copy-audited records.

---

## 9. Limitations & AI Disclosure

- **Style Drift**: People change writing habits over time; rolling 6-month profile update windows are recommended for production.
- **Low-Volume Senders**: Reliable conformal calibration at $\alpha=0.05$ requires $\ge 20$ training emails.
- **Character 3-grams**: Topic vocabulary can subtly influence 3-grams; glue function words remain primary.
- **English-Only**: Glue words and punctuation are tuned for English corporate communication.
- **AI-Assistance Disclosure**: Code scaffolding and forged corpus generated with an AI agent; design, evaluation, and statistical decisions human-reviewed.
- **Submission Slides**: The official 5-page PDF presentation is generated via `python scripts/generate_slides.py` and saved to `artifacts/GhostPen_Presentation.pdf`.
