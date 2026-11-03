"""Resample the small Synthea cancer-patient base table up to a usable volume.

Run as a module from the project root: `python -m src.generate.augment [target_n]`

Starts from the ~242 real Synthea profiles, drops implausible ages at
diagnosis, then resamples with replacement (stratified by cancer type) to a
target count, jittering age_at_diagnosis and scaling days_diagnosis_to_death
per synthetic patient. See PROGRESS.md Decisions log for why (time-boxed
stand-in for a full-scale Synthea run).
"""
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

from src.generate.synthea_base import load_base_table

ROOT = Path(__file__).resolve().parents[2]
AUGMENTED_PATH = ROOT / "data" / "synthea_seed" / "augmented_patients.csv"

MIN_AGE_AT_DX = 18
MAX_AGE_AT_DX = 95
SEED = 42


def filter_plausible(base: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    plausible = base[
        base["age_at_diagnosis"].between(MIN_AGE_AT_DX, MAX_AGE_AT_DX)
    ].reset_index(drop=True)
    dropped = len(base) - len(plausible)
    return plausible, dropped


def augment(base: pd.DataFrame, target_n: int = 5000, seed: int = SEED) -> pd.DataFrame:
    """Stratified resample-with-replacement to target_n, preserving cancer_type mix."""
    rng = np.random.default_rng(seed)

    type_counts = base["cancer_type"].value_counts()
    shares = (type_counts / len(base)).sort_index()
    per_type_n = (shares * target_n).round().astype(int)
    # fix rounding drift so totals sum exactly to target_n
    per_type_n.iloc[-1] += target_n - per_type_n.sum()

    rows = []
    for cancer_type, n in per_type_n.items():
        subset = base[base["cancer_type"] == cancer_type].reset_index(drop=True)
        picks = rng.integers(0, len(subset), size=n)
        for idx in picks:
            rows.append(subset.iloc[idx])

    sampled = pd.DataFrame(rows).reset_index(drop=True)

    n = len(sampled)
    age_jitter = rng.integers(-3, 4, size=n)  # -3..+3 inclusive
    death_scale = rng.uniform(0.8, 1.2, size=n)

    sampled["age_at_diagnosis"] = (sampled["age_at_diagnosis"] + age_jitter).clip(
        MIN_AGE_AT_DX, MAX_AGE_AT_DX
    )
    sampled["days_diagnosis_to_death"] = sampled["days_diagnosis_to_death"] * death_scale
    has_death = sampled["days_diagnosis_to_death"].notna()
    sampled.loc[has_death, "death_date"] = sampled.loc[has_death, "diagnosis_date"] + pd.to_timedelta(
        sampled.loc[has_death, "days_diagnosis_to_death"].round(), unit="D"
    )
    sampled.loc[~has_death, "death_date"] = pd.NaT

    sampled["source_synthea_id"] = sampled["patient_id"]
    sampled["patient_id"] = [str(uuid.uuid4()) for _ in range(n)]
    sampled["is_augmented"] = True

    return sampled[
        [
            "patient_id",
            "source_synthea_id",
            "sex",
            "state",
            "cancer_type",
            "age_at_diagnosis",
            "diagnosis_date",
            "death_date",
            "days_diagnosis_to_death",
            "is_augmented",
        ]
    ]


def load_augmented_table() -> pd.DataFrame:
    df = pd.read_csv(AUGMENTED_PATH, dtype={"patient_id": str, "source_synthea_id": str})
    df["diagnosis_date"] = pd.to_datetime(df["diagnosis_date"])
    df["death_date"] = pd.to_datetime(df["death_date"])
    return df


if __name__ == "__main__":
    import sys

    target_n = int(sys.argv[1]) if len(sys.argv) > 1 else 5000

    base = load_base_table()
    plausible, dropped = filter_plausible(base)
    print(f"[augment] dropped {dropped} implausible profiles (age at diagnosis < {MIN_AGE_AT_DX} or > {MAX_AGE_AT_DX})")
    print(f"[augment] {len(plausible)} plausible source profiles remain")

    augmented = augment(plausible, target_n=target_n)
    AUGMENTED_PATH.parent.mkdir(parents=True, exist_ok=True)
    augmented.to_csv(AUGMENTED_PATH, index=False)
    print(f"[augment] wrote {len(augmented)} rows to {AUGMENTED_PATH}")
