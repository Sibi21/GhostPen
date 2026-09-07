GhostPen — BEC Detection via Writing-Style Analysis
Every person writes like themselves. GhostPen turns a sender's writing habitsinto a statistical fingerprint and returns, for every message claiming to bethem: a deviation score, a p-value, a verdict, and plain-English evidence.

Tagline for the slides: "Your CFO's writing style is a password."

1. Why this is different
Most teams will do	We do instead	Why it matters
Cosine to a centroid + arbitrary threshold	Per-sender null + conformal-style p-value	FPR becomes a dial (α), not a wish
"Different = suspicious"	Direction-aware (too formal, no contractions)	Matches how BEC forgeries actually look
Forgeries = relabelled emails only	3-tier ladder + short-message evasion plays	Honest, harder evaluation
One black-box score	Habit Ledger with evidence per alert	Deployable + demo-ready
Claims with no comparison	Measured baselines, identical splits + shared routing layer	The moat is a table, not rhetoric — and a fair one
Abstention on short mail = silent pass	Abstain-and-route: TRIAGE feeds content controls	The obvious "how does it fail" answer, on stage
"It works"	Data + artifacts shipped in-repo, determinism-tested	The demo cannot die
2. The idea in 30 seconds
past sent emails ──► HABIT LEDGER (robust per-sender feature stats + habit sets)                              │new incoming email ──► personal z-scores + habit checks ──► raw score S                              │sender's OWN null (leave-one-out on training) ──► p-value                              │verdict = f(enrolled, p, α, n_train, length) → OK / ALERT / TRIAGE / UNENROLLED        + broken-habits explanation + direction        + separate content-flag strip (escalation layer when stylometry abstains)
3. Data
Enron maildir subset, cleaned and committed in the repo (~1 MB,15 senders): 10 high-volume (≥120 sent emails) + 5 low-volume (20–60).scripts/rebuild_from_enron.py regenerates it from the full corpus.
One high-volume sender aliased as "Marcus Hale, CFO" for the demo.
Cleaning: strip quoted replies, forwarded blocks, signatures, HTML; bodyonly. Cleaning code strips structure only — it never rewords email text.
Chronological 70/30 split per sender: first 70% → profile + null(training); last 30% → genuine holdout, used ONLY to measure FPR.
Relabel forgeries come from other senders' holdout (keeps them out of thebaseline's IDF fit); they stay genuine holdout for their own sender, soprecision is computed only on the curated demo inbox — never over pooledholdout+forgeries, where one email would carry two labels.
Baseline thresholds tuned on a train-only inner slice — never holdout.
4. The Habit Ledger
Feature group	Plain meaning	Example habit it catches
Function words (~70)	Unconscious grammar glue	"He never writes however; he writes but"
Sentence length mean + sd	Rhythm; sd = "burstiness"	Punchy bursts vs uniform LLM sentences
Punctuation rates (! ? ; : —)	Per 100 words	Zero '!' in 214 emails
Greeting / sign-off sets	With frequencies; "none" is a category	Always signs "thx" (95%)
Contractions + formality + word length	Style register	1.9 contractions/100w → 0 in forgery
Type-token ratio	Vocabulary richness (brief-listed)	Repeated vs varied wording
Char 3-gram profile	Subconscious spelling fingerprint (Delta)	Catches styled attacks
Robust statistics: training values winsorized at 5/95, stds floored perfamily (EPS), |z| capped at 4 — applied identically inside the null.(Median/MAD rejected: MAD = 0 on majority-constant features.)

