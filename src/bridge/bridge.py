"""Gap bridge: decomposes pipeline_metric - crm_metric into population,
measure, and source effects, both sequentially and via Shapley values.

Three binary factors, applied to the ALL-ENROLLED population / PDC>=80% /
hub-fills baseline (pipeline_metric):
  P (population): restrict to patients with >=1 hub fill
  M (measure):    swap PDC>=80% for an "on schedule" flag (hub fills, grace window)
  S (source):     swap the hub-derived flag for the CRM case-manager flag

Simplifying assumption (documented, not hidden): S and M are not fully
independent -- CRM has no PDC concept, so whenever S is "on" the CRM flag is
used regardless of M. This makes v() well-defined over all 8 subsets while
keeping the two sequential endpoints (v(empty)=pipeline_metric,
v({P,M,S})=crm_metric) exact.
"""
import itertools
import json
from pathlib import Path

import pandas as pd

from src.generate.overlay import get_quarters
from src.metrics.metrics import (
    GRACE_DAYS,
    PDC_THRESHOLD,
    crm_flag_by_patient,
    filler_patient_ids,
    on_schedule_by_patient,
    pdc_by_patient,
    population_mask,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = ROOT / "outputs" / "bridge.json"


def value(enrolments, hub_fills, crm_notes, q_start, q_end, p, m, s,
          pdc_threshold=PDC_THRESHOLD, grace_days=GRACE_DAYS):
    """v({P? , M?, S?}) -- see module docstring for the factor definitions."""
    pop = enrolments[population_mask(enrolments, q_start, q_end)]
    if p:
        pop = pop[pop["patient_id"].isin(filler_patient_ids(hub_fills, q_end))]
    if len(pop) == 0:
        return float("nan"), 0

    if s:
        flags = crm_flag_by_patient(pop, crm_notes, q_end).dropna()
        if len(flags) == 0:
            return float("nan"), 0
        return float(flags.mean()), len(flags)

    if m:
        flags = on_schedule_by_patient(pop, hub_fills, q_start, q_end, grace_days)
        return float(flags.mean()), len(pop)

    pdc = pdc_by_patient(pop, hub_fills, q_start, q_end)
    return float((pdc >= pdc_threshold).mean()), len(pop)


def sequential_bridge(enrolments, hub_fills, crm_notes, q_start, q_end):
    v0, n0 = value(enrolments, hub_fills, crm_notes, q_start, q_end, False, False, False)
    v1, n1 = value(enrolments, hub_fills, crm_notes, q_start, q_end, True, False, False)
    v2, n2 = value(enrolments, hub_fills, crm_notes, q_start, q_end, True, True, False)
    v3, n3 = value(enrolments, hub_fills, crm_notes, q_start, q_end, True, True, True)

    population_effect = v1 - v0
    measure_effect = v2 - v1
    source_effect = v3 - v2
    total_gap = v0 - v3  # pipeline - crm

    assert abs((population_effect + measure_effect + source_effect) - (v3 - v0)) < 1e-9

    return {
        "pipeline_metric": v0, "pipeline_n": n0,
        "after_population_restriction": v1, "after_population_n": n1,
        "after_measure_swap": v2, "after_measure_n": n2,
        "crm_metric": v3, "crm_n": n3,
        "population_effect": population_effect,
        "measure_effect": measure_effect,
        "source_effect": source_effect,
        "total_gap": total_gap,
    }


def shapley_effects(enrolments, hub_fills, crm_notes, q_start, q_end):
    factors = ["population", "measure", "source"]
    cache = {}

    def v(subset):
        key = frozenset(subset)
        if key not in cache:
            p, m, s = "population" in key, "measure" in key, "source" in key
            cache[key] = value(enrolments, hub_fills, crm_notes, q_start, q_end, p, m, s)[0]
        return cache[key]

    contributions = {f: [] for f in factors}
    for order in itertools.permutations(factors):
        present = set()
        prev = v(present)
        for factor in order:
            present = present | {factor}
            cur = v(present)
            contributions[factor].append(cur - prev)
            prev = cur

    return {f: sum(vals) / len(vals) for f, vals in contributions.items()}


def build_bridge():
    enrolments = pd.read_csv(ROOT / "data" / "enrolments.csv")
    hub_fills = pd.read_csv(ROOT / "data" / "hub_fills.csv")
    crm_notes = pd.read_csv(ROOT / "data" / "crm_notes.csv")
    for col in ("enrollment_date", "death_date", "disenrollment_date"):
        enrolments[col] = pd.to_datetime(enrolments[col])
    hub_fills["fill_date"] = pd.to_datetime(hub_fills["fill_date"])
    crm_notes["note_date"] = pd.to_datetime(crm_notes["note_date"])

    result = {"quarters": {}}
    quarters = {q["name"]: q for q in get_quarters()}
    for qname in ("Q3", "Q4"):
        q = quarters[qname]
        seq = sequential_bridge(enrolments, hub_fills, crm_notes, q["start"], q["end"])
        shap = shapley_effects(enrolments, hub_fills, crm_notes, q["start"], q["end"])
        result["quarters"][qname] = {
            "label": q["label"],
            "start": q["start"].isoformat(), "end": q["end"].isoformat(),
            "sequential": seq,
            "shapley": shap,
        }

    q3, q4 = result["quarters"]["Q3"]["sequential"], result["quarters"]["Q4"]["sequential"]
    result["quarter_over_quarter"] = {
        "pipeline_change": q4["pipeline_metric"] - q3["pipeline_metric"],
        "crm_change": q4["crm_metric"] - q3["crm_metric"],
        "population_effect_change": q4["population_effect"] - q3["population_effect"],
        "measure_effect_change": q4["measure_effect"] - q3["measure_effect"],
        "source_effect_change": q4["source_effect"] - q3["source_effect"],
        "explanation": (
            "The gap widened mostly because the population effect grew: more newly "
            "enrolled patients this quarter never received a first hub fill (modeled "
            "after a payer prior-authorization policy change), which pulls the "
            "all-enrolled pipeline population down without affecting the CRM "
            "dashboard's filler-only population at all."
        ),
    }
    return result


if __name__ == "__main__":
    result = build_bridge()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2))
    for qname, q in result["quarters"].items():
        seq = q["sequential"]
        print(f"{qname}: pipeline={seq['pipeline_metric']:.1%} -> crm={seq['crm_metric']:.1%} "
              f"(pop={seq['population_effect']:+.1%}, measure={seq['measure_effect']:+.1%}, source={seq['source_effect']:+.1%})")
        print(f"  shapley: {q['shapley']}")
    print(f"[bridge] wrote {OUTPUT_PATH}")
