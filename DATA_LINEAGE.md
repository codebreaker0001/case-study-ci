# Data lineage: Synthea base patient table

`data/synthea_seed/cancer_patients_base.csv` (built by `src/generate/synthea_base.py`)
is one row per Synthea patient with a confirmed diagnosis of breast, lung, or
colorectal cancer. Source: [Synthea](https://github.com/synthetichealth/synthea)
v4.0.0, Massachusetts population, seed 42, reference date 2026-09-01 (see
`config/synthea_run.json`).

| Column | Source file | Source field(s) | Notes |
|---|---|---|---|
| `patient_id` | `patients.csv` | `Id` | Synthea's UUID for the patient |
| `birth_date` | `patients.csv` | `BIRTHDATE` | |
| `age` | *derived* | `BIRTHDATE` | `(REFERENCE_DATE - birth_date).days // 365`. REFERENCE_DATE = 2026-09-01, the `-r` flag passed to Synthea. For deceased patients this is a hypothetical "age if still alive today" figure, not age at death -- see Decisions log caveat. |
| `sex` | `patients.csv` | `GENDER` | |
| `state` | `patients.csv` | `STATE` | All patients are Massachusetts in this run (single-state generation) |
| `cancer_type` | *derived* | `conditions.csv`: `CODE` | One of `breast`/`lung`/`colorectal`. Mapped from SNOMED CT diagnosis codes (see below). If a patient has condition rows matching more than one cancer type, the type of their EARLIEST matching row is kept (their index cancer) |
| `diagnosis_date` | *derived* | `conditions.csv`: `START` | START date of the patient's earliest matching condition row, using the same earliest-row rule as `cancer_type` |
| `death_date` | `patients.csv` | `DEATHDATE` | Null if alive at reference date |

## Cancer diagnosis codes

Pulled directly from the `ConditionOnset` states in Synthea's own module
source (`src/main/resources/modules/{breast_cancer,lung_cancer,colorectal_cancer}.json`
at tag v4.0.0), not from memory or general medical references:

| Cancer type | SNOMED CT code | Display |
|---|---|---|
| breast | 254837009 | Malignant neoplasm of breast (disorder) |
| lung | 254637007 | Non-small cell lung cancer (disorder) |
| lung | 254632001 | Small cell carcinoma of lung (disorder) |
| lung | 424132000 / 425048006 / 422968005 / 423121009 | NSCLC, TNM stage 1-4 |
| lung | 67811000119102 / 67821000119109 / 67831000119107 / 67841000119103 | SCLC, TNM stage 1-4 |
| colorectal | 93761005 | Primary malignant neoplasm of colon, stage I |
| colorectal | 109838007 | Overlapping malignant neoplasm of colon, stage II |
| colorectal | 363406005 | Malignant neoplasm of colon, stage III |
| colorectal | 94260004 | Metastatic malignant neoplasm to colon, stage IV |

Deliberately excluded: "suspected"/"situation" codes (e.g. 162573006
"Suspected lung cancer") and precancerous findings (e.g. 68496003 "Polyp of
colon", 713197008 "Recurrent rectal polyp") -- these are not confirmed
diagnoses.

## Loader behavior

`synthea_base.load_base_table()` uses fresh Synthea output from
`data/synthea_raw/csv/` if present, else falls back to the committed cache at
`data/synthea_seed/cancer_patients_base.csv`, logging which path it took.
