"""Program overlay: enrolments, hub fills, CRM notes on top of the augmented
cancer patient table. Re-anchors each profile's diagnosis date into a
4-quarter window ending "this quarter" (Q4), preserving age_at_diagnosis and
the diagnosis-to-death interval. All tunable mechanisms live in CONFIG.

Run as a module from the project root: `python -m src.generate.overlay`
"""
import random
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

from src.generate.augment import load_augmented_table

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"

CONFIG = {
    "seed": 42,
    "q4_end": "2026-09-01",      # reference date = end of "this quarter"
    "quarter_days": 90,
    "history_years": 2,          # how far before Q1 start diagnosis/enrollment dates can be drawn from
    "enrollment_lag_days": (0, 21),      # diagnosis -> program enrollment
    "first_fill_lag_days": (0, 14),      # enrollment -> first hub fill
    "supply_days_options": (28, 30),     # hub fill days-supply
    # Per-quarter "bad quarter" (missed-dose/delay) probability, drifting up Q1->Q4.
    "bad_quarter_prob": {"Q1": 0.14, "Q2": 0.17, "Q3": 0.21, "Q4": 0.25},
    "good_coverage_beta": (45, 1.0),     # coverage fraction of at-risk days when NOT a bad quarter
    "bad_coverage_beta": (2, 6),         # coverage fraction when IS a bad quarter
    "never_filler_base_prob": 0.05,       # enrolled but never fills (baseline, all quarters)
    "never_filler_payer_extra_prob": 0.55,  # EXTRA never-filler prob for patients enrolling in Q4: payer prior-auth change
    "discontinue_prob_per_quarter": 0.035,
    "dose_hold_prob_per_quarter": 0.04,   # clinician-directed hold for toxicity
    "dose_hold_days": (14, 42),
    "crm_truth_extra_miss_prob": 0.17,         # extra chance a case-manager-perceived "truth" diverges from fill-based truth (source effect)
    "case_manager_optimism_flip_prob": 0.20,  # prob a truly-off-schedule patient gets flagged "on schedule" anyway
    "case_manager_stale_prob": 0.20,          # prob this quarter's flag just repeats last known flag unchanged
    "note_missing_prob": 0.18,                # prob no CRM note at all this quarter
    "note_late_days": (0, 20),
    "neutral_note_prob": 0.25,                # prob note text carries no adherence info regardless of truth
    "payer_types": ["Commercial", "Medicare", "Medicaid"],
    "regions": ["Greater Boston", "North Shore", "South Shore", "Western MA", "Central MA", "Cape Cod"],
    "case_managers": [
        "J. Alvarez", "M. Chen", "R. Okafor", "S. Patel", "T. Nguyen",
        "K. O'Brien", "D. Russo", "L. Fitzgerald",
    ],
}


def get_quarters(config=CONFIG):
    """Chronological list of 4 quarters, Q4 ending at config['q4_end']."""
    q4_end = pd.Timestamp(config["q4_end"])
    days = config["quarter_days"]
    bounds = [q4_end - i * pd.Timedelta(days=days) for i in range(5)][::-1]
    names = ["Q1", "Q2", "Q3", "Q4"]
    labels = {"Q1": "history_1", "Q2": "history_2", "Q3": "last_quarter", "Q4": "this_quarter"}
    return [
        {"name": names[i], "label": labels[names[i]], "start": bounds[i], "end": bounds[i + 1]}
        for i in range(4)
    ]


