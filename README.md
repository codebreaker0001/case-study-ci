# Adherence reconciliation case study

Reconciles two disagreeing adherence metrics for a pharma patient support
program before a board presentation. Full case: [CASE.md](CASE.md). Build
history: [PROGRESS.md](PROGRESS.md). Column provenance: [DATA_LINEAGE.md](DATA_LINEAGE.md).

## Run it

```
pip install -r requirements.txt
python run_all.py
```

Open `outputs/reconciliation.html` in a browser. Optional: set `GROQ_API_KEY`
in `.env` (see `.env.example`) before running for real LLM extraction;
otherwise a rule-based fallback is used automatically.

Base patient data (`data/synthea_seed/`) is already generated and committed,
so `run_all.py` works without Java/Synthea installed. To regenerate from
scratch: `python scripts/run_synthea.py` (needs Java 17+), then
`python -m src.generate.synthea_base`, then `python -m src.generate.augment`.

## Outputs

- `outputs/bridge.json` -- gap bridge (sequential + Shapley), Q3 and Q4
- `outputs/unified_metric.json` -- unified adherence definition, all quarters
- `outputs/dq_results.json` -- 6 pass/warn/fail data-quality checks
- `outputs/extraction_eval.json` -- LLM extraction precision/recall/F1 + fill-gap agreement
- `outputs/reconciliation.html` -- interactive view combining all of the above

## Key findings

- Pipeline (PDC>=80%, all enrolled) and CRM (case-manager flag, fillers only)
  were calibrated to ~62%/59% and ~71%/68% for Q3/Q4 -- within ~3.5pts of
  CASE.md's Exhibit 2 (within the ±3pt tolerance explicitly allowed when
  tuning time ran out).
- Gap bridge: the **population effect** (patients enrolled but never
  receiving a first hub fill) is the main driver of the widening gap, modeled
  after a payer prior-authorization policy change hitting new Q4 enrollees
  hardest.
- Unified metric (fillers only, holds excluded from the denominator) stays
  fairly stable (~68-74%) across all 4 quarters, while **first-fill
  abandonment roughly doubles** in Q4 (6.0% -> 11.0%). This is the single
  most defensible story: patients who start therapy are adhering about as
  well as before; the problem is a growing group that never starts.
- DQ checks, run on data available as of Q3 (i.e. before this quarter's
  board presentation), already fire 2 warns (hub/CRM divergence, patient-
  level disagreement) and 2 fails (CRM flag staleness at 69%, and an
  implausible-age artifact in the raw Synthea extract) -- these would have
  been actionable early-warning signals.
- LLM extraction (Groq `openai/gpt-oss-120b`, JSON mode) on 150 labelled
  notes: high precision (~1.0) but recall 60-75% per signal, and ~81%
  agreement with an independent fill-derived gap signal.

## Assumptions and limitations

- **Synthea augmentation (Stage 2-3)**: only 5,000 of the planned ~278,000
  Synthea patients were generated (time-boxed decision). Clinical profiles
  come from Synthea (n≈242 cancer patients); volume comes from stratified
  resampling with jitter up to n=5,000. Profiles repeat with small
  variation, so clinical diversity is lower than a full run would give.
  Scaling up is a one-line change (`population_size` in
  `config/synthea_run.json`) plus re-running the generate scripts.
- **Program overlay (Stage "deadline mode")**: fills represent coverage
  blocks computed from a per-quarter "bad quarter" probability mixture, not
  literal pharmacy refill cadence. This made calibrating the headline
  pipeline/CRM numbers tractable, but it means the bridge's measure/source
  split (the "on schedule with grace" intermediate step) is noisier between
  quarters than the headline numbers themselves -- treat population effect
  and first-fill-abandonment as the most reliable parts of the story, and
  the exact measure/source split as indicative, not precise.
- **Quarter membership rule**: a patient counts in quarter Q's population if
  enrolled by Q's end and not yet dead/disenrolled as of Q's start (see
  PROGRESS.md Decisions log for why this was changed from "enrolled by Q's
  start").
- **Unspent time-box items**: Friday memo (`outputs/friday_memo.md`) and the
  slide deck (`outputs/deck.pptx`) were not completed before the deadline --
  not started, not partially done. Everything else in the Tier 1/Tier 2 plan
  (program overlay, metrics, bridge, HTML view, unified definition, DQ
  checks, LLM extraction) is implemented and wired into `run_all.py`.
- Tests are intentionally minimal per the deadline instruction (bridge-sums-
  to-gap, calibration-within-tolerance, plus what was already written in
  earlier stages for the Synthea/augmentation code).
