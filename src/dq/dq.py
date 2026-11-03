"""Data-quality checks: pass/warn/fail, each evaluated using only data
available AS OF the end of Q3 ("last quarter") -- i.e. everything they'd
have seen BEFORE this quarter's board presentation, to show these checks
are an early-warning system, not hindsight.
"""
import json
from pathlib import Path

import pandas as pd

from src.generate.overlay import get_quarters
from src.metrics.metrics import all_quarters_summary, filler_patient_ids, on_schedule_by_patient, population_mask

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = ROOT / "outputs" / "dq_results.json"


def run_checks(enrolments, hub_fills, crm_notes, base_table, as_of_quarter="Q3") -> list:
    quarters = get_quarters()
    as_of = next(q for q in quarters if q["name"] == as_of_quarter)
    checks = []

    # 1. Hub vs CRM divergence
    summary = all_quarters_summary(enrolments, hub_fills, crm_notes)
    row = summary[summary["quarter"] == as_of_quarter].iloc[0]
    gap = abs(row["pipeline_metric"] - row["crm_metric"])
    status = "fail" if gap > 0.15 else ("warn" if gap > 0.08 else "pass")
    checks.append({
        "name": "Hub vs CRM divergence",
        "status": status,
        "detail": f"|pipeline - crm| = {gap:.1%} as of {as_of_quarter} (warn>8pts, fail>15pts)",
    })

    # 2. Patient-level disagreement rate (hub on-schedule vs CRM flag, among fillers with both)
    pop = enrolments[population_mask(enrolments, as_of["start"], as_of["end"])]
    fillers = pop[pop["patient_id"].isin(filler_patient_ids(hub_fills, as_of["end"]))]
    hub_flags = on_schedule_by_patient(fillers, hub_fills, as_of["start"], as_of["end"])
    notes = crm_notes[crm_notes["note_date"] <= as_of["end"]].sort_values("note_date")
    crm_flags = notes.groupby("patient_id")["refilled_on_schedule"].last().reindex(fillers["patient_id"])
    comparable = crm_flags.dropna().index
    disagree_rate = (hub_flags.loc[comparable] != crm_flags.loc[comparable].astype(bool)).mean() if len(comparable) else float("nan")
    status = "fail" if disagree_rate > 0.30 else ("warn" if disagree_rate > 0.15 else "pass")
    checks.append({
        "name": "Patient-level hub/CRM disagreement rate",
        "status": status,
        "detail": f"{disagree_rate:.1%} of {len(comparable)} comparable patients disagree (warn>15%, fail>30%)",
    })

    # 3. CRM flag staleness (consecutive notes repeating the identical flag)
    all_notes = crm_notes[crm_notes["note_date"] <= as_of["end"]].sort_values(["patient_id", "note_date"])
    all_notes["prev_flag"] = all_notes.groupby("patient_id")["refilled_on_schedule"].shift(1)
    comparable_notes = all_notes.dropna(subset=["prev_flag"])
    stale_rate = (comparable_notes["refilled_on_schedule"] == comparable_notes["prev_flag"]).mean() if len(comparable_notes) else float("nan")
    status = "fail" if stale_rate > 0.55 else ("warn" if stale_rate > 0.35 else "pass")
    checks.append({
        "name": "CRM flag staleness",
        "status": status,
        "detail": f"{stale_rate:.1%} of notes repeat the immediately prior flag unchanged (warn>35%, fail>55%)",
    })

    # 4. Note coverage
    missing = 1 - len(crm_flags.dropna()) / len(fillers) if len(fillers) else float("nan")
    status = "fail" if missing > 0.30 else ("warn" if missing > 0.15 else "pass")
    checks.append({
        "name": "CRM note coverage",
        "status": status,
        "detail": f"{missing:.1%} of fillers have no CRM flag by {as_of_quarter} end (warn>15%, fail>30%)",
    })

    # 5. Enrolled-without-fill trend (rising never-filled share across quarters up to Q3)
    hist_quarters = [q for q in quarters if q["name"] <= as_of_quarter]
    shares = []
    for q in hist_quarters:
        p = enrolments[population_mask(enrolments, q["start"], q["end"])]
        f = filler_patient_ids(hub_fills, q["end"])
        shares.append(1 - p["patient_id"].isin(f).mean())
    rising = all(b >= a - 0.005 for a, b in zip(shares, shares[1:])) and (shares[-1] - shares[0] > 0.01)
    status = "warn" if rising else "pass"
    checks.append({
        "name": "Enrolled-without-fill trend",
        "status": status,
        "detail": f"never-filled share by quarter: {', '.join(f'{s:.1%}' for s in shares)}"
                  + (" -- rising before this quarter" if rising else ""),
    })

    # 6. Implausible age at diagnosis
    implausible = base_table[~base_table["age_at_diagnosis"].between(18, 95)]
    status = "fail" if len(implausible) > 0 else "pass"
    checks.append({
        "name": "Implausible age at diagnosis",
        "status": status,
        "detail": f"{len(implausible)} profiles with age at diagnosis <18 or >95 in the current base table",
    })

    return checks


if __name__ == "__main__":
    enrolments = pd.read_csv(ROOT / "data" / "enrolments.csv")
    hub_fills = pd.read_csv(ROOT / "data" / "hub_fills.csv")
    crm_notes = pd.read_csv(ROOT / "data" / "crm_notes.csv")
    base_table = pd.read_csv(ROOT / "data" / "synthea_seed" / "cancer_patients_base.csv")
    for col in ("enrollment_date", "death_date", "disenrollment_date"):
        enrolments[col] = pd.to_datetime(enrolments[col])
    hub_fills["fill_date"] = pd.to_datetime(hub_fills["fill_date"])
    crm_notes["note_date"] = pd.to_datetime(crm_notes["note_date"])

    checks = run_checks(enrolments, hub_fills, crm_notes, base_table, as_of_quarter="Q3")
    for c in checks:
        print(f"[{c['status'].upper():4}] {c['name']}: {c['detail']}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps({"as_of_quarter": "Q3", "checks": checks}, indent=2))
    print(f"[dq] wrote {OUTPUT_PATH}")
