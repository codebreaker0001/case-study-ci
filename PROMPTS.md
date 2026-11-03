# Prompts Used

These are the prompts I gave Claude Code to build this project, in the order I used them. I built the project one stage at a time, reviewing Claude's report after each stage before moving on.

---

## Stage 1: Project setup

```
I'm starting a case study project. In this first step, set up the project foundation only. Do not write any analysis code yet.

## The case

Role: I'm an onshore Forward Deployed Engineer on a pharma account (oncology patient support program, market access).

Key terms:
- Adherence: whether patients take their medicine as prescribed over time
- PDC (proportion of days covered): share of days in a period with medicine on hand, computed from pharmacy fill records
- Specialty pharmacy hub: collects fill records from specialty pharmacies in one place
- CRM: system where the client's case managers record notes about patients
- Patient support program: manufacturer-run program that helps patients start and stay on therapy

Situation: 18 months ago my team built an adherence pipeline from specialty pharmacy hub fills and program enrolment records. The client's BI team separately built a CRM-based dashboard. The two disagree. The VP of Market Access presents program ROI to the board on Friday and asks which number is right.

Exhibit 1: Definitions
| | Our pipeline | Client CRM dashboard |
|---|---|---|
| Population | All enrolled patients | Patients with at least 1 specialty pharmacy fill |
| Measure | PDC of 80% or more | "Refilled on schedule" flag, self-reported by case managers |
| Source | Specialty pharmacy hub fills | Case-manager notes in the CRM |

Exhibit 2: Adherence, quarter over quarter
| | This quarter | Last quarter |
|---|---|---|
| Our pipeline | 58% | 64% |
| Client CRM dashboard | 71% | 72% |

Requirements:
1. Generate a synthetic patient-level dataset with enrolments, hub fills and CRM case-manager notes, including free-text notes. Its aggregates must roughly reproduce Exhibit 2.
2. Compute both metrics from that data and build a bridge that splits the gap into population, measure-definition and data-source effects, for both quarters.
3. Use an LLM to extract adherence signals (missed doses, delays, discontinuation reasons) from the free-text notes, and measure how well the extraction agrees with fill data on a labelled sample.
4. Propose a unified adherence definition and implement it, with data-quality checks that would catch the two sources drifting apart again.
5. Show what is defensible to report on Friday, with the uncertainty attached.

Deliverables: runnable code, the synthetic data generator, an HTML reconciliation view (gap bridge, cohort filters, quarter toggle), and an optional slide deck of 8 slides or fewer.

My tool choices: Synthea (open-source synthetic patient generator) as the base for patient data, and the Groq API for the LLM.

## What to do now

1. Save the case above, word for word, as CASE.md.

2. Create the folder structure: src/ (with subfolders generate, metrics, bridge, extract, unified, dq, report, viz), data/, outputs/, scripts/, tests/.

3. Create CLAUDE.md (under ~80 lines) with:
   - A short project summary and a pointer to CASE.md and PROGRESS.md
   - Stack: Python 3.11+, pandas, numpy, pydantic, groq SDK. Java only needed to regenerate Synthea data.
   - The folder structure and what goes where
   - Rules: read CASE.md and PROGRESS.md at the start of every session; we build one stage at a time and you stop after each stage for my review; update PROGRESS.md after each task; run tests before marking anything done; use fixed random seeds; never hardcode target percentages; never put API keys in files; prefer simple, readable code.

4. Create PROGRESS.md with these 8 stages as headings, each with an empty checklist I'll fill in as we go:
   1. Project setup
   2. Synthea base patients
   3. Program overlay + calibration
   4. Metrics + gap bridge
   5. Unified definition + data-quality checks
   6. LLM extraction (Groq)
   7. Friday report
   8. HTML view + slide deck
   Add a "Current status" section at the top and a "Decisions log" section at the bottom.

5. Create .gitignore (including .env), .env.example containing GROQ_API_KEY=your_key_here, a starter requirements.txt, and a short README.md placeholder.

6. Initialise git and make a first commit.

7. Finally, explain back to me in plain language:
   - Your understanding of the problem and why the two numbers likely differ
   - What you think the hardest parts of this project will be
   - Any questions you have before we start Stage 2

Then STOP. Do not start Stage 2.
```

---

## Answers to Claude's questions after Stage 1

