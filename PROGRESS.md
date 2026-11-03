# Progress

## Current status

Stage 2 (Synthea base patients) complete at a reduced population size of
5,000 (deliberately scaled down from the ~150k-280k the math called for, to
get the pipeline working first -- see Decisions log). 242 cancer patients
extracted and cached. Waiting for Stage 3 instructions.

## 1. Project setup

- [x] Folder structure created
- [x] CASE.md, CLAUDE.md, PROGRESS.md in place
- [x] .gitignore, .env.example, requirements.txt, README.md in place
- [x] Git initialized, first commit made

## 2. Synthea base patients

- [x] Verified Java 21 (Temurin) meets Synthea v4.0.0's min JDK 17 requirement
- [x] scripts/run_synthea.py: downloads jar, runs Synthea, writes raw CSVs to git-ignored data/synthea_raw/
- [x] Test run (100, then 300 people) confirmed the pipeline and CSV-restriction both work
- [x] 10,000-patient calibration run to empirically measure cancer incidence
- [x] Full generation run at population_size=5,000 (scaled down from the math-derived target, see Decisions log)
- [x] src/generate/synthea_base.py: builds the clean one-row-per-cancer-patient base table, with cache fallback
- [x] Cached extract saved to data/synthea_seed/cancer_patients_base.csv (242 rows, 24KB, committed)
- [x] DATA_LINEAGE.md written
- [x] tests/test_synthea_base.py: 5 tests, all passing (no dup IDs, every row has a diagnosis, dates valid, multi-diagnosis rule, cache-only loader)

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

- **Synthea population size (superseded, see Stage 2 entries below)**:
  Provisional target of 100,000, based on published lifetime-risk
  percentages rather than Synthea's actual module behavior. Stage 2
  measured the real incidence empirically (496/10,000 = 4.96%, well below
  the ~11-12% assumed here) and replaced this estimate.

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

### Stage 2 decisions

- **Synthea version**: Pinned to v4.0.0 (latest tagged release), requires
  JDK 17+; local Java 21 (Temurin) is compatible. Jar downloaded from the
  GitHub release asset and cached in git-ignored `data/synthea_jar/`.

- **No `-m` module restriction**: Synthea's `-m` flag filters which modules
  load, but the official wiki documents it as a debugging aid that "will
  break modules, because many of them have dependencies" and is explicitly
  "not a way to make every patient have a given condition." Running it
  restricted to only the three cancer modules risks silently breaking
  submodule dependencies. Decision: run Synthea's full default module set
  (single state, Massachusetts) and filter for the three cancer types in
  post-processing (`src/generate/synthea_base.py`), using exact SNOMED
  codes read from the module source (see DATA_LINEAGE.md) rather than
  text-matching condition descriptions.

- **CSV export restricted to 2 files**: Synthea's CSV exporter writes 18
  tables by default (claims, claims_transactions, observations, imaging,
  procedures, etc.) totaling >7GB for just 10,000 patients, with no
  per-table toggle in the docs. Found `exporter.csv.included_files` in the
  exporter source (`CSVFileManager.java`) — a comma-separated whitelist —
  and set it to `patients.csv,conditions.csv`, which is all the base table
  needs. This does not change generation time (that's simulation-bound,
  not I/O-bound) but avoids writing/storing tables we never use.

- **Empirical incidence (measured on a 10,000-patient calibration run,
  Massachusetts, seed 42, reference date 2026-09-01)**: 496/10,000 (4.96%)
  of requested population had >=1 confirmed diagnosis among the three
  cancer types (breast 193, colorectal 214, lung 99 — not mutually
  exclusive before the earliest-diagnosis rule is applied). Of those, only
  50.8% were still alive at the reference date; just 13.5% were diagnosed
  within 3 years of it (most cancer diagnoses in a full-lifespan simulation
  are old). This is well below the ~11-12% assumed in the earlier
  provisional estimate above — lifetime-risk percentages from general
  medical literature do not equal Synthea's actual simulated incidence.

- **Population size: scaled down to 5,000 for now (user decision)**. The
  math above (needing ~7,000 alive-at-reference cancer patients for a
  3,000-3,500 enrolled cohort with margin) implies a full population of
  ~278,000, estimated at ~8.5 hours of simulation time (linear scaling from
  the 10k calibration run's ~19 minutes; CSV restriction doesn't change
  this since it's CPU-bound). Given these runtime options, the user chose
  to run only 5,000 patients now to get Stage 2 working end-to-end, with
  explicit intent to scale up later. Scaling up is a one-line change
  (`population_size` in `config/synthea_run.json`, or a CLI override to
  `scripts/run_synthea.py`) plus re-running; `scripts/calibrate_population.py`
  can re-derive the incidence/recency numbers from any new raw output.
  Result at n=5,000: 242 cancer patients (breast 96, colorectal 103,
  lung 43), 109 with a death date, ages 18-110 (mean 71.1 as of reference
  date).

- **"Age" column caveat**: computed as `(reference_date - birth_date) //
  365`, i.e. age as of 2026-09-01 regardless of death date. For deceased
  patients this is a hypothetical "age if still alive today," not age at
  death or at diagnosis. Flagged in DATA_LINEAGE.md; revisit if Stage 3
  needs age-at-diagnosis or age-at-death instead.

- **Multiple-diagnosis rule**: if a patient has condition rows matching
  more than one target cancer type (or multiple stage-progression rows of
  the same type), `cancer_type` and `diagnosis_date` are taken from their
  EARLIEST matching row — their first/index cancer. Implemented and tested
  in `src/generate/synthea_base.py` / `tests/test_synthea_base.py`.

- **Known data-quality artifact (not fixed in Stage 2)**: a handful of
  patients (e.g. one diagnosed with breast cancer at 323 days old) have
  implausibly young ages at diagnosis — a Synthea module quirk, not a bug
  in our extraction. Left in the base table as-is since Stage 2's job was
  a clean *column* extraction, not plausibility filtering. Candidate for a
  Stage 5 data-quality check (e.g. flag/exclude diagnosis age < 18) or a
  Stage 3 filter when building the enrolled cohort.
