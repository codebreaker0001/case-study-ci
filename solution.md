# Solution Document: Adherence Reporting Discrepancy

## 1. Solution overview

The client has two adherence numbers that don't match. Our pipeline says 58% this quarter (64% last quarter), and the client's CRM dashboard says 71% (72% last quarter). I found that the two numbers count different patients, use different measures and come from different data sources, so they were never measuring the same thing. I built a synthetic dataset that reproduces these numbers, broke the gap into its three causes, and used an LLM to read case-manager notes. My main result is: **most of the consistent, non-noisy part of the gap comes from patients who enrolled but never got their first fill (first-fill abandonment roughly doubled, 6.0% -> 11.0%, this quarter), and the number I would report on Friday is 68% (range ~65-71%), the unified definition computed among patients who actually started therapy.**

## 2. Approach and methodology

1. **Created patients with Synthea.** I used Synthea to generate realistic patients and kept only those with breast, lung or colorectal cancer.
2. **Increased the number of patients.** Synthea gave only 242 cancer patients, so I resampled them up to 5,000 with small random changes to age and survival time.
3. **Simulated the support program.** I added enrolments, pharmacy fills, treatment pauses, drop-offs and case-manager notes on top of these patients.
4. **Matched the case numbers.** I adjusted the simulation settings until both metrics came close to 58/71 and 64/72 (landed within ~1-3.5pts; see Evaluation).
5. **Built the gap bridge.** I changed one thing at a time (population, then measure, then source) to see how much each one adds to the gap, and also computed a Shapley-style average over all orderings so the result isn't sensitive to which factor I apply first.
6. **Used an LLM on the notes.** I used Groq to pull out missed doses, delays, pauses and discontinuation reasons from the free-text notes, and checked how accurate it was.
7. **Proposed one definition.** Unified = PDC>=80% from hub fills, among patients with >=1 fill, excluding clinician-directed hold days from the denominator. First-fill abandonment is reported as a separate number, not folded in, because it's an access problem, not an adherence problem. I also added 6 pass/warn/fail data-quality checks to warn if the two systems drift apart again.
8. **Prepared the Friday number.** 68% (range ~65-71%), based on where the unified metric lands (68.1% this quarter) and how much it's moved quarter over quarter (68.3% -> 68.1%, i.e. barely).
9. **Built an HTML view.** It shows the gap bridge, with a quarter toggle, a sequential/Shapley toggle, and cohort filters (cancer type, region, payer type, case manager) that recompute everything client-side.

## 3. How I arrived at it

**Things I considered but didn't do:**
- **Just picking one number as "right".** I didn't do this because each number answers a different question.
- **Running Synthea for 278,000 people.** This would have given enough cancer patients, but it would take too long (~8.5 hours estimated from a 10k-patient timing run). I moved each patient's dates into our time window and resampled instead.
- **Using an LLM to write the notes.** I used templates instead, so the LLM isn't tested on its own writing.
- **Mixing "never started therapy" into adherence.** I kept it as a separate number, because it's an access problem, not an adherence problem.

**Assumptions:**
- "This quarter" = Q4 of the simulated 4-quarter window (ending 2026-09-01); "last quarter" = Q3.
- Patients take an oral cancer drug with a 28 or 30-day supply.
- The gap grew this quarter because of a modeled insurance prior-authorization policy change that disproportionately stopped newly-enrolled patients from getting their first fill (first-fill abandonment rose from 6.0% to 11.0%).

**Clarification Desk answers used:** none -- no clarification channel was available in this session; the decisions above were made and documented in PROGRESS.md's Decisions log as they came up, with the user confirming direction at each stage (population size, quarter structure, deadline-mode scope cuts).

## 4. Data

- **Synthea:** 5,000 people generated, which gave 242 cancer patients (103 colorectal, 96 breast, 43 lung). I removed 8 with unrealistic ages, such as a cancer diagnosis in a baby (323 days old).
- **Resampling:** I copied the remaining 234 patients up to 5,000, keeping the same cancer mix (44.0% colorectal / 37.6% breast / 18.4% lung, matched within rounding) and adding small changes (age jitter +/-3yr, survival-interval scaling 0.8-1.2x) so the copies aren't identical.
- **Program data:** simulated enrolments, pharmacy fills and CRM notes. Active population per quarter: Q1=3,615-3,649, Q2=3,845-3,881, Q3=4,069-4,146, Q4=4,308-4,345 (ranges reflect pipeline vs. filler-only denominators across my calibration passes; final run ~4,116/4,337 pipeline population for Q3/Q4).
- **Ground truth:** for every note, I saved the true answer (missed dose, delay, pause and so on) in `data/ground_truth_notes.csv`, used only to check the LLM -- the metrics code never reads this file.

**Limitations:**
- Many patients are copies of the same 234 profiles, so there is less variety than real data.
- The program behaviour is based on my own assumptions, not real data. In particular, synthetic fills represent coverage blocks (how many days were covered) rather than literal pharmacy refill timestamps, which makes the bridge's "measure effect" and "source effect" steps noisier between quarters than the headline pipeline/CRM numbers (see Evaluation).
- The notes are simpler than real notes, so the LLM may look more accurate here than it would in real life.

## 5. Evaluation

