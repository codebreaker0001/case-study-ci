"""Build outputs/reconciliation.html: a self-contained reconciliation view
with an embedded per-patient-quarter dataset so cohort filters and the
sequential/Shapley toggle can recompute the bridge entirely client-side.

Run as a module from the project root: `python -m src.viz.build_reconciliation`
"""
import json
from pathlib import Path

import pandas as pd

from src.generate.overlay import get_quarters
from src.metrics.metrics import (
    GRACE_DAYS,
    PDC_THRESHOLD,
    crm_flag_by_patient,
    filler_patient_ids,
    on_schedule_by_patient,
    pdc_by_patient,
    population_mask,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = ROOT / "outputs" / "reconciliation.html"


def per_patient_quarter_rows(enrolments, hub_fills, crm_notes, q):
    pop = enrolments[population_mask(enrolments, q["start"], q["end"])].copy()
    fillers = filler_patient_ids(hub_fills, q["end"])
    pop["is_filler"] = pop["patient_id"].isin(fillers)

    pdc = pdc_by_patient(pop, hub_fills, q["start"], q["end"])
    pop["pdc80"] = (pdc.reindex(pop["patient_id"]).values >= PDC_THRESHOLD)

    hub_flags = on_schedule_by_patient(pop, hub_fills, q["start"], q["end"], GRACE_DAYS)
    pop["hub_onsched"] = hub_flags.reindex(pop["patient_id"]).values
    pop.loc[~pop["is_filler"], "hub_onsched"] = False

    crm_flags = crm_flag_by_patient(pop, crm_notes, q["end"])
    pop["crm_known"] = crm_flags.reindex(pop["patient_id"]).notna().values
    pop["crm_flag"] = crm_flags.reindex(pop["patient_id"]).fillna(False).values.astype(bool)

    rows = pop[[
        "patient_id", "cancer_type", "region", "payer_type", "case_manager",
        "is_filler", "pdc80", "hub_onsched", "crm_known", "crm_flag",
    ]].copy()
    for c in ["is_filler", "pdc80", "hub_onsched", "crm_known", "crm_flag"]:
        rows[c] = rows[c].astype(bool)
    return rows.to_dict(orient="records")


def build():
    enrolments = pd.read_csv(ROOT / "data" / "enrolments.csv")
    hub_fills = pd.read_csv(ROOT / "data" / "hub_fills.csv")
    crm_notes = pd.read_csv(ROOT / "data" / "crm_notes.csv")
    for col in ("enrollment_date", "death_date", "disenrollment_date"):
        enrolments[col] = pd.to_datetime(enrolments[col])
    hub_fills["fill_date"] = pd.to_datetime(hub_fills["fill_date"])
    crm_notes["note_date"] = pd.to_datetime(crm_notes["note_date"])

    bridge = json.loads((ROOT / "outputs" / "bridge.json").read_text())

    quarters = {q["name"]: q for q in get_quarters()}
    data = {"quarters": {}}
    for qname in ("Q3", "Q4"):
        q = quarters[qname]
        data["quarters"][qname] = {
            "label": q["label"],
            "rows": per_patient_quarter_rows(enrolments, hub_fills, crm_notes, q),
            "bridge": bridge["quarters"][qname],
        }
    data["quarter_over_quarter"] = bridge["quarter_over_quarter"]

    cohorts = {
        "cancer_type": sorted(enrolments["cancer_type"].dropna().unique().tolist()),
        "region": sorted(enrolments["region"].dropna().unique().tolist()),
        "payer_type": sorted(enrolments["payer_type"].dropna().unique().tolist()),
        "case_manager": sorted(enrolments["case_manager"].dropna().unique().tolist()),
    }

    unified = None
    unified_path = ROOT / "outputs" / "unified_metric.json"
    if unified_path.exists():
        unified = json.loads(unified_path.read_text())

    dq = None
    dq_path = ROOT / "outputs" / "dq_results.json"
    if dq_path.exists():
        dq = json.loads(dq_path.read_text())

    extract = None
    extract_path = ROOT / "outputs" / "extraction_eval.json"
    if extract_path.exists():
        extract = json.loads(extract_path.read_text())

    html = TEMPLATE.replace("__DATA_JSON__", json.dumps(data)) \
        .replace("__COHORTS_JSON__", json.dumps(cohorts)) \
        .replace("__UNIFIED_JSON__", json.dumps(unified)) \
        .replace("__DQ_JSON__", json.dumps(dq)) \
        .replace("__EXTRACT_JSON__", json.dumps(extract))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"[reconciliation] wrote {OUTPUT_PATH}")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Adherence Reconciliation</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.4/chart.umd.min.js"></script>
