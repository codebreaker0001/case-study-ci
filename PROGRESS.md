# Progress

## Current status

Stage 1 (Project setup) complete. Stage 2 decisions confirmed below; no
analysis or generation code written yet. Waiting for Stage 2 instructions.

## 1. Project setup

- [x] Folder structure created
- [x] CASE.md, CLAUDE.md, PROGRESS.md in place
- [x] .gitignore, .env.example, requirements.txt, README.md in place
- [x] Git initialized, first commit made

## 2. Synthea base patients

- [ ] 

## 3. Program overlay + calibration

- [ ] 

## 4. Metrics + gap bridge

- [ ] 

## 5. Unified definition + data-quality checks

- [ ] 

## 6. LLM extraction (Groq)

- [ ] 

## 7. Friday report

- [ ] 

## 8. HTML view + slide deck

- [ ] 

## Decisions log

- **Base patient source**: Use Synthea's cancer modules (breast, colorectal,
  lung — confirm exact module names/availability when Synthea is run in
  Stage 2) so patients carry real diagnosis dates and death dates, which
  drive dropout/progression naturally. Fallback: if the cancer modules yield
  too few usable patients, generate a plain demographic Synthea population
  and assign the oncology indication (diagnosis date, stage, mortality risk)
  in the program overlay instead. The overlay (enrolments, hub fills, CRM
  notes) is built entirely in `src/generate`, independent of which fallback
  path is used.

- **Synthea population size**: Provisional target of **100,000** raw Synthea
  patients, configurable (not hardcoded). Reasoning: published Synthea
  module lifetime risk is roughly ~12% for breast cancer (women), ~6-7% for
  lung, ~4-5% for colorectal, giving a rough population-wide estimate of
  ~11-12% of all simulated patients ever receiving one of these three
  diagnoses over their simulated lifetime. Not all of those are usable —
  many are diagnosed long before our enrolment window or already deceased
  by then — so a ~50% usability discount is assumed. That implies needing
  roughly 6,000-7,000 raw cancer-diagnosed patients to comfortably source a
  3,000-3,500-patient enrolled cohort (see population size below), which at
  ~11-12% incidence means a raw population on the order of 55,000-65,000;
  100,000 is chosen to leave margin. This estimate is unvalidated against
  actual Synthea output and will be checked empirically in Stage 2 — if the
  yield is far off, the population size will be adjusted and this entry
  updated with the real number.

- **Enrolled cohort size**: Target ~2,000-2,500 patients *active* per
  quarter (per your instruction, for ~±1pt sampling noise). Because
  patients persist across quarters and attrite via death/discontinuation,
  the total unique ever-enrolled cohort needs headroom above that, targeted
  at ~3,000-3,500 unique patients enrolled across the full 4-quarter window.

- **Quarter structure**: Generate 4 quarters total — 2 history quarters (Q1,
  Q2) plus the 2 quarters from Exhibit 2 (Q3 = "last quarter" = 64%/72%,
  Q4 = "this quarter" = 58%/71%). Only Q3 and Q4 are calibrated to match
  Exhibit 2; Q1-Q2 should look plausible with the drift (pipeline declining
  faster than CRM) starting gradually, not jumping straight to the Q3/Q4
  gap. Patients are generated once and persist across quarters (enrol,
  then fill/lapse/pause/discontinue over time) rather than being
  regenerated per quarter.

- **Quarterly population membership rule**: A patient counts in quarter Q's
  population (the pipeline's "all enrolled patients" definition) if:
  `enrollment_date <= Q_start` AND `(disenrollment_date is null OR
  disenrollment_date > Q_start)` AND `(death_date is null OR death_date >
  Q_start)`. I.e. population is a beginning-of-quarter snapshot: a patient
  must be enrolled on or before quarter start to count, and leaves the
  count starting the quarter after they die or formally disenrol. A patient
  who dies or discontinues *during* quarter Q still counts in Q's
  population and their partial coverage (fewer days-on-hand out of the full
  quarter) naturally pulls PDC down for that quarter — this is the intended
  mechanism for realistic, non-hardcoded adherence decline. The CRM
  dashboard's narrower population ("≥1 specialty pharmacy fill") is the
  same membership rule intersected with "has at least one hub fill record
  on or before Q_end".