def _simulate_patient(row, quarters, rng, pyrng, config):
    """Simulate one patient's enrollment, fills, holds, discontinuation, death."""
    q1_start, q4_end = quarters[0]["start"], quarters[-1]["end"]
    history_start = q1_start - pd.Timedelta(days=365 * config["history_years"])

    dx_date = pd.Timestamp(
        history_start + pd.Timedelta(days=int(rng.integers(0, (q4_end - history_start).days)))
    )
    enrollment_date = dx_date + pd.Timedelta(days=int(rng.integers(*config["enrollment_lag_days"])))

    days_to_death = row["days_diagnosis_to_death"]
    death_date = dx_date + pd.Timedelta(days=round(days_to_death)) if pd.notna(days_to_death) else pd.NaT

    in_q4 = quarters[-1]["start"] <= enrollment_date <= quarters[-1]["end"]
    never_filler_prob = config["never_filler_base_prob"] + (
        config["never_filler_payer_extra_prob"] if in_q4 else 0.0
    )
    never_filler = pyrng.random() < never_filler_prob

    # end of this patient's program involvement, before considering discontinuation
    hard_end = min(death_date, q4_end) if pd.notna(death_date) else q4_end

    # roll discontinuation quarter-by-quarter among quarters the patient is enrolled in
    disenrollment_date = pd.NaT
    disenrollment_reason = None
    for q in quarters:
        if disenrollment_date is not pd.NaT and not pd.isna(disenrollment_date):
            break
        if enrollment_date > q["end"] or hard_end < q["start"]:
            continue
        if pyrng.random() < config["discontinue_prob_per_quarter"]:
            lo = max(q["start"], enrollment_date)
            hi = min(q["end"], hard_end)
            if hi > lo:
                offset = int(pyrng.random() * (hi - lo).days) if (hi - lo).days > 0 else 0
                disenrollment_date = lo + pd.Timedelta(days=offset)
                disenrollment_reason = pyrng.choice(
                    ["disease progression", "toxicity", "patient choice", "lost to follow-up"]
                )

    program_end = hard_end
    if pd.notna(disenrollment_date):
        program_end = min(program_end, disenrollment_date)

    # clinician-directed dose hold (toxicity): at most one, somewhere in the active window
    hold_start, hold_end = pd.NaT, pd.NaT
    if not never_filler and program_end > enrollment_date:
        for q in quarters:
            if enrollment_date > q["end"] or program_end < q["start"]:
                continue
            if pyrng.random() < config["dose_hold_prob_per_quarter"]:
                lo = max(q["start"], enrollment_date)
                hi = min(q["end"], program_end)
                if hi > lo:
                    offset = int(pyrng.random() * (hi - lo).days) if (hi - lo).days > 0 else 0
                    hold_start = lo + pd.Timedelta(days=offset)
                    hold_end = hold_start + pd.Timedelta(
                        days=int(rng.integers(*config["dose_hold_days"]))
                    )
                    break

    fills = []
    quarter_flags = {}  # quarter name -> {"missed": bool, "delay": bool}

    if not never_filler and program_end > enrollment_date:
        enrollment_delay = pd.Timedelta(days=int(rng.integers(*config["first_fill_lag_days"])))
        for q in quarters:
            active_start = max(q["start"], enrollment_date + enrollment_delay)
            active_end = min(q["end"], program_end)
            active_days = (active_end - active_start).days
            if active_days <= 0:
                continue

            hold_overlap_days = 0
            if pd.notna(hold_start):
                ov_start, ov_end = max(active_start, hold_start), min(active_end, hold_end)
                hold_overlap_days = max(0, (ov_end - ov_start).days)

            if hold_overlap_days > 0:
                days_covered = max(active_days - hold_overlap_days, 0)
                gap_days = hold_overlap_days
                gap_start = max(active_start, hold_start)
                is_bad = True
                quarter_flags[q["name"]] = {"missed": False, "delay": False, "hold": True}
            else:
                is_bad = pyrng.random() < config["bad_quarter_prob"][q["name"]]
                coverage_frac = float(rng.beta(*(config["bad_coverage_beta"] if is_bad else config["good_coverage_beta"])))
                days_covered = min(int(round(coverage_frac * active_days)), active_days)
                gap_days = active_days - days_covered
                gap_start = active_start + pd.Timedelta(days=days_covered // 2)
                event_type = "missed" if (is_bad and gap_days >= 14) else ("delay" if is_bad and gap_days > 0 else None)
                quarter_flags[q["name"]] = {
                    "missed": event_type == "missed",
                    "delay": event_type == "delay",
                    "hold": False,
                }

            supply = int(pyrng.choice(config["supply_days_options"]))
            if gap_days <= 0 or days_covered == 0:
                if days_covered > 0:
                    fills.append((active_start, days_covered))
            else:
                first_block = days_covered // 2
                second_block = days_covered - first_block
                if first_block > 0:
                    fills.append((active_start, first_block))
                second_start = gap_start + pd.Timedelta(days=gap_days)
                if second_block > 0 and second_start < active_end:
                    fills.append((second_start, second_block))
            del supply  # supply duration isn't separately meaningful once coverage is computed directly

    return {
        "diagnosis_date": dx_date,
        "enrollment_date": enrollment_date,
        "death_date": death_date,
        "disenrollment_date": disenrollment_date,
        "disenrollment_reason": disenrollment_reason,
        "never_filler": never_filler,
        "hold_start": hold_start,
        "hold_end": hold_end,
        "fills": fills,
        "quarter_flags": quarter_flags,
    }


NEUTRAL_TEMPLATES = [
    "Pt doing well, f/u scheduled next visit.",
    "Checked in w/ pt, no new concerns reported.",
    "Pt tol tx well per report. Cont current plan.",
    "Spoke w/ pt's spouse, pt stable, no issues noted.",
    "F/u call completed, pt reports feeling okay.",
]


def _note_text(flags, pyrng):
    if flags["neutral"]:
        return pyrng.choice(NEUTRAL_TEMPLATES)
    parts = []
    if flags["missed_doses"]:
        parts.append(pyrng.choice(["Pt admits missed doses this cycle.", "Pt states missed a few doses, ran out early.", "Missed refill, pt forgot to call in."]))
    if flags["delay"]:
        parts.append(pyrng.choice(["Refill delayed ~2 wks, pharmacy backorder per pt.", "Pt picked up refill late, pt says lost track of time.", "Delay in refill noted, f/u next wk."]))
    if flags["therapy_hold"]:
        if flags["hold_clinician_directed"]:
            parts.append(pyrng.choice(["Tx on hold per MD for tox (neutropenia). Will resume next cycle.", "Dose hold ordered by onc for s/e mgmt.", "MD directed hold d/t tox, pt aware."]))
        else:
            parts.append("Pt self-paused tx, reason unclear.")
    if flags["discontinued"]:
        reason = flags["discontinuation_reason"] or "unspecified"
        parts.append(f"Pt d/c'd tx. Reason: {reason}.")
    if not parts:
        parts.append(pyrng.choice(NEUTRAL_TEMPLATES))
    return " ".join(parts)


def build_overlay(base: pd.DataFrame, config=CONFIG):
    seed = config["seed"]
    rng = np.random.default_rng(seed)
    pyrng = random.Random(seed)
    quarters = get_quarters(config)

    enrol_rows = []
    fill_rows = []
    note_rows = []
    gt_rows = []

    for _, row in base.iterrows():
        sim = _simulate_patient(row, quarters, rng, pyrng, config)
        pid = row["patient_id"]

        enrol_rows.append({
            "patient_id": pid,
            "sex": row["sex"],
            "state": row["state"],
            "region": pyrng.choice(config["regions"]),
            "payer_type": pyrng.choice(config["payer_types"]),
            "case_manager": pyrng.choice(config["case_managers"]),
            "cancer_type": row["cancer_type"],
            "age_at_diagnosis": row["age_at_diagnosis"],
            "diagnosis_date": sim["diagnosis_date"],
            "enrollment_date": sim["enrollment_date"],
            "death_date": sim["death_date"],
            "disenrollment_date": sim["disenrollment_date"],
            "disenrollment_reason": sim["disenrollment_reason"],
            "never_filler": sim["never_filler"],
            "hold_start": sim["hold_start"],
            "hold_end": sim["hold_end"],
        })

        for fdate, supply in sim["fills"]:
            fill_rows.append({
                "fill_id": str(uuid.uuid4()),
                "patient_id": pid,
                "fill_date": fdate,
                "days_supply": supply,
            })

        # one CRM note opportunity per quarter the patient is enrolled in
        last_flag = None
        for q in quarters:
            if sim["enrollment_date"] > q["end"]:
                continue
            program_end = sim["disenrollment_date"] if pd.notna(sim["disenrollment_date"]) else (
                sim["death_date"] if pd.notna(sim["death_date"]) else q["end"]
            )
            if program_end < q["start"]:
                continue
            if pyrng.random() < config["note_missing_prob"]:
                continue

            note_date = q["start"] + pd.Timedelta(
                days=int(pyrng.random() * config["quarter_days"]) + int(rng.integers(*config["note_late_days"]))
            )

            qflags = sim["quarter_flags"].get(q["name"], {"missed": False, "delay": False, "hold": False})
            missed_recent = qflags["missed"]
            delay_recent = qflags["delay"]
            hold_active = qflags["hold"]
            discontinued_this_q = (
                pd.notna(sim["disenrollment_date"]) and q["start"] <= sim["disenrollment_date"] <= q["end"]
            )

            truth_on_schedule = (not sim["never_filler"]) and not (missed_recent or delay_recent or hold_active)
            if truth_on_schedule and pyrng.random() < config["crm_truth_extra_miss_prob"]:
                truth_on_schedule = False  # case-manager-perceived status diverges from fill data

            if pyrng.random() < config["case_manager_stale_prob"] and last_flag is not None:
                reported_flag = last_flag
            else:
                reported_flag = truth_on_schedule
                if (not truth_on_schedule) and pyrng.random() < config["case_manager_optimism_flip_prob"]:
                    reported_flag = True
            last_flag = reported_flag

            flags = {
                "missed_doses": missed_recent,
                "delay": delay_recent,
                "discontinued": discontinued_this_q,
                "discontinuation_reason": sim["disenrollment_reason"] if discontinued_this_q else None,
                "therapy_hold": hold_active,
                "hold_clinician_directed": hold_active,  # all simulated holds are clinician-directed
                "neutral": pyrng.random() < config["neutral_note_prob"],
            }

            note_id = str(uuid.uuid4())
            note_rows.append({
                "note_id": note_id,
                "patient_id": pid,
                "note_date": note_date,
                "case_manager": enrol_rows[-1]["case_manager"],
                "refilled_on_schedule": reported_flag,
                "note_text": _note_text(flags, pyrng),
            })
            gt_rows.append({
                "note_id": note_id,
                "missed_doses": flags["missed_doses"],
                "delay": flags["delay"],
                "discontinued": flags["discontinued"],
                "discontinuation_reason": flags["discontinuation_reason"],
                "therapy_hold": flags["therapy_hold"],
                "hold_clinician_directed": flags["hold_clinician_directed"],
            })

    enrolments = pd.DataFrame(enrol_rows)
    hub_fills = pd.DataFrame(fill_rows)
    crm_notes = pd.DataFrame(note_rows)
    ground_truth_notes = pd.DataFrame(gt_rows)
    return enrolments, hub_fills, crm_notes, ground_truth_notes


def save_overlay(enrolments, hub_fills, crm_notes, ground_truth_notes):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    enrolments.to_csv(DATA_DIR / "enrolments.csv", index=False)
    hub_fills.to_csv(DATA_DIR / "hub_fills.csv", index=False)
    crm_notes.to_csv(DATA_DIR / "crm_notes.csv", index=False)
    ground_truth_notes.to_csv(DATA_DIR / "ground_truth_notes.csv", index=False)


def print_calibration_table(enrolments, hub_fills, crm_notes):
    from src.metrics.metrics import all_quarters_summary

    targets = {"Q3": (0.64, 0.72), "Q4": (0.58, 0.71)}
    summary = all_quarters_summary(enrolments, hub_fills, crm_notes)
    print("\n[overlay] calibration table (CASE.md Exhibit 2 targets: Q3=64%/72%, Q4=58%/71%)")
    print(f"{'quarter':8}{'pipeline':>10}{'target':>8}{'off':>8}{'crm':>10}{'target':>8}{'off':>8}")
    for _, r in summary.iterrows():
        pt, ct = targets.get(r["quarter"], (None, None))
        p_off = f"{r['pipeline_metric']-pt:+.1%}" if pt else "-"
        c_off = f"{r['crm_metric']-ct:+.1%}" if ct else "-"
        print(
            f"{r['quarter']:8}{r['pipeline_metric']:>10.1%}{(f'{pt:.0%}' if pt else '-'):>8}{p_off:>8}"
            f"{r['crm_metric']:>10.1%}{(f'{ct:.0%}' if ct else '-'):>8}{c_off:>8}"
        )
    return summary


if __name__ == "__main__":
    base = load_augmented_table()
    enrolments, hub_fills, crm_notes, ground_truth_notes = build_overlay(base, CONFIG)
    save_overlay(enrolments, hub_fills, crm_notes, ground_truth_notes)
    print(f"[overlay] enrolments={len(enrolments)} fills={len(hub_fills)} notes={len(crm_notes)}")
    print(f"[overlay] never_filler rate: {enrolments['never_filler'].mean():.1%}")
    print_calibration_table(enrolments, hub_fills, crm_notes)
