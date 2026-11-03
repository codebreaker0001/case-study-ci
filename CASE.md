# The case

Role: I'm an onshore Forward Deployed Engineer on a pharma account (oncology patient support program, market access).

Key terms:
- Adherence: whether patients take their medicine as prescribed over time
- PDC (proportion of days covered): share of days in a period with medicine on hand, computed from pharmacy fill records
- Specialty pharmacy hub: collects fill records from specialty pharmacies in one place
- CRM: system where the client's case managers record notes about patients
- Patient support program: manufacturer-run program that helps patients start and stay on therapy

Situation: 18 months ago my team built an adherence pipeline from specialty pharmacy hub fills and program enrolment records. The client's BI team separately built a CRM-based dashboard. The two disagree. The VP of Market Access presents program ROI to the board on Friday and asks which number is right.

Exhibit 1: Definitions
| | Our pipeline | Client CRM dashboard |
|---|---|---|
| Population | All enrolled patients | Patients with at least 1 specialty pharmacy fill |
| Measure | PDC of 80% or more | "Refilled on schedule" flag, self-reported by case managers |
| Source | Specialty pharmacy hub fills | Case-manager notes in the CRM |

Exhibit 2: Adherence, quarter over quarter
| | This quarter | Last quarter |
|---|---|---|
| Our pipeline | 58% | 64% |
| Client CRM dashboard | 71% | 72% |

Requirements:
1. Generate a synthetic patient-level dataset with enrolments, hub fills and CRM case-manager notes, including free-text notes. Its aggregates must roughly reproduce Exhibit 2.
2. Compute both metrics from that data and build a bridge that splits the gap into population, measure-definition and data-source effects, for both quarters.
3. Use an LLM to extract adherence signals (missed doses, delays, discontinuation reasons) from the free-text notes, and measure how well the extraction agrees with fill data on a labelled sample.
4. Propose a unified adherence definition and implement it, with data-quality checks that would catch the two sources drifting apart again.
5. Show what is defensible to report on Friday, with the uncertainty attached.

Deliverables: runnable code, the synthetic data generator, an HTML reconciliation view (gap bridge, cohort filters, quarter toggle), and an optional slide deck of 8 slides or fewer.

My tool choices: Synthea (open-source synthetic patient generator) as the base for patient data, and the Groq API for the LLM.
