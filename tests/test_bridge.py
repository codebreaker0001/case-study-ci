import pandas as pd

from src.bridge.bridge import sequential_bridge


def _fake_data():
    enrolments = pd.DataFrame({
        "patient_id": ["p1", "p2", "p3", "p4"],
        "enrollment_date": pd.to_datetime(["2026-01-01"] * 4),
        "death_date": pd.to_datetime([None, None, None, None]),
        "disenrollment_date": pd.to_datetime([None, None, None, None]),
    })
    hub_fills = pd.DataFrame({
        "patient_id": ["p1", "p1", "p2"],
        "fill_date": pd.to_datetime(["2026-01-01", "2026-02-01", "2026-01-05"]),
        "days_supply": [30, 30, 90],
    })
    crm_notes = pd.DataFrame({
        "patient_id": ["p1", "p2"],
        "note_date": pd.to_datetime(["2026-03-01", "2026-03-01"]),
        "refilled_on_schedule": [True, False],
    })
    return enrolments, hub_fills, crm_notes


def test_bridge_sums_to_total_gap():
    enrolments, hub_fills, crm_notes = _fake_data()
    q_start, q_end = pd.Timestamp("2026-01-01"), pd.Timestamp("2026-04-01")
    result = sequential_bridge(enrolments, hub_fills, crm_notes, q_start, q_end)

    steps_sum = result["population_effect"] + result["measure_effect"] + result["source_effect"]
    expected = result["crm_metric"] - result["pipeline_metric"]
    assert abs(steps_sum - expected) < 1e-9
