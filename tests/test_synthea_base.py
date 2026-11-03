import pandas as pd
import pytest

from src.generate import synthea_base


def _fake_raw():
    patients = pd.DataFrame(
        {
            "Id": ["p1", "p2", "p3"],
            "BIRTHDATE": ["1960-01-01", "1970-06-15", "1990-03-20"],
            "DEATHDATE": ["2020-01-01", "", ""],
            "GENDER": ["F", "M", "F"],
            "STATE": ["Massachusetts", "Massachusetts", "Massachusetts"],
        }
    )
    conditions = pd.DataFrame(
        {
            "START": ["2015-05-01", "2010-01-01", "2016-02-02", "2022-01-01"],
            "STOP": ["", "2012-01-01", "", ""],
            "PATIENT": ["p1", "p2", "p2", "p3"],
            "ENCOUNTER": ["e1", "e2", "e3", "e4"],
            "SYSTEM": ["SNOMED-CT"] * 4,
            # p2 has two matching codes (stage progression): earliest should win
            "CODE": ["254837009", "93761005", "363406005", "254632001"],
            "DESCRIPTION": ["Malignant neoplasm of breast (disorder)",
                             "Primary malignant neoplasm of colon (disorder)",
                             "Malignant neoplasm of colon (disorder)",
                             "Small cell carcinoma of lung (disorder)"],
        }
    )
    return patients, conditions


def test_no_duplicate_patient_ids():
    patients, conditions = _fake_raw()
    base = synthea_base.build_base_table(patients, conditions)
    assert base["patient_id"].is_unique


def test_every_patient_has_cancer_diagnosis():
    patients, conditions = _fake_raw()
    base = synthea_base.build_base_table(patients, conditions)
    assert base["cancer_type"].isin(["breast", "lung", "colorectal"]).all()
    assert base["diagnosis_date"].notna().all()


def test_multiple_diagnoses_keeps_earliest():
    patients, conditions = _fake_raw()
    base = synthea_base.build_base_table(patients, conditions)
    p2 = base[base["patient_id"] == "p2"].iloc[0]
    assert p2["cancer_type"] == "colorectal"
    assert p2["diagnosis_date"] == pd.Timestamp("2010-01-01")


def test_dates_valid():
    patients, conditions = _fake_raw()
    base = synthea_base.build_base_table(patients, conditions)
    assert (base["diagnosis_date"] >= base["birth_date"]).all()
    with_death = base[base["death_date"].notna()]
    assert (with_death["death_date"] >= with_death["diagnosis_date"]).all()


def test_loader_falls_back_to_cache(tmp_path, monkeypatch):
    patients, conditions = _fake_raw()
    base = synthea_base.build_base_table(patients, conditions)

    missing_raw_dir = tmp_path / "no_such_raw"
    cache_dir = tmp_path / "seed"
    cache_dir.mkdir()
    cache_path = cache_dir / "cancer_patients_base.csv"
    base.to_csv(cache_path, index=False)

    monkeypatch.setattr(synthea_base, "RAW_DIR", missing_raw_dir)
    monkeypatch.setattr(synthea_base, "SEED_PATH", cache_path)

    loaded = synthea_base.load_base_table()
    assert len(loaded) == len(base)
    assert set(loaded["patient_id"]) == set(base["patient_id"])
