import pandas as pd

from src.generate import augment


def _fake_base():
    return pd.DataFrame(
        {
            "patient_id": [f"p{i}" for i in range(10)],
            "sex": ["F", "M"] * 5,
            "state": ["Massachusetts"] * 10,
            "cancer_type": ["breast"] * 6 + ["lung"] * 2 + ["colorectal"] * 2,
            "age_at_diagnosis": [40, 50, 60, 70, 45, 55, 65, 75, 35, 85],
            "diagnosis_date": pd.to_datetime(["2020-01-01"] * 10),
            "death_date": pd.to_datetime(["2021-01-01"] + [None] * 9),
            "days_diagnosis_to_death": [365.0] + [None] * 9,
        }
    )


def test_patient_id_unique():
    base = _fake_base()
    out = augment.augment(base, target_n=500, seed=42)
    assert out["patient_id"].is_unique


def test_cancer_type_mix_within_2pts_of_source():
    base = _fake_base()
    out = augment.augment(base, target_n=5000, seed=42)
    source_share = base["cancer_type"].value_counts(normalize=True)
    out_share = out["cancer_type"].value_counts(normalize=True)
    for cancer_type, share in source_share.items():
        assert abs(out_share[cancer_type] - share) <= 0.02
