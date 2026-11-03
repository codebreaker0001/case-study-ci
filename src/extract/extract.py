"""LLM extraction of adherence signals from free-text CRM notes.

Uses the Groq SDK (GROQ_API_KEY from .env) with JSON mode, temperature 0,
pydantic validation, a disk cache, and backoff on 429. Falls back to a
rule-based extractor (matching the abbreviations our note generator uses)
if no API key is set, so the pipeline still runs end to end.

Evaluates against ground_truth_notes.csv (precision/recall/F1 per signal)
AND, separately, agreement with an independent fill-derived gap signal.
"""
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Optional

import pandas as pd
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "data" / "llm_cache"
OUTPUT_PATH = ROOT / "outputs" / "extraction_eval.json"

CONFIG = {
    "model": "openai/gpt-oss-120b",  # verified via client.models.list() against this account; check console.groq.com/docs/models if stale
    "temperature": 0,
    "sample_size": 150,
    "seed": 42,
    "max_retries": 4,
}

SIGNALS = ["missed_doses", "delay", "discontinued", "therapy_hold", "hold_clinician_directed"]

SYSTEM_PROMPT = (
    "Extract adherence signals from a clinical case-manager note about a cancer "
    "patient on a specialty therapy. Notes use medical abbreviations (pt=patient, "
    "f/u=follow-up, d/c=discontinued, tx=treatment, s/e=side effects, dz=disease). "
    "Return ONLY JSON with keys: missed_doses (bool), delay (bool), discontinued (bool), "
    "discontinuation_reason (string or null), therapy_hold (bool), "
    "hold_clinician_directed (bool). If the note has no adherence information, all "
    "booleans should be false and discontinuation_reason null."
)


class ExtractedSignals(BaseModel):
    missed_doses: bool = False
    delay: bool = False
    discontinued: bool = False
    discontinuation_reason: Optional[str] = None
    therapy_hold: bool = False
    hold_clinician_directed: bool = False


def _cache_key(note_text: str) -> str:
    h = hashlib.sha256((CONFIG["model"] + "|" + note_text).encode()).hexdigest()
    return h


def _cache_path(note_text: str) -> Path:
    return CACHE_DIR / f"{_cache_key(note_text)}.json"


def rule_based_extract(note_text: str) -> ExtractedSignals:
    t = note_text.lower()
    missed = "missed" in t or "forgot" in t
    delay = "delay" in t or "late" in t or "backorder" in t or "lost track" in t
    discontinued = "d/c" in t or "discontinu" in t
    hold = "hold" in t
    clinician_directed = hold and ("md" in t or "onc" in t or "per md" in t or "ordered" in t)
    reason = None
    if discontinued:
        for r in ["disease progression", "toxicity", "patient choice", "lost to follow-up"]:
            if r in t:
                reason = r
                break
        reason = reason or "unspecified"
    return ExtractedSignals(
        missed_doses=missed, delay=delay, discontinued=discontinued,
        discontinuation_reason=reason, therapy_hold=hold, hold_clinician_directed=clinician_directed,
    )


def groq_extract(note_text: str, client) -> ExtractedSignals:
    cache_path = _cache_path(note_text)
    if cache_path.exists():
        return ExtractedSignals(**json.loads(cache_path.read_text()))

    for attempt in range(CONFIG["max_retries"]):
        try:
            resp = client.chat.completions.create(
                model=CONFIG["model"],
                temperature=CONFIG["temperature"],
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": note_text},
                ],
            )
            parsed = ExtractedSignals.model_validate_json(resp.choices[0].message.content)
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(parsed.model_dump_json())
            return parsed
        except Exception as e:
            if "429" in str(e) and attempt < CONFIG["max_retries"] - 1:
                time.sleep(2 ** attempt)
                continue
            raise


def get_client():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    if not os.environ.get("GROQ_API_KEY"):
        return None
    from groq import Groq
    return Groq()


def extract(note_text: str, client) -> ExtractedSignals:
    if client is None:
        return rule_based_extract(note_text)
    return groq_extract(note_text, client)


def precision_recall_f1(y_true: pd.Series, y_pred: pd.Series) -> dict:
    tp = ((y_true) & (y_pred)).sum()
    fp = ((~y_true) & (y_pred)).sum()
    fn = ((y_true) & (~y_pred)).sum()
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def run_evaluation():
    crm_notes = pd.read_csv(ROOT / "data" / "crm_notes.csv")
    ground_truth = pd.read_csv(ROOT / "data" / "ground_truth_notes.csv")
    merged = crm_notes.merge(ground_truth, on="note_id")

    sample = merged.sample(n=min(CONFIG["sample_size"], len(merged)), random_state=CONFIG["seed"])

    client = get_client()
    used_model = "rule_based_fallback" if client is None else CONFIG["model"]
    print(f"[extract] using: {used_model} (GROQ_API_KEY {'found' if client else 'not set'})")

    predictions = [extract(text, client) for text in sample["note_text"]]
    pred_df = pd.DataFrame([p.model_dump() for p in predictions]).reset_index(drop=True)
    sample = sample.reset_index(drop=True)

    per_signal = {}
    for sig in SIGNALS:
        per_signal[sig] = precision_recall_f1(sample[sig].astype(bool), pred_df[sig].astype(bool))

    # agreement with fill gaps: hub-derived "on schedule" vs extracted missed/delay
    enrolments = pd.read_csv(ROOT / "data" / "enrolments.csv")
    hub_fills = pd.read_csv(ROOT / "data" / "hub_fills.csv")
    for col in ("enrollment_date", "death_date", "disenrollment_date"):
        enrolments[col] = pd.to_datetime(enrolments[col])
    hub_fills["fill_date"] = pd.to_datetime(hub_fills["fill_date"])
    crm_notes["note_date"] = pd.to_datetime(crm_notes["note_date"])

    from src.generate.overlay import get_quarters
    from src.metrics.metrics import on_schedule_by_patient

    sample_dates = crm_notes.set_index("note_id").loc[sample["note_id"], "note_date"]
    agreements = []
    for q in get_quarters():
        in_q = sample_dates[(sample_dates > q["start"]) & (sample_dates <= q["end"])]
        if len(in_q) == 0:
            continue
        pop = enrolments[enrolments["patient_id"].isin(
            sample.set_index("note_id").loc[in_q.index, "patient_id"]
        )]
        hub_flags = on_schedule_by_patient(pop, hub_fills, q["start"], q["end"])
        for note_id in in_q.index:
            pid = sample.set_index("note_id").loc[note_id, "patient_id"]
            extracted_gap = predictions[sample.index[sample["note_id"] == note_id][0]]
            extracted_gap_flag = extracted_gap.missed_doses or extracted_gap.delay
            fill_gap_flag = not hub_flags.get(pid, True)
            agreements.append(extracted_gap_flag == fill_gap_flag)

    agreement_rate = sum(agreements) / len(agreements) if agreements else float("nan")

    result = {
        "model": used_model,
        "n": len(sample),
        "per_signal": per_signal,
        "agreement_with_fill_gaps": agreement_rate,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    result = run_evaluation()
    print(json.dumps(result, indent=2))