- **Matching the case numbers:** Q3 pipeline=62.2% (target 64%, off -1.8pts), Q3 CRM=70.7% (target 72%, off -1.3pts); Q4 pipeline=59.2% (target 58%, off +1.2pts), Q4 CRM=67.8% (target 71%, off -3.2pts). All four within the ±3.5pt band I used as a practical stopping point after several calibration passes.
- **Gap bridge (Shapley, more stable than sequential across orderings):** Q3: population +3.6pts, measure +14.1pts, source -9.2pts. Q4: population +6.0pts, measure +2.8pts, source -0.2pts. The population effect is the only one that grows consistently and directionally (3.6 -> 6.0pts); measure and source swing a lot between quarters and partly cancel, which I attribute to the coverage-block fill simulation (see Limitations) rather than a real phenomenon -- I would not present the measure/source split to the VP with the same confidence as the population effect.
- **LLM accuracy (150 labelled notes, Groq `openai/gpt-oss-120b`):** missed_doses P=1.00/R=0.68/F1=0.81; delay P=0/R=0/F1=0 (only ~0.5% prevalence, none landed in this sample -- not a model failure, a sampling artifact); discontinued P=1.00/R=0.60/F1=0.75; therapy_hold and hold_clinician_directed both P=1.00/R=0.75/F1=0.86. Agreement with an independent fill-derived gap signal: 80.8%. The rule-based fallback scored identically on this sample, which given template-generated notes isn't surprising -- a real deployment would need to re-validate on natural language.
- **Final number with range:** 68% (unified metric, Q4), range ~65-71%. This range is a judgment call bounded by (a) the unified metric's own quarter-to-quarter movement (68.3% -> 68.1%) and (b) the CRM metric at 67.8%, which the DQ checks say is itself compromised by 69% flag staleness -- not a formal bootstrap CI (that step, the Friday memo, wasn't completed before the deadline; see Limitations).
- **Data-quality checks:** evaluated using only data as of Q3 (before this quarter's board presentation) -- 2 warn (hub vs CRM divergence 8.5pts, patient-level disagreement 28.5%), 2 fail (CRM flag staleness 69%, implausible age at diagnosis in the raw Synthea extract), 2 pass (CRM note coverage, enrolled-without-fill trend). The two fails would have been actionable before this quarter.
- **Tests:** bridge-sums-to-gap (the sequential steps add up exactly to pipeline-minus-CRM) and calibration-within-tolerance, plus tests kept from earlier stages (Synthea base-table extraction, augmentation resampling). 9 tests passing.

**How the mid-session update changed my solution:** the original plan (asked in a separate step) was to run Synthea at ~150k-278k patients for full statistical power; a mid-session deadline instruction cut this to 5,000 patients plus resampling, and later moved from a stage-by-stage review process to a single uninterrupted build-and-commit sequence across all pipeline stages (overlay, metrics, bridge, HTML, unified/DQ, LLM extraction), skipping the Friday memo and slide deck that were originally planned.

## 6. Tech stack

- **Language:** Python 3.14 (dev machine; targets 3.11+)
- **Libraries:** pandas, numpy, pydantic, groq, python-dotenv, pytest
- **Synthetic data:** Synthea v4.0.0 (Java, JDK 21 Temurin)
- **LLM:** Groq, model `openai/gpt-oss-120b`
- **Charts:** HTML with Chart.js (CDN)
- **Coding assistant:** Claude Code (Anthropic), model Claude Sonnet 5

## 7. Use of LLMs

I used the LLM to read case-manager notes and find missed doses, delays, treatment pauses and discontinuation reasons. I used an LLM instead of simple keyword rules because the notes have abbreviations, typos and phrases like "no missed doses", which keyword rules can get wrong. I also built a keyword version to compare against; on this synthetic, template-generated sample the two scored identically, which doesn't demonstrate an LLM advantage -- it would need testing on more naturalistic notes to show the gap keyword rules can't close.

To keep the LLM reliable, I asked for a fixed JSON format, set temperature to 0, and checked its answers against the ground truth and the pharmacy fill data.

**Where it can go wrong:** misreading "no" or "maybe", mixing up planned and past pauses, and guessing numbers that aren't in the note. Confirmed from results: recall is the weak point (60-75% per signal, not precision, which was 100% on this sample) -- the model/rules under-call events more than they over-call them, which for a program-ROI narrative means the true problem rate is likely at least as bad as reported, not better.

## 8. Limitations and next steps

- The data is synthetic, so the next step would be to run the same analysis on the client's real data.
- **Privacy:** real notes contain patient information, so they should not be sent to an outside LLM without the right agreements, or they should be anonymised first.
- **Security:** API keys should be stored securely (`.env`, gitignored, never committed -- verified in this project), and access to patient-level data should be limited.
- **Monitoring:** the data-quality checks should run every time new data comes in, and the LLM should be re-checked regularly.
- **Agreement:** the client's teams should all agree on the one definition before it goes to the board.
- **Not completed before the deadline:** `outputs/friday_memo.md` (bootstrap CIs, sensitivity ranges) and `outputs/deck.pptx` (slide deck) were not built -- the Friday number and range above are a judgment call, not a formal statistical interval.

## 9. Submission index

| File | What it is | How to run |
|---|---|---|
| `solution.md` | This document | Read |
| `README.md` | Setup instructions | Read |
| `run_all.py` | Runs the whole project | `python run_all.py` |
| `requirements.txt` | Python packages | `pip install -r requirements.txt` |
| `.env.example` | Where to put the Groq API key | Copy to `.env` and add your key |
| `data/synthea_seed/` | Saved Synthea patients | Used automatically |
| `src/` | All the code | Run through `run_all.py` |
| `outputs/reconciliation.html` | The interactive gap view | Open in a browser |
| `outputs/bridge.json`, `outputs/unified_metric.json`, `outputs/dq_results.json`, `outputs/extraction_eval.json` | Underlying numbers behind the HTML view | Read, or regenerate via `run_all.py` |
| `tests/` | Tests | `pytest` |

Not produced: `outputs/friday_memo.md`, `outputs/deck.pptx` (see Limitations).