```
Answers:

1. Use Synthea's cancer-related modules (check which exist, e.g. breast, lung, colorectal) so patients have real cancer diagnoses, diagnosis dates and death dates, not just demographics. Use death and progression as natural causes of drop-off and of enrolled-but-never-filled patients. Build the program layer (enrolments, hub fills, CRM notes) entirely in src/generate. If the cancer modules yield too few usable patients, fall back to using Synthea for demographics only and assign the oncology indication in the overlay, but document that decision in the Decisions log.

2. Aim for roughly 2,000–2,500 patients active per quarter, so sampling noise is around ±1 pt and calibration within ±2 pts is stable. Cancer is rare in a general population, so work out how large a Synthea population is needed to get enough cancer patients, and make the population size configurable. Tell me the number you choose and why.

3. Generate 4 quarters: 2 quarters of history plus the 2 quarters in Exhibit 2. Calibrate only the last 2 quarters to Exhibit 2; the earlier quarters should look plausible and show the drift starting gradually. Patients should persist across quarters (enrol once, then fill, lapse, pause or discontinue over time) rather than being regenerated each quarter. Propose a clear rule for which patients count in each quarter's population, and include it in the Decisions log.

Don't start building yet. Confirm these decisions and record them in PROGRESS.md, then wait for my Stage 2 instructions.
```

---

## Stage 2: Synthea base patients

```
Stage 2: Synthea base patients. Read CASE.md, CLAUDE.md and PROGRESS.md first.

Goal: produce a clean base table of cancer patients from Synthea. Do NOT build the program overlay (enrolments, fills, CRM notes) yet; that's Stage 3.

1. Check the environment: is Java installed, and which version? Check the Synthea GitHub repo and wiki for the current release, the required Java version, CLI flags, how to enable CSV export, and which cancer-related modules exist. Don't rely on memory. Tell me what you found before running anything large.

2. Write scripts/run_synthea.py that:
   - Downloads the synthea-with-dependencies.jar release into a git-ignored folder if it isn't already there
   - Runs Synthea with settings from a config file: seed, population size, modules, CSV export, and US state/location
   - Saves raw output to a git-ignored folder (data/synthea_raw/)

3. Do a small test run first (about 100 people) to confirm it works. Then work out the population size needed to yield enough cancer patients for ~2,000–2,500 active patients per quarter across 4 quarters (remember, some will die, discontinue or never fill). Explain the maths, then run the full generation.

4. Write src/generate/synthea_base.py that reads the raw CSVs and builds a clean base table with one row per cancer patient: patient_id, birth date, age, sex, state/region, cancer type, diagnosis date, death date (if any). Keep only the columns we need. If a patient has multiple cancer diagnoses, pick a clear rule and document it.

5. Save this as a cached extract in data/synthea_seed/ (committed to git, so keep it small). The loader must use fresh Synthea output if it exists, otherwise fall back to the cache, and log which path it used.

6. Create DATA_LINEAGE.md with a table of each column, its source (Synthea), and the original Synthea file and field it came from.

7. Write tests: the base table has no duplicate patient IDs, every patient has a cancer diagnosis, dates are valid, and the loader works from the cache alone.

8. Update PROGRESS.md and the Decisions log, then commit.

9. Report back with:
   - The population size you used and why
   - Total cancer patients, broken down by cancer type
   - Age and sex distribution, and how many have a death date
   - The size of the cached extract
   - Anything surprising or problematic

Then STOP. Do not start Stage 3.
```

---

## Stage 2b: Augmenting the cancer patients

Synthea gave only 242 cancer patients, and a full-size run would have taken too long, so I resampled the existing profiles instead.

```
Change of plan: I'm on a tight deadline, so stop the 100k Synthea run (kill the background process) and don't wait for it. Keep the scaled-up config and code path as-is, so a future full run would be picked up automatically by the loader.

Instead, augment the existing cancer profiles. Keep this simple and quick:

1. Start from the current base table (~242 cancer profiles). Add age_at_diagnosis and days_diagnosis_to_death columns if they're not there yet. Exclude implausible profiles (age at diagnosis under 18 or over 95) and report how many were dropped.

2. Write src/generate/augment.py that resamples the remaining profiles with replacement to a target of 5,000 patients (configurable), stratified by cancer type so the original type mix is preserved. Use a fixed seed.

3. For each new patient:
   - Assign a new unique patient_id, and keep a source_synthea_id column pointing to the original profile
   - Jitter age_at_diagnosis by a random integer from -3 to +3 years, clipped to 18–95
   - If the source profile died, keep the death but scale days_diagnosis_to_death by a random factor between 0.8 and 1.2
   - Keep sex and cancer type from the source; keep state/region from the source
   - Add is_augmented = True

4. Save the augmented table to data/synthea_seed/ (keep it small) and make it the table Stage 3 will use.

5. Add a row to DATA_LINEAGE.md and a Decisions log entry in PROGRESS.md: "Clinical profiles from Synthea (n≈242); volume from stratified resampling with jitter to n=5,000, due to time constraints. Limitation: profiles repeat with small variation, so the data has less clinical diversity than a full Synthea run. A full run would remove this limitation by changing one config value."

6. Add 2 quick tests: the patient_id is unique, and the cancer type mix is within 2 pts of the source mix. Commit.

7. Report back briefly: final count by cancer type, the number dropped as implausible, the share with a death date, and median age at diagnosis.

Time-box this to about 10 minutes. Then STOP.
```

