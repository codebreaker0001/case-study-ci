"""Unified adherence definition: PDC>=80% from hub fills, among patients with
>=1 fill, excluding clinician-directed hold days from the PDC denominator.
First-fill abandonment (enrolled, never filled) is reported separately,
never folded into the unified rate -- it's a different failure mode
(never started) from "started but not adherent."
"""
import json
from pathlib import Path

import pandas as pd

from src.generate.overlay import get_quarters
from src.metrics.metrics import PDC_THRESHOLD, covered_days_by_patient, filler_patient_ids, population_mask

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = ROOT / "outputs" / "unified_metric.json"


def hold_days_in_quarter(enrolments: pd.DataFrame, q_start, q_end) -> pd.Series:
    hs = enrolments["hold_start"]
    he = enrolments["hold_end"]
    ov_start = hs.clip(lower=q_start)
    ov_end = he.clip(upper=q_end)
    days = (ov_end - ov_start).dt.days.clip(lower=0).fillna(0).astype(int)
    days.index = enrolments["patient_id"]
    return days


def unified_metric(enrolments, hub_fills, q_start, q_end, pdc_threshold=PDC_THRESHOLD) -> dict:
    pop = enrolments[population_mask(enrolments, q_start, q_end)]
    fillers = pop[pop["patient_id"].isin(filler_patient_ids(hub_fills, q_end))]

    first_fill_abandonment = {
        "rate": 1 - len(fillers) / len(pop) if len(pop) else float("nan"),
        "n_abandoned": int(len(pop) - len(fillers)),
        "n_population": int(len(pop)),
    }

    if len(fillers) == 0:
        return {"metric": float("nan"), "n": 0, "first_fill_abandonment": first_fill_abandonment}

    quarter_days = (q_end - q_start).days
    covered = covered_days_by_patient(fillers, hub_fills, q_start, q_end)
    hold_days = hold_days_in_quarter(fillers, q_start, q_end)
    denom = (quarter_days - hold_days.reindex(covered.index).fillna(0)).clip(lower=1)
    pdc_excl_hold = (covered / denom).clip(upper=1.0)

    adherent = (pdc_excl_hold >= pdc_threshold).sum()
    return {
        "metric": adherent / len(fillers),
        "n": len(fillers),
        "adherent": int(adherent),
        "first_fill_abandonment": first_fill_abandonment,
    }


def all_quarters_unified(enrolments, hub_fills) -> dict:
    result = {}
    for q in get_quarters():
        result[q["name"]] = unified_metric(enrolments, hub_fills, q["start"], q["end"])
    return result


if __name__ == "__main__":
    enrolments = pd.read_csv(ROOT / "data" / "enrolments.csv")
    hub_fills = pd.read_csv(ROOT / "data" / "hub_fills.csv")
    for col in ("enrollment_date", "death_date", "disenrollment_date", "hold_start", "hold_end"):
        enrolments[col] = pd.to_datetime(enrolments[col])
    hub_fills["fill_date"] = pd.to_datetime(hub_fills["fill_date"])

    result = all_quarters_unified(enrolments, hub_fills)
    for q, r in result.items():
        print(f"{q}: unified={r['metric']:.1%} (n={r['n']}) first_fill_abandonment={r['first_fill_abandonment']['rate']:.1%}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2))
    print(f"[unified] wrote {OUTPUT_PATH}")
