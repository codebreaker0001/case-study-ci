"""Build a clean one-row-per-cancer-patient base table from raw Synthea output.

Loader prefers fresh Synthea output (data/synthea_raw/csv/) and falls back to
the committed cache (data/synthea_seed/) if no fresh output exists. See
DATA_LINEAGE.md for column provenance and CASE.md / PROGRESS.md decisions log
for the cancer-code and "multiple diagnoses" rules.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "synthea_raw" / "csv"
SEED_DIR = ROOT / "data" / "synthea_seed"
SEED_PATH = SEED_DIR / "cancer_patients_base.csv"

# Diagnosis condition codes (SNOMED CT), read directly from each module's
# ConditionOnset states in synthetichealth/synthea @ v4.0.0:
#   src/main/resources/modules/{breast_cancer,lung_cancer,colorectal_cancer}.json
# Suspicion/situation codes and precancerous findings (e.g. "Suspected lung
# cancer", "Polyp of colon") are deliberately excluded -- only confirmed
# diagnosis stages count.
CANCER_CODES = {
    "254837009": "breast",
    "254637007": "lung",
    "254632001": "lung",
    "424132000": "lung",
    "425048006": "lung",
    "422968005": "lung",
    "423121009": "lung",
    "67811000119102": "lung",
    "67821000119109": "lung",
    "67831000119107": "lung",
    "67841000119103": "lung",
    "93761005": "colorectal",
    "109838007": "colorectal",
    "363406005": "colorectal",
    "94260004": "colorectal",
}

# Reference date passed to Synthea via -r (config/synthea_run.json). Used to
# compute patient age for the base table.
REFERENCE_DATE = pd.Timestamp("2026-09-01")


def _read_raw(raw_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    patients = pd.read_csv(raw_dir / "patients.csv", dtype=str)
    conditions = pd.read_csv(raw_dir / "conditions.csv", dtype=str)
    return patients, conditions


def build_base_table(patients: pd.DataFrame, conditions: pd.DataFrame) -> pd.DataFrame:
    """One row per patient with >=1 target cancer diagnosis.

    Rule for multiple diagnoses: a patient's cancer_type and diagnosis_date
    are taken from their EARLIEST matching condition row (their first-ever
    diagnosis among the three types) -- this is their index cancer, i.e. the
    one a patient support program would have enrolled them for. Any later,
    distinct cancer (e.g. a second primary) is not represented separately.
    """
    cancer_conditions = conditions[conditions["CODE"].isin(CANCER_CODES)].copy()
    cancer_conditions["cancer_type"] = cancer_conditions["CODE"].map(CANCER_CODES)
    cancer_conditions["START"] = pd.to_datetime(cancer_conditions["START"])

    first_dx = (
        cancer_conditions.sort_values("START")
        .groupby("PATIENT", as_index=False)
        .first()[["PATIENT", "START", "cancer_type"]]
        .rename(columns={"PATIENT": "patient_id", "START": "diagnosis_date"})
    )

    patients = patients.rename(columns={"Id": "patient_id"})
    patients["BIRTHDATE"] = pd.to_datetime(patients["BIRTHDATE"])
    patients["DEATHDATE"] = pd.to_datetime(patients["DEATHDATE"])

    base = first_dx.merge(
        patients[["patient_id", "BIRTHDATE", "DEATHDATE", "GENDER", "STATE"]],
        on="patient_id",
        how="left",
    )
    base["age"] = ((REFERENCE_DATE - base["BIRTHDATE"]).dt.days // 365).astype(int)
    base["age_at_diagnosis"] = (
        (base["diagnosis_date"] - base["BIRTHDATE"]).dt.days // 365
    ).astype(int)
    base["days_diagnosis_to_death"] = (
        base["DEATHDATE"] - base["diagnosis_date"]
    ).dt.days

    base = base.rename(
        columns={
            "BIRTHDATE": "birth_date",
            "DEATHDATE": "death_date",
            "GENDER": "sex",
            "STATE": "state",
        }
    )
    return base[
        [
            "patient_id",
            "birth_date",
            "age",
            "sex",
            "state",
            "cancer_type",
            "diagnosis_date",
            "death_date",
            "age_at_diagnosis",
            "days_diagnosis_to_death",
        ]
    ].sort_values("patient_id").reset_index(drop=True)


def load_base_table() -> pd.DataFrame:
    """Fresh Synthea output if present, else the committed cache. Logs which."""
    if (RAW_DIR / "patients.csv").exists() and (RAW_DIR / "conditions.csv").exists():
        print(f"[synthea_base] building from fresh Synthea output at {RAW_DIR}")
        patients, conditions = _read_raw(RAW_DIR)
        return build_base_table(patients, conditions)

    if SEED_PATH.exists():
        print(f"[synthea_base] no fresh Synthea output found; using cached extract at {SEED_PATH}")
        df = pd.read_csv(SEED_PATH, dtype={"patient_id": str})
        for col in ("birth_date", "diagnosis_date", "death_date"):
            df[col] = pd.to_datetime(df[col])
        return df

    raise FileNotFoundError(
        f"No Synthea raw output at {RAW_DIR} and no cached extract at {SEED_PATH}. "
        "Run scripts/run_synthea.py first."
    )


if __name__ == "__main__":
    table = load_base_table()
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(SEED_PATH, index=False)
    print(f"[synthea_base] wrote {len(table)} rows to {SEED_PATH}")