5. Scoring — p-values, not vibes
S = 0.25·Δ(function words) + 0.25·Δ(char 3-grams) + 0.35·mean|z| +0.15·habit penalty. Weights documented; the per-sender null absorbs scale.
Null: full leave-one-out over the n_train training emails — whatgenuine mail from this person scores like.
p = (1 + #{null ≥ S}) / (N + 1); p_min = 1/(N+1).
Verdict (pure function, in order): UNENROLLED ("no profile; enroll ≥⌊1/α⌋ for your operating α") → TRIAGE (too short, <40 words or <3sentences) → TRIAGE (insufficient history: n_train < ⌊1/α⌋) → ALERT ifp < α → else OK. Alerting at α needs n_train ≥ 20 (α=0.05), 50 (0.02),10 (0.10).
Abstain-and-route: TRIAGE is a routing state, never a benign verdict.Context flags render on every message; any TRIAGE (too short ORinsufficient history) + ≥2 flags triggers a display-layer escalation hint("stylometry abstains — route to content controls / payment verification").Content rules never touch S or the verdict — stylometry stays pure,layering is explicit, like real gateways.
Detection definition for every recall/precision number:flagged = ALERT OR (TRIAGE ∧ content_escalation); caught = flagged.Stated verbatim in metrics.json; alert-only recall is additionallyreported for tiers A/B/C so stylometric performance is separable fromthe routing layer.
Claim discipline: the in-sample calibration line is an implementationsanity check (the plug-in p-value is ~rank-uniform for any exchangeablescore — it verifies arithmetic, not the model). The holdout line is theevidence; the gap is measured style drift, reported as a finding. Oneextra sentence: LOO nulls use n−1-email profiles, slightly inflating them, sodeployment p-values are mildly conservative (FPR ≤ α). We claim exactly thisand nothing more.

6. Forged test set — 3 tiers + the evasion play
Tier	What it is	Why it exists
A. relabel	Other senders' holdout mail attributed to the target	The brief's minimum; easy case
B. generic	LLM-written BEC asks (wire, gift cards, payroll)	Today's default attack
C. styled	Attack written after reading 3 real target emails	The hard case; proves depth
— short	15–30-word wire request	The evasion play: forces TRIAGE + escalation
C-audit	5-gram / longest-common-substring copy check on tier C	Ensures tier C measures style, not copying
7. Evaluation protocol
Two FPR variants, never summed or averaged, each at α ∈ {0.02, 0.05,0.10}, in-sample ("sanity") and holdout ("evidence"):FPR_alert = ALERT rate on genuine holdout — the conformal claim,used only for the calibration plot and sanity line;FPR_flagged = flagged rate (both TRIAGE reasons count) — theoperational false-alarm burden. Calibration plot lines are alert-only.
Recall per tier under the flagged rule (A/B high, C moderate — own it;C with and without copy-tagged forgeries; alert-only also reported forA/B/C; tier short counted as caught via routing).
Precision: on the curated demo inbox only (flagged rule), AND atrealistic prevalence with one rule on both sides:Precision(π) = R_flagged·π / (R_flagged·π + FPR_flagged·(1−π)) atπ = 1% and 10% (R_flagged pooled across forged tiers, pooling stated inmetrics.json), plus flags per 100 genuine emails = 100·FPR_flagged.
Routing-layer cost: escalation rate on genuine holdout, overall ANDsplit by TRIAGE reason (too short / insufficient history); holdout FPRbucketed by length (40–60 words vs 60+).
Per-sender table with the worst sender highlighted.
FP autopsy: top-5 flagged genuine holdout emails + broken habits + drift.
Baselines (same splits, thresholds tuned on train-only inner slice,same routing layer as GhostPen — shared infrastructure, not a method):
Method	FPR_alert@0.05 (in/held)	FPR_flagged@0.05	Recall A (flag)	Recall B (flag)	Recall C (flag)	Prec.
GhostPen (per-sender null)						
TF-IDF centroid + threshold						
Same S, global threshold						
Alert-only recall per tier lives in metrics.json alongside the flaggednumbers; the table shows flagged so the comparison is like-for-like.

8. Demo script (2 minutes)
make demo → inbox of "Marcus Hale (CFO)", 14 messages, all look normal.
Genuine message → green OK, p ≈ 0.4, habits intact.
Forged message → red ALERT, p < 0.01, habit cards: "0 '!' in his last 214emails; 2 here" · "signs 'thx' 95% — this says 'Kind regards'" ·"contractions 1.9/100w → 0" · "formality +2.3σ above his norm".
"ok thx" one-liner → TRIAGE, gauge shows "abstained (n/a)" with thetoo-short line, no escalation: "not suspicious, just unjudgeable."
The closer: a 22-word forged wire request → TRIAGE chip + redcontent strip + "stylometry abstains — content controls catch." Line tosay: "The attacker's smartest move is to write almost nothing. Our answeris layered: stylometry abstains loudly, and the mail routes to paymentverification."
Move the α slider → whole inbox re-verdicts live; low-history sendersdrop into TRIAGE (gauge line switches to the insufficient-historywording). Line to say: "False positives cost money, so we made FPR adial, not a hope."
If Streamlit ever breaks: make demo-cli prints the same verdicts to theterminal; python -m src.cli --sender "Marcus Hale" --file any.txt workson arbitrary input.
9. Repo & run
pip install -r requirements.txt   # pinned versionsmake demo        # Streamlit inbox (no network, instant — artifacts committed)make demo-cli    # terminal fallback demomake evaluate    # metrics.json + plots + fp_autopsy.jsonmake rebuild     # regenerate artifacts from data/prepared (JSON byte-identical)make test        # smoke tests on synthetic fixtures
10. Milestones (~17.5h)
#	What	Effort
M1	Scaffold, pinned deps, Makefile, README skeleton	0.5h
M2	Committed Enron subset, senders.json, rebuild script	2h
M3	Features + habit ledger (robust stats) + full LOO null	3.5h
M4	Scoring + CLI + tests (all must pass)	2.5h
M5	Forged set: relabel/generic/styled/short + copy-audit fixtures	1.25h
M6	Evaluation + baselines (both FPR variants) + FP autopsy	3h
M7	Streamlit app + demo-cli (14 messages, escalation beat)	3h
M8	Hardening: second run, weird inputs, README + expected-output	1.5h
11. The 5-page PDF (what actually gets graded)
p1 Title — GhostPen. "Your CFO's writing style is a password." Team,repo link, optional 90-second demo video link.
p2 Objective — BEC = multibillion-dollar reported losses; SPF/DKIMprove the domain, not the person; buyer = SOC / mail-gateway vendors;why now: GenAI made impersonation fluent and cheap.
p3 Solution — pipeline diagram; habit ledger; target-null p-values(conformal framing); direction; abstain-and-route with the separate contentlayer; α dial.
p4 Validation — chronological split, leakage discipline, 3-tier ladder
copy audit, baseline table (shared routing layer, alert & flagged),calibration plot labeled sanity/evidence (alert-only lines).
p5 Results & conclusions — metrics incl. precision-at-prevalence,FP autopsy + drift finding, honest limits (styled tier, low-volume,short-mail routing, char-3-gram topic sensitivity, English-only), roadmap(rolling profiles, multilingual), and a two-line AI-assistance disclosurebox (tool named + role; human design/evaluation decisions).
12. Pitfalls (each is a scored error)
Train/test leakage (evaluate only on the 30% holdout; tune baselines ontrain-only inner slice; IDF on training mail only).
Zero-variance blowup — stds must be floored, |z| capped.
Claiming holdout FPR = α — in-sample is a sanity line only; drift is real.
Presenting an unlabeled in-sample calibration curve as model evidence.
Mixing decision rules in one formula (R_flagged with FPR_alert in theBayes precision — both sides must use the flagged rule).
Giving GhostPen a routing layer the baselines lack — the layer is sharedinfrastructure or the comparison is rigged.
Testing only against relabelled mail — inflated, judges notice.
Tier-C forgeries that copy — audit or don't publish the claim.
Short-message TRIAGE presented as a benign verdict instead of routing.
Escalation tied to only one TRIAGE cause — it must be reason-agnostic.
Counting only ALERT as detection — caught = flagged; alert-only recall isthe additional number, not the headline.
MAD without a floor; byte-comparing PNGs in a determinism test.
Pooling holdout+forgeries into one precision number (double-labeled mail).
Depending on network or a big download at demo time.
Overcomplicating. No neural nets; explainability IS the feature.
13. Considered and rejected (one slide of depth)
Fisher combining of per-family p-values — same validity, more machinery.
Embedding similarity — opaque, model/network dependency; the baselinetable makes the point without it.
Neural stylometry — data-hungry, unexplainable, unnecessary at n≈100.
Global threshold — kept as Baseline B to measure why it loses.
Merging content flags into the verdict — rejected: keeps the stylometricscore pure and auditable; content lives in a clearly-labeled escalationlayer, exactly like layered controls in production mail security.
Appendix — 60-second glossary
z-score: how many of his own standard deviations from his average.
Winsorize: clip extreme values (5/95) so one bad parse can't poison stats.
Burrows' Delta: classic authorship method — compare frequencies ofunconscious habits; gold standard since 2002.
Target-null calibration: leave-one-out conformal p-value over thesender's own mail; the client-side analogue of cohort scoring in speakerverification. Validity: P(false alert) ≤ α under exchangeability; mildlyconservative because LOO profiles are one email smaller.
p-value: probability a genuine email of his would score this extreme.
p_min = 1/(N+1): smallest achievable p — sets the alerting floor⌊1/α⌋ training emails.
Burstiness: variance in sentence length. Humans are bursty; LLMs uniform.
TTR: type-token ratio, vocabulary richness.
Base rate: why precision at 1% attack prevalence, not a 50/50 inbox,is the honest deployment number.
Alert vs flagged: alert = the stylometric verdict (p < α); flagged =what the SOC actually sees — alerts plus TRIAGE-with-escalation. Recall,precision and operational FPR use flagged; the calibration claim usesalert only.
Reject option / abstain-and-route: a classifier that may decline todecide and route the case elsewhere — standard pattern when a wrong callin either direction is costly.