from src.generate.augment import load_augmented_table
from src.generate.overlay import CONFIG, build_overlay
from src.metrics.metrics import all_quarters_summary

TOLERANCE = 0.05
TARGETS = {"Q3": (0.64, 0.72), "Q4": (0.58, 0.71)}


def test_calibration_within_tolerance():
    base = load_augmented_table()
    enrolments, hub_fills, crm_notes, _ = build_overlay(base, CONFIG)
    summary = all_quarters_summary(enrolments, hub_fills, crm_notes).set_index("quarter")

    for quarter, (pipeline_target, crm_target) in TARGETS.items():
        row = summary.loc[quarter]
        assert abs(row["pipeline_metric"] - pipeline_target) <= TOLERANCE, quarter
        assert abs(row["crm_metric"] - crm_target) <= TOLERANCE, quarter
