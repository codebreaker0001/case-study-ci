"""Measure cancer incidence and diagnosis recency in a Synthea raw output folder.

Run after any Synthea generation (data/synthea_raw/csv/) to work out what
population size is needed for a target number of usable cancer patients, e.g.
when scaling up from the current 5,000-patient run. Not part of the main
pipeline.
"""
import csv
from collections import defaultdict
from datetime import date

RAW = "data/synthea_raw/csv"

BREAST = {"254837009"}
LUNG = {
    "254637007", "254632001", "424132000", "425048006", "422968005", "423121009",
    "67811000119102", "67821000119109", "67831000119107", "67841000119103",
}
COLORECTAL = {"93761005", "109838007", "363406005", "94260004"}

TYPE_OF = {}
for code in BREAST:
    TYPE_OF[code] = "breast"
for code in LUNG:
    TYPE_OF[code] = "lung"
for code in COLORECTAL:
    TYPE_OF[code] = "colorectal"

ALL_CODES = set(TYPE_OF)

REF_DATE = date(2026, 9, 1)


def parse(d):
    return date.fromisoformat(d[:10]) if d else None


patients = {}
with open(f"{RAW}/patients.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        patients[row["Id"]] = parse(row["DEATHDATE"])

onsets = defaultdict(list)  # patient -> list of (date, type)
with open(f"{RAW}/conditions.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        code = row["CODE"]
        if code in ALL_CODES:
            onsets[row["PATIENT"]].append((parse(row["START"]), TYPE_OF[code]))

total_patients = len(patients)
cancer_patients = len(onsets)
print(f"total patients in run: {total_patients}")
print(f"patients with >=1 target cancer diagnosis: {cancer_patients} ({cancer_patients/total_patients:.2%})")

by_type = defaultdict(int)
recent_3y = 0
recent_5y = 0
alive_at_ref = 0
for pid, events in onsets.items():
    events.sort()
    first_date, first_type = events[0]
    by_type[first_type] += 1
    death = patients[pid]
    if (REF_DATE - first_date).days <= 3 * 365:
        recent_3y += 1
    if (REF_DATE - first_date).days <= 5 * 365:
        recent_5y += 1
    if death is None or death >= first_date:
        if death is None:
            alive_at_ref += 1

print("by first-diagnosed type:", dict(by_type))
print(f"diagnosed within 3y of reference date: {recent_3y} ({recent_3y/cancer_patients:.1%} of cancer patients)")
print(f"diagnosed within 5y of reference date: {recent_5y} ({recent_5y/cancer_patients:.1%} of cancer patients)")
print(f"still alive at reference date (no deathdate): {alive_at_ref} ({alive_at_ref/cancer_patients:.1%})")
