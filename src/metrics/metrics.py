"""Pipeline and CRM adherence metrics, computed exactly per CASE.md Exhibit 1.

Pipeline: population = all enrolled patients; measure = PDC >= threshold;
          source = specialty pharmacy hub fills.
CRM:      population = patients with >=1 hub fill; measure = "refilled on
          schedule" flag; source = case-manager CRM notes (most recent known
          flag as of quarter end -- this is where staleness shows up).

Never reads data/ground_truth_notes.csv.
"""
import numpy as np
import pandas as pd

from src.generate.overlay import get_quarters

PDC_THRESHOLD = 0.80
GRACE_DAYS = 7


def population_mask(enrolments: pd.DataFrame, q_start: pd.Timestamp, q_end: pd.Timestamp = None) -> pd.Series:
    """All-enrolled population for the quarter: enrolled by quarter end (so new
    enrollees count in the quarter they join, not only from the quarter after),
    not yet dead/disenrolled as of quarter start."""
    e = enrolments
    enrolled_cutoff = q_end if q_end is not None else q_start
    return (
        (e["enrollment_date"] <= enrolled_cutoff)
        & (e["disenrollment_date"].isna() | (e["disenrollment_date"] > q_start))
        & (e["death_date"].isna() | (e["death_date"] > q_start))
    )


def filler_patient_ids(hub_fills: pd.DataFrame, as_of: pd.Timestamp) -> set:
    return set(hub_fills.loc[hub_fills["fill_date"] <= as_of, "patient_id"].unique())


def pdc_by_patient(enrolments: pd.DataFrame, hub_fills: pd.DataFrame, q_start, q_end) -> pd.Series:
    """PDC for each patient in `enrolments`, over [q_start, q_end), from hub fills only."""
    quarter_days = (q_end - q_start).days
    fills = hub_fills[(hub_fills["fill_date"] < q_end) & (hub_fills["fill_date"] + pd.to_timedelta(hub_fills["days_supply"], unit="D") > q_start)]
    covered = {}
    for pid, grp in fills.groupby("patient_id"):
        days = np.zeros(quarter_days, dtype=bool)
        for fill_date, supply in zip(grp["fill_date"], grp["days_supply"]):
            start = max(fill_date, q_start)
            end = min(fill_date + pd.Timedelta(days=int(supply)), q_end)
            if end > start:
                a = (start - q_start).days
                b = (end - q_start).days
                days[a:b] = True
        covered[pid] = days.sum()
    pdc = pd.Series(0.0, index=enrolments["patient_id"])
    for pid, days_covered in covered.items():
        if pid in pdc.index:
            pdc.loc[pid] = days_covered / quarter_days
    return pdc


def on_schedule_by_patient(enrolments: pd.DataFrame, hub_fills: pd.DataFrame, q_start, q_end, grace_days=GRACE_DAYS) -> pd.Series:
    """Binary 'on schedule' measure from hub fills: most recent scheduled refill before
    q_end was filled within `grace_days` of when it was due. Patients with no fill by
    q_end are marked not-on-schedule."""
    result = pd.Series(False, index=enrolments["patient_id"])
    fills = hub_fills[hub_fills["fill_date"] <= q_end].sort_values("fill_date")
    for pid, grp in fills.groupby("patient_id"):
        if pid not in result.index:
            continue
        rows = list(zip(grp["fill_date"], grp["days_supply"]))
        last_date, last_supply = rows[-1]
        if len(rows) == 1:
            result.loc[pid] = True
            continue
        prev_date, prev_supply = rows[-2]
        due = prev_date + pd.Timedelta(days=int(prev_supply))
        gap = (last_date - due).days
        result.loc[pid] = gap <= grace_days
    return result


def crm_flag_by_patient(enrolments: pd.DataFrame, crm_notes: pd.DataFrame, q_end) -> pd.Series:
    """Most recent known refilled_on_schedule flag as of q_end (NaN if none yet)."""
    notes = crm_notes[crm_notes["note_date"] <= q_end].sort_values("note_date")
    latest = notes.groupby("patient_id")["refilled_on_schedule"].last()
    return latest.reindex(enrolments["patient_id"])


def pipeline_metric(enrolments, hub_fills, q_start, q_end, pdc_threshold=PDC_THRESHOLD) -> dict:
    pop = enrolments[population_mask(enrolments, q_start, q_end)]
    if len(pop) == 0:
        return {"metric": float("nan"), "n": 0}
    pdc = pdc_by_patient(pop, hub_fills, q_start, q_end)
    adherent = (pdc >= pdc_threshold).sum()
    return {"metric": adherent / len(pop), "n": len(pop), "adherent": int(adherent)}


def crm_metric(enrolments, hub_fills, crm_notes, q_start, q_end) -> dict:
    pop = enrolments[population_mask(enrolments, q_start, q_end)]
    fillers = pop[pop["patient_id"].isin(filler_patient_ids(hub_fills, q_end))]
    if len(fillers) == 0:
        return {"metric": float("nan"), "n": 0}
    flags = crm_flag_by_patient(fillers, crm_notes, q_end)
    known = flags.dropna()
    if len(known) == 0:
        return {"metric": float("nan"), "n": 0}
    return {"metric": known.mean(), "n": len(known), "fillers_total": len(fillers)}


def all_quarters_summary(enrolments, hub_fills, crm_notes, config=None) -> pd.DataFrame:
    quarters = get_quarters(config) if config else get_quarters()
    rows = []
    for q in quarters:
        pm = pipeline_metric(enrolments, hub_fills, q["start"], q["end"])
        cm = crm_metric(enrolments, hub_fills, crm_notes, q["start"], q["end"])
        rows.append({
            "quarter": q["name"],
            "label": q["label"],
            "pipeline_metric": pm["metric"],
            "pipeline_n": pm["n"],
            "crm_metric": cm["metric"],
            "crm_n": cm["n"],
        })
    return pd.DataFrame(rows)