---

## Stage 3: Program overlay + calibration

```
Stage 3: program overlay + calibration. Read CASE.md, CLAUDE.md and PROGRESS.md first. Use the augmented 5,000-patient base table from Stage 2.

Goal: simulate the patient support program on top of the base patients so that both legacy metrics roughly reproduce Exhibit 2. Do NOT build the bridge yet; that's Stage 4.

1. Timeline: use 4 quarters, Q4 2025 to Q3 2026, with Q3 2026 = "this quarter" and Q2 2026 = "last quarter" in Exhibit 2. Re-anchor each patient's diagnosis date into or shortly before this window, preserving age at diagnosis and the diagnosis-to-death interval. Spread enrolments so roughly 2,000–2,500 patients are active in each quarter. Patients persist across quarters.

2. Simulate each patient's journey in src/generate/overlay.py:
   - Program enrolment (date, payer type, indication = cancer type, assigned case manager)
   - First fill or abandonment (reasons: prior-auth denial, cost, switched therapy, progression or death before start). Make the prior-auth denial rate rise in Q3 2026 because of a payer policy change. This is the main driver of the widening gap; document it.
   - Refill cycles of 28 or 30 days supply, with realistic late refills (missed doses), clinician-directed toxicity holds, discontinuation, and death
   - Case-manager CRM notes every few weeks per active patient, each with a "refilled on schedule" flag. Simulate case-manager behaviour: some are more optimistic than others, flags sometimes carry over stale from the previous note, and some patients have missing or late notes.
   - Free-text notes generated from templates with random variation: abbreviations (pt, d/c, PA, tx, onc), occasional typos, mixed signals, and some notes with no adherence info. Notes must reflect what actually happened to the patient (holds, missed doses, delays, discontinuation reasons). Do NOT use an LLM to write notes.

3. Save the outputs:
   - data/enrolments.csv
   - data/hub_fills.csv: fill_id, patient_id, fill_date, days_supply, pharmacy
   - data/crm_notes.csv: note_id, patient_id, note_date, case_manager, refilled_on_schedule, note_text
   - data/ground_truth_notes.csv: note_id, missed_doses, delay, discontinued, discontinuation_reason, therapy_hold, hold_clinician_directed
   - data/ground_truth_patients.csv: true per-patient behaviour
   The metrics code must NEVER read the ground truth files. Add a test that enforces this (e.g. grep src/metrics for "ground_truth").

4. Implement both legacy metrics in src/metrics/ exactly per Exhibit 1, per quarter:
   - Pipeline: all patients enrolled and active in the quarter; adherent if PDC ≥ 80% from hub fills. Standard PDC rules: overlapping fills roll forward, the period is truncated at death, never-filled = PDC 0.
   - CRM: patients with ≥1 hub fill; adherent if their latest CRM "refilled on schedule" flag in the quarter is true (decide how to treat patients with no note in the quarter and document it).
   Write down the exact rule for "active in the quarter" in the Decisions log.

5. Put all simulation parameters in one config file (config/overlay.yaml or .json) with a comment explaining each. Calibrate by tuning these parameters (a simple search is fine), NOT by forcing outputs. Target within ±2 pts: pipeline 58% (Q3) / 64% (Q2), CRM 71% (Q3) / 72% (Q2). Q4 2025 and Q1 2026 should look plausible, with the gap starting to widen gradually.

6. Tests: calibration within tolerance; no duplicate IDs; fills never occur before enrolment or after death; metrics code never touches ground truth; PDC is correct on 3 tiny hand-built cases (perfect adherence, a 2-week gap, and never filled).

7. Update DATA_LINEAGE.md, PROGRESS.md and the Decisions log. Commit.

8. Report back with:
   - The calibration table: both metrics × 4 quarters, vs targets
   - Active patients per quarter
   - Never-fill (abandonment) rate per quarter, and the reasons breakdown
   - The final values of the key config parameters
   - 5 example CRM notes, with their ground-truth labels
   - Anything surprising or any compromises made



---


```
Read solution.md. Replace every [TBD: ...] placeholder with the actual values from this project: calibration results, bridge numbers, LLM metrics, the Groq model ID, library versions, confidence intervals, file names and test counts. Use exact numbers from outputs/ and PROGRESS.md. Don't change the section structure. Leave the Clarification Desk and mid-session update sections for me. List any placeholder you couldn't fill.
```
