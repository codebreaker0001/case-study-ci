# Project

Reconciling two disagreeing adherence metrics (pipeline vs. CRM dashboard) for a
pharma patient support program, before a board presentation. Full case: [CASE.md](CASE.md).
Build plan and status: [PROGRESS.md](PROGRESS.md).

## Stack

- Python 3.11+, pandas, numpy, pydantic, groq SDK
- Java only needed to regenerate Synthea base patient data (Synthea is a Java CLI tool)

## Folder structure

- `src/generate/` — synthetic data generation (Synthea overlay, enrolments, hub fills, CRM notes)
- `src/metrics/` — PDC and "refilled on schedule" metric computation
- `src/bridge/` — gap bridge decomposition (population / measure-definition / data-source effects)
- `src/extract/` — LLM extraction of adherence signals from free-text CRM notes (Groq)
- `src/unified/` — unified adherence definition
- `src/dq/` — data-quality checks
- `src/report/` — Friday report generation
- `src/viz/` — HTML reconciliation view and optional slide deck
- `data/` — generated/raw data (gitignored except small fixtures)
- `outputs/` — generated reports, views, decks
- `scripts/` — one-off/CLI entry points
- `tests/` — tests, mirroring `src/` structure

## Rules

- Read CASE.md and PROGRESS.md at the start of every session.
- We build one stage at a time (see PROGRESS.md). Stop after each stage for review — do not jump ahead.
- Update PROGRESS.md after finishing each task.
- Run tests before marking any task done.
- Use fixed random seeds everywhere data is generated or sampled.
- Never hardcode target percentages (e.g. don't tune code to literally output 58%/64%/71%/72% — calibrate the underlying generative parameters instead).
- Never put API keys in files. Load GROQ_API_KEY from environment / `.env` (gitignored), document it in `.env.example`.
- Prefer simple, readable code over clever abstractions.