<style>
  :root {
    --bg: #f7f8fa; --card: #ffffff; --text: #1a1d23; --muted: #6b7280;
    --border: #e5e7eb; --accent: #2563eb; --pipeline: #2563eb; --crm: #f59e0b;
    --unified: #10b981; --good: #10b981; --bad: #ef4444;
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
  header { padding: 24px 32px; background:var(--card); border-bottom:1px solid var(--border); }
  header h1 { margin:0 0 4px; font-size: 22px; }
  header p { margin:0; color:var(--muted); font-size: 14px; }
  main { max-width: 1200px; margin: 0 auto; padding: 24px 32px 64px; }
  .row { display:flex; gap:16px; flex-wrap:wrap; margin-bottom:24px; }
  .card { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:18px 20px; }
  .headline { flex:1; min-width:180px; text-align:center; }
  .headline .value { font-size: 32px; font-weight:700; }
  .headline .label { color:var(--muted); font-size:13px; margin-top:4px; }
  .headline.pipeline .value { color: var(--pipeline); }
  .headline.crm .value { color: var(--crm); }
  .headline.unified .value { color: var(--unified); }
  .controls { display:flex; gap:16px; flex-wrap:wrap; align-items:flex-end; margin-bottom:20px; }
  .controls .group { display:flex; flex-direction:column; gap:4px; }
  .controls label { font-size:12px; color:var(--muted); }
  select, button { font-size:14px; padding:6px 10px; border-radius:6px; border:1px solid var(--border); background:white; }
  button.toggle { cursor:pointer; }
  button.toggle.active { background:var(--accent); color:white; border-color:var(--accent); }
  .section-title { font-size:15px; font-weight:600; margin: 28px 0 10px; }
  canvas { max-height: 380px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th, td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--border); }
  .pass { color: var(--good); font-weight:600; }
  .warn { color: #d97706; font-weight:600; }
  .fail { color: var(--bad); font-weight:600; }
  .explanation { color:var(--muted); font-size:14px; line-height:1.5; }
  .n { color:var(--muted); font-size:12px; }
</style>
</head>
<body>
<header>
  <h1>Adherence Reconciliation</h1>
  <p>Pipeline vs. CRM dashboard, reconciled with a population / measure / source gap bridge. Cohort filters recompute everything below client-side.</p>
</header>
<main>
  <div class="controls card">
    <div class="group">
      <label>Quarter</label>
      <div>
        <button class="toggle" data-quarter="Q3">Last quarter (Q3)</button>
        <button class="toggle" data-quarter="Q4">This quarter (Q4)</button>
      </div>
    </div>
    <div class="group">
      <label>Bridge method</label>
      <div>
        <button class="toggle" data-method="sequential">Sequential</button>
        <button class="toggle" data-method="shapley">Shapley</button>
      </div>
    </div>
    <div class="group"><label>Cancer type</label><select id="f-cancer_type"><option value="">All</option></select></div>
    <div class="group"><label>Region</label><select id="f-region"><option value="">All</option></select></div>
    <div class="group"><label>Payer type</label><select id="f-payer_type"><option value="">All</option></select></div>
    <div class="group"><label>Case manager</label><select id="f-case_manager"><option value="">All</option></select></div>
  </div>

  <div class="row">
    <div class="card headline pipeline"><div class="value" id="hl-pipeline">-</div><div class="label">Pipeline (PDC&ge;80%, all enrolled)</div><div class="n" id="hl-pipeline-n"></div></div>
    <div class="card headline crm"><div class="value" id="hl-crm">-</div><div class="label">CRM dashboard (on-schedule flag, fillers)</div><div class="n" id="hl-crm-n"></div></div>
    <div class="card headline unified"><div class="value" id="hl-unified">-</div><div class="label">Unified definition</div><div class="n" id="hl-unified-n"></div></div>
  </div>

  <div class="card">
    <div class="section-title">Gap bridge</div>
    <canvas id="bridgeChart"></canvas>
    <p class="explanation" id="qoq-explanation"></p>
  </div>

  <div class="card" id="dq-card" style="margin-top:24px; display:none;">
    <div class="section-title">Data quality checks</div>
    <table id="dq-table"><thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead><tbody></tbody></table>
  </div>

  <div class="card" id="extract-card" style="margin-top:24px; display:none;">
    <div class="section-title">LLM extraction evaluation (vs. labelled sample)</div>
    <table id="extract-table"><thead><tr><th>Signal</th><th>Precision</th><th>Recall</th><th>F1</th></tr></thead><tbody></tbody></table>
    <p class="explanation" id="extract-agreement"></p>
  </div>
</main>

<script>
const DATA = __DATA_JSON__;
const COHORTS = __COHORTS_JSON__;
const UNIFIED = __UNIFIED_JSON__;
const DQ = __DQ_JSON__;
const EXTRACT = __EXTRACT_JSON__;

let state = { quarter: "Q4", method: "sequential",
  cancer_type: "", region: "", payer_type: "", case_manager: "" };

function populateSelect(id, key) {
  const sel = document.getElementById(id);
  COHORTS[key].forEach(v => {
    const opt = document.createElement("option");
    opt.value = v; opt.textContent = v;
    sel.appendChild(opt);
  });
  sel.addEventListener("change", () => { state[key] = sel.value; render(); });
}
["cancer_type", "region", "payer_type", "case_manager"].forEach(k => populateSelect("f-" + k, k));

document.querySelectorAll('button[data-quarter]').forEach(b => b.addEventListener('click', () => {
  state.quarter = b.dataset.quarter; render();
}));
document.querySelectorAll('button[data-method]').forEach(b => b.addEventListener('click', () => {
  state.method = b.dataset.method; render();
}));

function filteredRows() {
  const rows = DATA.quarters[state.quarter].rows;
  return rows.filter(r =>
    (!state.cancer_type || r.cancer_type === state.cancer_type) &&
    (!state.region || r.region === state.region) &&
    (!state.payer_type || r.payer_type === state.payer_type) &&
    (!state.case_manager || r.case_manager === state.case_manager)
  );
}

function valueFor(rows, p, m, s) {
  let pop = rows;
  if (p) pop = pop.filter(r => r.is_filler);
  if (pop.length === 0) return [NaN, 0];
  if (s) {
    const known = pop.filter(r => r.crm_known);
    if (known.length === 0) return [NaN, 0];
    return [known.filter(r => r.crm_flag).length / known.length, known.length];
  }
  if (m) {
    return [pop.filter(r => r.hub_onsched).length / pop.length, pop.length];
  }
  return [pop.filter(r => r.pdc80).length / pop.length, pop.length];
}

function sequential(rows) {
  const [v0, n0] = valueFor(rows, false, false, false);
  const [v1] = valueFor(rows, true, false, false);
  const [v2] = valueFor(rows, true, true, false);
  const [v3, n3] = valueFor(rows, true, true, true);
  return {
    labels: ["Pipeline", "+ Population", "+ Measure", "= CRM"],
    values: [v0, v1 - v0, v2 - v1, v3 - v2],
    bases: [0, v0, v1, v2],
    pipeline: v0, crm: v3, pipeline_n: n0, crm_n: n3,
  };
}

function shapley(rows) {
  const factors = ["population", "measure", "source"];
  const perms = permutations(factors);
  const contrib = { population: [], measure: [], source: [] };
  perms.forEach(order => {
    let present = new Set();
    let prev = valueFor(rows, false, false, false)[0];
    order.forEach(f => {
      present.add(f);
      const cur = valueFor(rows, present.has("population"), present.has("measure"), present.has("source"))[0];
      contrib[f].push(cur - prev);
      prev = cur;
    });
  });
  const avg = k => contrib[k].reduce((a, b) => a + b, 0) / contrib[k].length;
  const [v0, n0] = valueFor(rows, false, false, false);
  const [v3, n3] = valueFor(rows, true, true, true);
  return {
    labels: ["Pipeline", "Population", "Measure", "Source", "= CRM"],
    values: [v0, avg("population"), avg("measure"), avg("source")],
    bases: [0, v0, v0 + avg("population"), v0 + avg("population") + avg("measure")],
    pipeline: v0, crm: v3, pipeline_n: n0, crm_n: n3,
  };
}

function permutations(arr) {
  if (arr.length <= 1) return [arr];
  const result = [];
  arr.forEach((item, i) => {
    const rest = arr.slice(0, i).concat(arr.slice(i + 1));
    permutations(rest).forEach(p => result.push([item].concat(p)));
  });
  return result;
}

let chart = null;
function render() {
  const rows = filteredRows();
  const result = state.method === "shapley" ? shapley(rows) : sequential(rows);

  document.getElementById("hl-pipeline").textContent = (result.pipeline * 100).toFixed(1) + "%";
  document.getElementById("hl-crm").textContent = (result.crm * 100).toFixed(1) + "%";
  document.getElementById("hl-pipeline-n").textContent = "n=" + result.pipeline_n;
  document.getElementById("hl-crm-n").textContent = "n=" + result.crm_n;

  if (UNIFIED && UNIFIED[state.quarter]) {
    document.getElementById("hl-unified").textContent = (UNIFIED[state.quarter].metric * 100).toFixed(1) + "%";
    document.getElementById("hl-unified-n").textContent = "n=" + UNIFIED[state.quarter].n;
  } else {
    document.getElementById("hl-unified").textContent = "pending";
    document.getElementById("hl-unified-n").textContent = "";
  }

  document.querySelectorAll('button[data-quarter]').forEach(b => b.classList.toggle('active', b.dataset.quarter === state.quarter));
  document.querySelectorAll('button[data-method]').forEach(b => b.classList.toggle('active', b.dataset.method === state.method));

  const ctx = document.getElementById("bridgeChart").getContext("2d");
  if (chart) chart.destroy();
  chart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: result.labels,
      datasets: [
        { label: "base", data: result.bases, backgroundColor: "rgba(0,0,0,0)" },
        { label: "effect", data: result.values, backgroundColor: result.values.map((v,i) => i===0 ? "#2563eb" : (v>=0 ? "#10b981" : "#ef4444")) },
      ]
    },
    options: {
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => (c.datasetIndex===1 ? (c.raw*100).toFixed(1)+"%" : "") } } },
      scales: { x: { stacked: true }, y: { stacked: true, ticks: { callback: v => (v*100).toFixed(0)+"%" } } }
    }
  });

  document.getElementById("qoq-explanation").textContent = DATA.quarter_over_quarter.explanation;

  if (DQ) {
    document.getElementById("dq-card").style.display = "block";
    const tbody = document.querySelector("#dq-table tbody");
    tbody.innerHTML = "";
    DQ.checks.forEach(c => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${c.name}</td><td class="${c.status}">${c.status.toUpperCase()}</td><td>${c.detail}</td>`;
      tbody.appendChild(tr);
    });
  }

  if (EXTRACT) {
    document.getElementById("extract-card").style.display = "block";
    const tbody = document.querySelector("#extract-table tbody");
    tbody.innerHTML = "";
    Object.entries(EXTRACT.per_signal).forEach(([sig, m]) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${sig}</td><td>${m.precision.toFixed(2)}</td><td>${m.recall.toFixed(2)}</td><td>${m.f1.toFixed(2)}</td>`;
      tbody.appendChild(tr);
    });
    document.getElementById("extract-agreement").textContent =
      `Agreement with fill-gap signal: ${(EXTRACT.agreement_with_fill_gaps*100).toFixed(1)}% (n=${EXTRACT.n})`;
  }
}

render();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    build()
