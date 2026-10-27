# Cross-Examiner Investigation Report

Question: Not specified
Evidence source: zetaris
Records analyzed: 81
Discrepancies identified: 4

> A discrepancy signals a question to investigate; it does not, by itself, establish which source is correct.

## Where the evidence came from

- **unified_semantic_layer**: 262 records from lightning.metastore.cross_examiner.coverage_observations.coverage_observation (zetaris_usl)
- **synthetic_programme_reports**: 181 records from the semantic layer (excluded) — generated records are never evidence

## Sources and their lineage

> Every reported number comes from one of these sources. A source that republishes another series is counted once with the series it republishes, so it can never confirm the numbers it was derived from.

| Measure | Source | Series it comes from | Republishes | Type |
|---|---|---|---|---|
| Household survey coverage (65.3%) | Cameroon DHS 2018 survey report | Cameroon household survey coverage (independent household sampling) (`cameroon_household_survey`) | - | pdf |
| Administrative coverage (71.0%) | WUENIC country profile 2023 revision | Cameroon administrative reporting (WHO/UNICEF Joint Reporting Form), as published in the country profile (`cameroon_admin_jrf`) | - | pdf |
| WUENIC estimate (61.0%) | WUENIC 2025 revision | WHO/UNICEF Estimates of National Immunization Coverage (WUENIC), 2025 revision (`wuenic_2025`) | - | xlsx |
| Administrative coverage (74.0%) | WUENIC country profile 2023 revision | Cameroon administrative reporting (WHO/UNICEF Joint Reporting Form), as published in the country profile (`cameroon_admin_jrf`) | - | pdf |
| Household survey coverage (54.0%) | WUENIC country profile 2023 revision | Cameroon household survey coverage (independent household sampling) (`cameroon_household_survey`) | - | pdf |
| WUENIC estimate (63.0%) | WUENIC 2025 revision | WHO/UNICEF Estimates of National Immunization Coverage (WUENIC), 2025 revision (`wuenic_2025`) | - | xlsx |
| Household survey coverage (56.0%) | WUENIC country profile 2023 revision | Cameroon household survey coverage (independent household sampling) (`cameroon_household_survey`) | - | pdf |
| WUENIC estimate (65.0%) | WUENIC 2025 revision | WHO/UNICEF Estimates of National Immunization Coverage (WUENIC), 2025 revision (`wuenic_2025`) | - | xlsx |
| Administrative coverage (82.0%) | WUENIC country profile 2023 revision | Cameroon administrative reporting (WHO/UNICEF Joint Reporting Form), as published in the country profile (`cameroon_admin_jrf`) | - | pdf |
| WUENIC estimate (71.0%) | WUENIC 2025 revision | WHO/UNICEF Estimates of National Immunization Coverage (WUENIC), 2025 revision (`wuenic_2025`) | - | xlsx |

## Relevant Prior Memories

No relevant prior memories were retrieved.

## Model-driven investigation

> The model proposes which evidence to gather and may challenge a claim. Its output is advisory: trusted Python code fetches the evidence, validates the numbers, and makes the decision.

- Model runtime: `not configured` at `n/a`
- Model calls made: 0 (budget 12)
- Model status: disabled
- Note: MODEL_NOT_REQUESTED

### Proposed evidence actions
- **Cameroon MCV1 (2018)**: FETCH_WUENIC_WORKBOOK (proposed by: deterministic) — A WUENIC/UNICEF source is still unverified, so the workbook extract is compared against the claimed value.
- **Cameroon MCV1 (2020)**: FETCH_WUENIC_WORKBOOK (proposed by: deterministic) — A WUENIC/UNICEF source is still unverified, so the workbook extract is compared against the claimed value.
- **Cameroon MCV1 (2021)**: FETCH_WUENIC_WORKBOOK (proposed by: deterministic) — A WUENIC/UNICEF source is still unverified, so the workbook extract is compared against the claimed value.
- **Cameroon MCV1 (2023)**: FETCH_WUENIC_WORKBOOK (proposed by: deterministic) — A WUENIC/UNICEF source is still unverified, so the workbook extract is compared against the claimed value.
- **Cameroon MCV1 (2018)**: FETCH_WUENIC_WORKBOOK (proposed by: deterministic) — A WUENIC/UNICEF source is still unverified, so the workbook extract is compared against the claimed value. [fallback: ACTION_NOT_AVAILABLE_FOR_THIS_FINDING]
- **Cameroon MCV1 (2020)**: FETCH_WUENIC_WORKBOOK (proposed by: deterministic) — A WUENIC/UNICEF source is still unverified, so the workbook extract is compared against the claimed value. [fallback: ACTION_NOT_AVAILABLE_FOR_THIS_FINDING]
- **Cameroon MCV1 (2021)**: FETCH_WUENIC_WORKBOOK (proposed by: deterministic) — A WUENIC/UNICEF source is still unverified, so the workbook extract is compared against the claimed value. [fallback: ACTION_NOT_AVAILABLE_FOR_THIS_FINDING]
- **Cameroon MCV1 (2023)**: FETCH_WUENIC_WORKBOOK (proposed by: deterministic) — A WUENIC/UNICEF source is still unverified, so the workbook extract is compared against the claimed value. [fallback: ACTION_NOT_AVAILABLE_FOR_THIS_FINDING]
- **Cameroon MCV1 (2018)**: FETCH_WUENIC_WORKBOOK (proposed by: deterministic) — A WUENIC/UNICEF source is still unverified, so the workbook extract is compared against the claimed value. [fallback: ACTION_NOT_AVAILABLE_FOR_THIS_FINDING]
- **Cameroon MCV1 (2020)**: FETCH_WUENIC_WORKBOOK (proposed by: deterministic) — A WUENIC/UNICEF source is still unverified, so the workbook extract is compared against the claimed value. [fallback: ACTION_NOT_AVAILABLE_FOR_THIS_FINDING]
- **Cameroon MCV1 (2021)**: FETCH_WUENIC_WORKBOOK (proposed by: deterministic) — A WUENIC/UNICEF source is still unverified, so the workbook extract is compared against the claimed value. [fallback: ACTION_NOT_AVAILABLE_FOR_THIS_FINDING]
- **Cameroon MCV1 (2023)**: FETCH_WUENIC_WORKBOOK (proposed by: deterministic) — A WUENIC/UNICEF source is still unverified, so the workbook extract is compared against the claimed value. [fallback: ACTION_NOT_AVAILABLE_FOR_THIS_FINDING]
- **Cameroon MCV1 (2018)**: FETCH_WUENIC_WORKBOOK (proposed by: deterministic) — A WUENIC/UNICEF source is still unverified, so the workbook extract is compared against the claimed value. [fallback: ACTION_NOT_AVAILABLE_FOR_THIS_FINDING]
- **Cameroon MCV1 (2020)**: FETCH_WUENIC_WORKBOOK (proposed by: deterministic) — A WUENIC/UNICEF source is still unverified, so the workbook extract is compared against the claimed value. [fallback: ACTION_NOT_AVAILABLE_FOR_THIS_FINDING]
- **Cameroon MCV1 (2021)**: FETCH_WUENIC_WORKBOOK (proposed by: deterministic) — A WUENIC/UNICEF source is still unverified, so the workbook extract is compared against the claimed value. [fallback: ACTION_NOT_AVAILABLE_FOR_THIS_FINDING]
- **Cameroon MCV1 (2023)**: FETCH_WUENIC_WORKBOOK (proposed by: deterministic) — A WUENIC/UNICEF source is still unverified, so the workbook extract is compared against the claimed value. [fallback: ACTION_NOT_AVAILABLE_FOR_THIS_FINDING]

### Model challenges
- **Cameroon MCV1 (2018)** (challenged by: deterministic):
  - The evidence record is internally consistent; the gap between the two measures is unexplained by the checks that were run.
  - Missing support: No independent document confirms either value.
  - Fallback reason: MODEL_NOT_REQUESTED
- **Cameroon MCV1 (2020)** (challenged by: deterministic):
  - The evidence record is internally consistent; the gap between the two measures is unexplained by the checks that were run.
  - Missing support: No independent document confirms either value.
  - Fallback reason: MODEL_NOT_REQUESTED
- **Cameroon MCV1 (2021)** (challenged by: deterministic):
  - The evidence record is internally consistent; the gap between the two measures is unexplained by the checks that were run.
  - Missing support: No independent document confirms either value.
  - Fallback reason: MODEL_NOT_REQUESTED
- **Cameroon MCV1 (2023)** (challenged by: deterministic):
  - The evidence record is internally consistent; the gap between the two measures is unexplained by the checks that were run.
  - Missing support: No independent document confirms either value.
  - Fallback reason: MODEL_NOT_REQUESTED

## Revision loop

> After the critic ran, the investigator requested extra evidence or stopped. This is a recorded decision, not a verdict about which coverage figure is correct.

- **Cameroon MCV1 (2018)**: action=FETCH_WUENIC; outcome=REVISED_SOURCE_CHECK; stop reason=EXTRACT_VALUE_MATCHED
- **Cameroon MCV1 (2020)**: action=FETCH_WUENIC; outcome=REVISED_SOURCE_CHECK; stop reason=EXTRACT_VALUE_MATCHED
- **Cameroon MCV1 (2021)**: action=FETCH_WUENIC; outcome=REVISED_SOURCE_CHECK; stop reason=EXTRACT_VALUE_MATCHED
- **Cameroon MCV1 (2023)**: action=FETCH_WUENIC; outcome=REVISED_SOURCE_CHECK; stop reason=EXTRACT_VALUE_MATCHED
- **Cameroon MCV1 (2018)**: action=FETCH_SOURCE_DOCUMENT; outcome=EVIDENCE_RETRIEVED; stop reason=SOURCE_DOCUMENT_RETRIEVED
- **Cameroon MCV1 (2020)**: action=FETCH_SOURCE_DOCUMENT; outcome=EVIDENCE_RETRIEVED; stop reason=SOURCE_DOCUMENT_RETRIEVED
- **Cameroon MCV1 (2021)**: action=FETCH_SOURCE_DOCUMENT; outcome=EVIDENCE_RETRIEVED; stop reason=SOURCE_DOCUMENT_RETRIEVED
- **Cameroon MCV1 (2023)**: action=FETCH_SOURCE_DOCUMENT; outcome=EVIDENCE_RETRIEVED; stop reason=SOURCE_DOCUMENT_RETRIEVED
- **Cameroon MCV1 (2018)**: action=QUERY_ZETARIS; outcome=EVIDENCE_RETRIEVED; stop reason=ZETARIS_VALUE_MATCHED
- **Cameroon MCV1 (2020)**: action=QUERY_ZETARIS; outcome=EVIDENCE_RETRIEVED; stop reason=ZETARIS_VALUE_MATCHED
- **Cameroon MCV1 (2021)**: action=QUERY_ZETARIS; outcome=EVIDENCE_RETRIEVED; stop reason=ZETARIS_VALUE_MATCHED
- **Cameroon MCV1 (2023)**: action=QUERY_ZETARIS; outcome=EVIDENCE_RETRIEVED; stop reason=ZETARIS_VALUE_MATCHED

## Investigation trace

> One iteration is one pass of the loop: the coordinator planned the next step, the trusted code executed it, the critic challenged the result and the arbiter adjudicated it.

### Iteration 1

- Active findings: Cameroon MCV1 (2018), Cameroon MCV1 (2020), Cameroon MCV1 (2021), Cameroon MCV1 (2023)
- Proposed for Cameroon MCV1 (2018): FETCH_WUENIC_WORKBOOK (proposed by: deterministic)
- Proposed for Cameroon MCV1 (2020): FETCH_WUENIC_WORKBOOK (proposed by: deterministic)
- Proposed for Cameroon MCV1 (2021): FETCH_WUENIC_WORKBOOK (proposed by: deterministic)
- Proposed for Cameroon MCV1 (2023): FETCH_WUENIC_WORKBOOK (proposed by: deterministic)
- Next step for Cameroon MCV1 (2018): FETCH_WUENIC_WORKBOOK (chosen by: deterministic) — A WUENIC/UNICEF source is still unverified.
- Next step for Cameroon MCV1 (2020): FETCH_WUENIC_WORKBOOK (chosen by: deterministic) — A WUENIC/UNICEF source is still unverified.
- Next step for Cameroon MCV1 (2021): FETCH_WUENIC_WORKBOOK (chosen by: deterministic) — A WUENIC/UNICEF source is still unverified.
- Next step for Cameroon MCV1 (2023): FETCH_WUENIC_WORKBOOK (chosen by: deterministic) — A WUENIC/UNICEF source is still unverified.
- Executed: FETCH_WUENIC_WORKBOOK for Cameroon MCV1 (2018) — outcome=REVISED_SOURCE_CHECK, stop reason=EXTRACT_VALUE_MATCHED
- Executed: FETCH_WUENIC_WORKBOOK for Cameroon MCV1 (2020) — outcome=REVISED_SOURCE_CHECK, stop reason=EXTRACT_VALUE_MATCHED
- Executed: FETCH_WUENIC_WORKBOOK for Cameroon MCV1 (2021) — outcome=REVISED_SOURCE_CHECK, stop reason=EXTRACT_VALUE_MATCHED
- Executed: FETCH_WUENIC_WORKBOOK for Cameroon MCV1 (2023) — outcome=REVISED_SOURCE_CHECK, stop reason=EXTRACT_VALUE_MATCHED
- Challenge for Cameroon MCV1 (2018) (raised by: deterministic): The evidence record is internally consistent; the gap between the two measures is unexplained by the checks that were run.
- Challenge for Cameroon MCV1 (2020) (raised by: deterministic): The evidence record is internally consistent; the gap between the two measures is unexplained by the checks that were run.
- Challenge for Cameroon MCV1 (2021) (raised by: deterministic): The evidence record is internally consistent; the gap between the two measures is unexplained by the checks that were run.
- Challenge for Cameroon MCV1 (2023) (raised by: deterministic): The evidence record is internally consistent; the gap between the two measures is unexplained by the checks that were run.
- Adjudication for Cameroon MCV1 (2018): REVIEW → REVIEW (proposed none; rejected: MODEL_NOT_REQUESTED)
- Adjudication for Cameroon MCV1 (2020): REVIEW → REVIEW (proposed none; rejected: MODEL_NOT_REQUESTED)
- Adjudication for Cameroon MCV1 (2021): REVIEW → REVIEW (proposed none; rejected: MODEL_NOT_REQUESTED)
- Adjudication for Cameroon MCV1 (2023): REVIEW → REVIEW (proposed none; rejected: MODEL_NOT_REQUESTED)

### Iteration 2

- Active findings: Cameroon MCV1 (2018), Cameroon MCV1 (2020), Cameroon MCV1 (2021), Cameroon MCV1 (2023)
- Proposed for Cameroon MCV1 (2018): FETCH_WUENIC_WORKBOOK (proposed by: deterministic, ACTION_NOT_AVAILABLE_FOR_THIS_FINDING)
- Proposed for Cameroon MCV1 (2020): FETCH_WUENIC_WORKBOOK (proposed by: deterministic, ACTION_NOT_AVAILABLE_FOR_THIS_FINDING)
- Proposed for Cameroon MCV1 (2021): FETCH_WUENIC_WORKBOOK (proposed by: deterministic, ACTION_NOT_AVAILABLE_FOR_THIS_FINDING)
- Proposed for Cameroon MCV1 (2023): FETCH_WUENIC_WORKBOOK (proposed by: deterministic, ACTION_NOT_AVAILABLE_FOR_THIS_FINDING)
- Next step for Cameroon MCV1 (2018): FETCH_SOURCE_DOCUMENT (chosen by: deterministic) — A source document for this finding has not been retrieved yet.
- Next step for Cameroon MCV1 (2020): FETCH_SOURCE_DOCUMENT (chosen by: deterministic) — A source document for this finding has not been retrieved yet.
- Next step for Cameroon MCV1 (2021): FETCH_SOURCE_DOCUMENT (chosen by: deterministic) — A source document for this finding has not been retrieved yet.
- Next step for Cameroon MCV1 (2023): FETCH_SOURCE_DOCUMENT (chosen by: deterministic) — A source document for this finding has not been retrieved yet.
- Executed: FETCH_SOURCE_DOCUMENT for Cameroon MCV1 (2018) — outcome=EVIDENCE_RETRIEVED, stop reason=SOURCE_DOCUMENT_RETRIEVED
- Executed: FETCH_SOURCE_DOCUMENT for Cameroon MCV1 (2020) — outcome=EVIDENCE_RETRIEVED, stop reason=SOURCE_DOCUMENT_RETRIEVED
- Executed: FETCH_SOURCE_DOCUMENT for Cameroon MCV1 (2021) — outcome=EVIDENCE_RETRIEVED, stop reason=SOURCE_DOCUMENT_RETRIEVED
- Executed: FETCH_SOURCE_DOCUMENT for Cameroon MCV1 (2023) — outcome=EVIDENCE_RETRIEVED, stop reason=SOURCE_DOCUMENT_RETRIEVED
- Rejected proposal: the model asked for FETCH_WUENIC_WORKBOOK for Cameroon MCV1 (2023) — ACTION_NOT_AVAILABLE_FOR_THIS_FINDING
- Rejected proposal: the model asked for FETCH_WUENIC_WORKBOOK for Cameroon MCV1 (2023) — ACTION_NOT_AVAILABLE_FOR_THIS_FINDING
- Rejected proposal: the model asked for FETCH_WUENIC_WORKBOOK for Cameroon MCV1 (2023) — ACTION_NOT_AVAILABLE_FOR_THIS_FINDING
- Rejected proposal: the model asked for FETCH_WUENIC_WORKBOOK for Cameroon MCV1 (2023) — ACTION_NOT_AVAILABLE_FOR_THIS_FINDING
- Challenge for Cameroon MCV1 (2018) (raised by: deterministic): The evidence record is internally consistent; the gap between the two measures is unexplained by the checks that were run.
- Challenge for Cameroon MCV1 (2020) (raised by: deterministic): The evidence record is internally consistent; the gap between the two measures is unexplained by the checks that were run.
- Challenge for Cameroon MCV1 (2021) (raised by: deterministic): The evidence record is internally consistent; the gap between the two measures is unexplained by the checks that were run.
- Challenge for Cameroon MCV1 (2023) (raised by: deterministic): The evidence record is internally consistent; the gap between the two measures is unexplained by the checks that were run.
- Adjudication for Cameroon MCV1 (2018): REVIEW → REVIEW (proposed none; rejected: MODEL_NOT_REQUESTED)
- Adjudication for Cameroon MCV1 (2020): REVIEW → REVIEW (proposed none; rejected: MODEL_NOT_REQUESTED)
- Adjudication for Cameroon MCV1 (2021): REVIEW → REVIEW (proposed none; rejected: MODEL_NOT_REQUESTED)
- Adjudication for Cameroon MCV1 (2023): REVIEW → REVIEW (proposed none; rejected: MODEL_NOT_REQUESTED)

### Iteration 3

- Active findings: Cameroon MCV1 (2018), Cameroon MCV1 (2020), Cameroon MCV1 (2021), Cameroon MCV1 (2023)
- Proposed for Cameroon MCV1 (2018): FETCH_WUENIC_WORKBOOK (proposed by: deterministic, ACTION_NOT_AVAILABLE_FOR_THIS_FINDING)
- Proposed for Cameroon MCV1 (2020): FETCH_WUENIC_WORKBOOK (proposed by: deterministic, ACTION_NOT_AVAILABLE_FOR_THIS_FINDING)
- Proposed for Cameroon MCV1 (2021): FETCH_WUENIC_WORKBOOK (proposed by: deterministic, ACTION_NOT_AVAILABLE_FOR_THIS_FINDING)
- Proposed for Cameroon MCV1 (2023): FETCH_WUENIC_WORKBOOK (proposed by: deterministic, ACTION_NOT_AVAILABLE_FOR_THIS_FINDING)
- Next step for Cameroon MCV1 (2018): QUERY_ZETARIS (chosen by: deterministic) — A published value is not corroborated yet.
- Next step for Cameroon MCV1 (2020): QUERY_ZETARIS (chosen by: deterministic) — A published value is not corroborated yet.
- Next step for Cameroon MCV1 (2021): QUERY_ZETARIS (chosen by: deterministic) — A published value is not corroborated yet.
- Next step for Cameroon MCV1 (2023): QUERY_ZETARIS (chosen by: deterministic) — A published value is not corroborated yet.
- Executed: QUERY_ZETARIS for Cameroon MCV1 (2018) — outcome=EVIDENCE_RETRIEVED, stop reason=ZETARIS_VALUE_MATCHED
- Executed: QUERY_ZETARIS for Cameroon MCV1 (2020) — outcome=EVIDENCE_RETRIEVED, stop reason=ZETARIS_VALUE_MATCHED
- Executed: QUERY_ZETARIS for Cameroon MCV1 (2021) — outcome=EVIDENCE_RETRIEVED, stop reason=ZETARIS_VALUE_MATCHED
- Executed: QUERY_ZETARIS for Cameroon MCV1 (2023) — outcome=EVIDENCE_RETRIEVED, stop reason=ZETARIS_VALUE_MATCHED
- Rejected proposal: the model asked for FETCH_WUENIC_WORKBOOK for Cameroon MCV1 (2023) — ACTION_NOT_AVAILABLE_FOR_THIS_FINDING
- Rejected proposal: the model asked for FETCH_WUENIC_WORKBOOK for Cameroon MCV1 (2023) — ACTION_NOT_AVAILABLE_FOR_THIS_FINDING
- Rejected proposal: the model asked for FETCH_WUENIC_WORKBOOK for Cameroon MCV1 (2023) — ACTION_NOT_AVAILABLE_FOR_THIS_FINDING
- Rejected proposal: the model asked for FETCH_WUENIC_WORKBOOK for Cameroon MCV1 (2023) — ACTION_NOT_AVAILABLE_FOR_THIS_FINDING
- Challenge for Cameroon MCV1 (2018) (raised by: deterministic) (carried forward: the decision did not change): The evidence record is internally consistent; the gap between the two measures is unexplained by the checks that were run.
- Challenge for Cameroon MCV1 (2020) (raised by: deterministic) (carried forward: the decision did not change): The evidence record is internally consistent; the gap between the two measures is unexplained by the checks that were run.
- Challenge for Cameroon MCV1 (2021) (raised by: deterministic) (carried forward: the decision did not change): The evidence record is internally consistent; the gap between the two measures is unexplained by the checks that were run.
- Challenge for Cameroon MCV1 (2023) (raised by: deterministic) (carried forward: the decision did not change): The evidence record is internally consistent; the gap between the two measures is unexplained by the checks that were run.
- Adjudication for Cameroon MCV1 (2018): REVIEW → REVIEW (proposed none; rejected: MODEL_NOT_REQUESTED)
- Adjudication for Cameroon MCV1 (2020): REVIEW → REVIEW (proposed none; rejected: MODEL_NOT_REQUESTED)
- Adjudication for Cameroon MCV1 (2021): REVIEW → REVIEW (proposed none; rejected: MODEL_NOT_REQUESTED)
- Adjudication for Cameroon MCV1 (2023): REVIEW → REVIEW (proposed none; rejected: MODEL_NOT_REQUESTED)

### Iteration 4

- Active findings: Cameroon MCV1 (2018), Cameroon MCV1 (2020), Cameroon MCV1 (2021), Cameroon MCV1 (2023)
- Proposed for Cameroon MCV1 (2018): FETCH_WUENIC_WORKBOOK (proposed by: deterministic, ACTION_NOT_AVAILABLE_FOR_THIS_FINDING)
- Proposed for Cameroon MCV1 (2020): FETCH_WUENIC_WORKBOOK (proposed by: deterministic, ACTION_NOT_AVAILABLE_FOR_THIS_FINDING)
- Proposed for Cameroon MCV1 (2021): FETCH_WUENIC_WORKBOOK (proposed by: deterministic, ACTION_NOT_AVAILABLE_FOR_THIS_FINDING)
- Proposed for Cameroon MCV1 (2023): FETCH_WUENIC_WORKBOOK (proposed by: deterministic, ACTION_NOT_AVAILABLE_FOR_THIS_FINDING)
- Next step for Cameroon MCV1 (2018): STOP (chosen by: deterministic) — No permitted action remains for this finding.
- Next step for Cameroon MCV1 (2020): STOP (chosen by: deterministic) — No permitted action remains for this finding.
- Next step for Cameroon MCV1 (2021): STOP (chosen by: deterministic) — No permitted action remains for this finding.
- Next step for Cameroon MCV1 (2023): STOP (chosen by: deterministic) — No permitted action remains for this finding.
- Rejected proposal: the model asked for FETCH_WUENIC_WORKBOOK for Cameroon MCV1 (2023) — ACTION_NOT_AVAILABLE_FOR_THIS_FINDING
- Rejected proposal: the model asked for FETCH_WUENIC_WORKBOOK for Cameroon MCV1 (2023) — ACTION_NOT_AVAILABLE_FOR_THIS_FINDING
- Rejected proposal: the model asked for FETCH_WUENIC_WORKBOOK for Cameroon MCV1 (2023) — ACTION_NOT_AVAILABLE_FOR_THIS_FINDING
- Rejected proposal: the model asked for FETCH_WUENIC_WORKBOOK for Cameroon MCV1 (2023) — ACTION_NOT_AVAILABLE_FOR_THIS_FINDING
- Iteration stop reason: REPEATED_STATE

## Evidence ledger

> Every row is an item the trusted code registered. The id is what a model proposal is checked against, so a citation that names an item that was never gathered is rejected.

- **ev-1**: Cameroon DHS 2018 survey report — status=SOURCE_DOCUMENT_RETRIEVED, scope=DOCUMENT_PRESENCE
  - https://dhsprogram.com/pubs/pdf/SR266/SR266.pdf
- **ev-2**: WUENIC country profile 2023 revision — status=SOURCE_DOCUMENT_RETRIEVED, scope=DOCUMENT_PRESENCE
  - https://cdn.who.int/media/docs/default-source/country-profiles/immunization/2024-country-profiles/immunization-2024-cmr.pdf?download=true&sfvrsn=fb0d6c18_3
- **ev-3**: WUENIC country profile 2023 revision — status=NOT_VERIFIED, scope=CONTEXT_ONLY
  - https://data.unicef.org/resources/dataset/immunization/
- **ev-4**: CONFLICT_ADMIN_SURVEY Cameroon MCV1 2018: Administrative coverage 71.0 vs Household survey coverage 65.3 — status=CONFLICT_DETECTED, scope=INDEPENDENT_MEASUREMENT
- **ev-5**: CONFLICT_ADMIN_SURVEY Cameroon MCV1 2020: Administrative coverage 74.0 vs Household survey coverage 54.0 — status=CONFLICT_DETECTED, scope=INDEPENDENT_MEASUREMENT
- **ev-6**: CONFLICT_ADMIN_SURVEY Cameroon MCV1 2021: Administrative coverage 74.0 vs Household survey coverage 56.0 — status=CONFLICT_DETECTED, scope=INDEPENDENT_MEASUREMENT
- **ev-7**: Evidence store row for Cameroon MCV1 2018 — status=EXTRACT_CONSISTENT, scope=SELF_CONSISTENCY
  - https://dhsprogram.com/pubs/pdf/SR266/SR266.pdf
- **ev-8**: Evidence store row for Cameroon MCV1 2020 — status=EXTRACT_CONSISTENT, scope=SELF_CONSISTENCY
  - https://cdn.who.int/media/docs/default-source/country-profiles/immunization/2024-country-profiles/immunization-2024-cmr.pdf?download=true&sfvrsn=fb0d6c18_3
- **ev-9**: Evidence store row for Cameroon MCV1 2021 — status=EXTRACT_CONSISTENT, scope=SELF_CONSISTENCY
  - https://cdn.who.int/media/docs/default-source/country-profiles/immunization/2024-country-profiles/immunization-2024-cmr.pdf?download=true&sfvrsn=fb0d6c18_3
- **ev-10**: Evidence store row for Cameroon MCV1 2023 — status=EXTRACT_CONSISTENT, scope=SELF_CONSISTENCY
  - https://cdn.who.int/media/docs/default-source/country-profiles/immunization/2024-country-profiles/immunization-2024-cmr.pdf?download=true&sfvrsn=fb0d6c18_3

## Stopping reason

- Investigation stopped: **REPEATED_STATE**
- 4 finding(s) are still open: Cameroon MCV1 (2018), Cameroon MCV1 (2020), Cameroon MCV1 (2021), Cameroon MCV1 (2023). The investigation reached the same state twice, so it was stopped instead of looping.
- Findings still open: Cameroon MCV1 (2018), Cameroon MCV1 (2020), Cameroon MCV1 (2021), Cameroon MCV1 (2023)
  - Cameroon MCV1 (2018): NO_ACTION — No permitted action remains for this finding.
  - Cameroon MCV1 (2020): NO_ACTION — No permitted action remains for this finding.
  - Cameroon MCV1 (2021): NO_ACTION — No permitted action remains for this finding.
  - Cameroon MCV1 (2023): NO_ACTION — No permitted action remains for this finding.

## Finding 1: Cameroon MCV1 (2018)

- **Observation A:** WUENIC estimate — 61.0%
- **Observation B:** Administrative coverage — 71.0%
- **Absolute gap:** 10.0 percentage points
- **Deterministic decision:** REVIEW
- **Final disposition:** REVIEW
- **Reason:** The observed gap meets the review threshold; investigate definitions, denominators, reporting quality, and estimation methods.


### Other reported numbers for this country and year

> These are not a third publication of the same series. Each one comes from a different kind of measurement, so it says something the two published figures cannot.

- **Household survey coverage**: 65.3% (Cameroon household survey coverage (independent household sampling))
  - Note: Measles (MCV1) among children 12-23 months; published in the Cameroon DHS 2018 summary report (SR266); cross-checked against the Countdown to 2030 Cameroon DHS 2018 country sheet


### Conflicts between lines that do not share an upstream

- **CONFLICT_ADMIN_SURVEY**: Administrative coverage 71.0% against Household survey coverage 65.3% — 5.700000000000003 percentage points
  - The administrative figure is 5.7 percentage points above an independent household-survey measurement for the same year. The administrative number is not usable as the coverage level; the survey is the better estimate of the level, with the usual caveats about survey design.


### Recommendation for the coverage level

- **Use for the coverage level:** Household survey coverage — 65.3%
- **Do not use as the coverage level:** Administrative coverage — 71.0%
- **Difference:** 5.700000000000003 percentage points
- **Why:** The administrative figure is 5.7 percentage points above an independent household-survey measurement for the same year. The administrative number is not usable as the coverage level; the survey is the better estimate of the level, with the usual caveats about survey design.
- Caveat: The survey figure is independent of the administrative reporting, but it was read from a publication that also carries the administrative line, so it was not re-read from the survey's own report.
- Caveat: A survey measures a sample of households, not the whole population, so it carries its own sampling uncertainty.
- Caveat: This is a recommendation for the coverage level, not a claim that one of the published figures is correct.

### Sources

- [Cameroon DHS 2018 survey report](https://dhsprogram.com/pubs/pdf/SR266/SR266.pdf)
  - Verification status: SOURCE_DOCUMENT_RETRIEVED (the document was retrieved so it can be inspected; its contents and values are not verified)
  - Retrieved document: application/pdf, 2036701 bytes
  - Limitation: Retrieving a source document shows that it exists; it does not verify the values inside it.
- [WUENIC country profile 2023 revision](https://cdn.who.int/media/docs/default-source/country-profiles/immunization/2024-country-profiles/immunization-2024-cmr.pdf?download=true&sfvrsn=fb0d6c18_3)
  - Verification status: EXTRACT_CONSISTENT (self-consistency check against the local WUENIC workbook extract, which is where the claimed value came from; this is not independent verification)
  - Matching table page: 20
  - WUENIC estimate: claim=61.0%, table=61.0%, matched=yes
  - Limitation: Text matching does not validate the underlying data.
  - Limitation: PDF extraction can fail or reorder table values.
  - Limitation: A match does not establish which measure is more accurate.
  - Limitation: Workbook matching compares the claim with a local WUENIC extract; it does not prove the estimate is correct or more accurate than administrative coverage.
- [WUENIC country profile 2023 revision](https://data.unicef.org/resources/dataset/immunization/)
  - Verification status: EXTRACT_CONSISTENT (self-consistency check against the local WUENIC workbook extract, which is where the claimed value came from; this is not independent verification)
  - Matching table page: 20
  - WUENIC estimate: claim=61.0%, table=61.0%, matched=yes
  - Limitation: Text matching does not validate the underlying data.
  - Limitation: PDF extraction can fail or reorder table values.
  - Limitation: A match does not establish which measure is more accurate.
  - Limitation: Workbook matching compares the claim with a local WUENIC extract; it does not prove the estimate is correct or more accurate than administrative coverage.

### Adjudication
- **Baseline disposition:** REVIEW
- **Final disposition:** REVIEW
- **Proposed verdict:** none
- **Proposal rejected:** MODEL_NOT_REQUESTED
- **What this means:** The discrepancy stands but is not resolved; a human has to look at the definitions, denominators, reporting quality and estimation methods.

### Unresolved uncertainty

These are the questions the evidence still leaves open, so the finding is not resolved:

- The document behind 'Cameroon DHS 2018 survey report' was retrieved but its values were not checked.
- 'WUENIC country profile 2023 revision' was only compared with the extract the claim came from (self-consistency, not independent verification).
- 'WUENIC country profile 2023 revision' was never verified against its own published source.
- Missing support: No independent document confirms either value.


### Limitations and next steps
- Verify the original source documents and definitions of each measure.
- Check denominators, reporting periods, and estimation methodology.
- A source link does not independently verify its contents.
- Do not treat a remembered claim as confirmation of a current finding.

## Finding 2: Cameroon MCV1 (2020)

- **Observation A:** WUENIC estimate — 63.0%
- **Observation B:** Administrative coverage — 74.0%
- **Absolute gap:** 11.0 percentage points
- **Deterministic decision:** REVIEW
- **Final disposition:** REVIEW
- **Reason:** The observed gap meets the review threshold; investigate definitions, denominators, reporting quality, and estimation methods.


### Other reported numbers for this country and year

> These are not a third publication of the same series. Each one comes from a different kind of measurement, so it says something the two published figures cannot.

- **Household survey coverage**: 54.0% (Cameroon household survey coverage (independent household sampling))
  - Note: Household survey row published in the country profile


### Conflicts between lines that do not share an upstream

- **CONFLICT_ADMIN_SURVEY**: Administrative coverage 74.0% against Household survey coverage 54.0% — 20.0 percentage points
  - The administrative figure is 20.0 percentage points above an independent household-survey measurement for the same year. The administrative number is not usable as the coverage level; the survey is the better estimate of the level, with the usual caveats about survey design.


### Recommendation for the coverage level

- **Use for the coverage level:** Household survey coverage — 54.0%
- **Do not use as the coverage level:** Administrative coverage — 74.0%
- **Difference:** 20.0 percentage points
- **Why:** The administrative figure is 20.0 percentage points above an independent household-survey measurement for the same year. The administrative number is not usable as the coverage level; the survey is the better estimate of the level, with the usual caveats about survey design.
- Caveat: The survey figure is independent of the administrative reporting, but it was read from a publication that also carries the administrative line, so it was not re-read from the survey's own report.
- Caveat: A survey measures a sample of households, not the whole population, so it carries its own sampling uncertainty.
- Caveat: This is a recommendation for the coverage level, not a claim that one of the published figures is correct.

### Sources

- [WUENIC country profile 2023 revision](https://cdn.who.int/media/docs/default-source/country-profiles/immunization/2024-country-profiles/immunization-2024-cmr.pdf?download=true&sfvrsn=fb0d6c18_3)
  - Verification status: SOURCE_DOCUMENT_RETRIEVED (the document was retrieved so it can be inspected; its contents and values are not verified)
  - Matching table page: 20
  - WUENIC estimate: claim=63.0%, table=63.0%, matched=yes
  - Retrieved document: application/pdf, 444677 bytes
  - Limitation: Text matching does not validate the underlying data.
  - Limitation: PDF extraction can fail or reorder table values.
  - Limitation: A match does not establish which measure is more accurate.
  - Limitation: Workbook matching compares the claim with a local WUENIC extract; it does not prove the estimate is correct or more accurate than administrative coverage.
  - Limitation: Retrieving a source document shows that it exists; it does not verify the values inside it.
- [WUENIC country profile 2023 revision](https://data.unicef.org/resources/dataset/immunization/)
  - Verification status: SOURCE_DOCUMENT_RETRIEVED (the document was retrieved so it can be inspected; its contents and values are not verified)
  - Matching table page: 20
  - WUENIC estimate: claim=63.0%, table=63.0%, matched=yes
  - Retrieved document: application/pdf, 444677 bytes
  - Limitation: Text matching does not validate the underlying data.
  - Limitation: PDF extraction can fail or reorder table values.
  - Limitation: A match does not establish which measure is more accurate.
  - Limitation: Workbook matching compares the claim with a local WUENIC extract; it does not prove the estimate is correct or more accurate than administrative coverage.
  - Limitation: Retrieving a source document shows that it exists; it does not verify the values inside it.

### Adjudication
- **Baseline disposition:** REVIEW
- **Final disposition:** REVIEW
- **Proposed verdict:** none
- **Proposal rejected:** MODEL_NOT_REQUESTED
- **What this means:** The discrepancy stands but is not resolved; a human has to look at the definitions, denominators, reporting quality and estimation methods.

### Unresolved uncertainty

These are the questions the evidence still leaves open, so the finding is not resolved:

- The document behind 'WUENIC country profile 2023 revision' was retrieved but its values were not checked.
- 'WUENIC country profile 2023 revision' was never verified against its own published source.
- Missing support: No independent document confirms either value.


### Limitations and next steps
- Verify the original source documents and definitions of each measure.
- Check denominators, reporting periods, and estimation methodology.
- A source link does not independently verify its contents.
- Do not treat a remembered claim as confirmation of a current finding.

## Finding 3: Cameroon MCV1 (2021)

- **Observation A:** WUENIC estimate — 65.0%
- **Observation B:** Administrative coverage — 74.0%
- **Absolute gap:** 9.0 percentage points
- **Deterministic decision:** REVIEW
- **Final disposition:** REVIEW
- **Reason:** The observed gap meets the review threshold; investigate definitions, denominators, reporting quality, and estimation methods.


### Other reported numbers for this country and year

> These are not a third publication of the same series. Each one comes from a different kind of measurement, so it says something the two published figures cannot.

- **Household survey coverage**: 56.0% (Cameroon household survey coverage (independent household sampling))
  - Note: Household survey row published in the country profile


### Conflicts between lines that do not share an upstream

- **CONFLICT_ADMIN_SURVEY**: Administrative coverage 74.0% against Household survey coverage 56.0% — 18.0 percentage points
  - The administrative figure is 18.0 percentage points above an independent household-survey measurement for the same year. The administrative number is not usable as the coverage level; the survey is the better estimate of the level, with the usual caveats about survey design.


### Recommendation for the coverage level

- **Use for the coverage level:** Household survey coverage — 56.0%
- **Do not use as the coverage level:** Administrative coverage — 74.0%
- **Difference:** 18.0 percentage points
- **Why:** The administrative figure is 18.0 percentage points above an independent household-survey measurement for the same year. The administrative number is not usable as the coverage level; the survey is the better estimate of the level, with the usual caveats about survey design.
- Caveat: The survey figure is independent of the administrative reporting, but it was read from a publication that also carries the administrative line, so it was not re-read from the survey's own report.
- Caveat: A survey measures a sample of households, not the whole population, so it carries its own sampling uncertainty.
- Caveat: This is a recommendation for the coverage level, not a claim that one of the published figures is correct.

### Sources

- [WUENIC country profile 2023 revision](https://cdn.who.int/media/docs/default-source/country-profiles/immunization/2024-country-profiles/immunization-2024-cmr.pdf?download=true&sfvrsn=fb0d6c18_3)
  - Verification status: SOURCE_DOCUMENT_RETRIEVED (the document was retrieved so it can be inspected; its contents and values are not verified)
  - Matching table page: 20
  - WUENIC estimate: claim=65.0%, table=65.0%, matched=yes
  - Retrieved document: application/pdf, 444677 bytes
  - Limitation: Text matching does not validate the underlying data.
  - Limitation: PDF extraction can fail or reorder table values.
  - Limitation: A match does not establish which measure is more accurate.
  - Limitation: Workbook matching compares the claim with a local WUENIC extract; it does not prove the estimate is correct or more accurate than administrative coverage.
  - Limitation: Retrieving a source document shows that it exists; it does not verify the values inside it.
- [WUENIC country profile 2023 revision](https://data.unicef.org/resources/dataset/immunization/)
  - Verification status: SOURCE_DOCUMENT_RETRIEVED (the document was retrieved so it can be inspected; its contents and values are not verified)
  - Matching table page: 20
  - WUENIC estimate: claim=65.0%, table=65.0%, matched=yes
  - Retrieved document: application/pdf, 444677 bytes
  - Limitation: Text matching does not validate the underlying data.
  - Limitation: PDF extraction can fail or reorder table values.
  - Limitation: A match does not establish which measure is more accurate.
  - Limitation: Workbook matching compares the claim with a local WUENIC extract; it does not prove the estimate is correct or more accurate than administrative coverage.
  - Limitation: Retrieving a source document shows that it exists; it does not verify the values inside it.

### Adjudication
- **Baseline disposition:** REVIEW
- **Final disposition:** REVIEW
- **Proposed verdict:** none
- **Proposal rejected:** MODEL_NOT_REQUESTED
- **What this means:** The discrepancy stands but is not resolved; a human has to look at the definitions, denominators, reporting quality and estimation methods.

### Unresolved uncertainty

These are the questions the evidence still leaves open, so the finding is not resolved:

- The document behind 'WUENIC country profile 2023 revision' was retrieved but its values were not checked.
- 'WUENIC country profile 2023 revision' was never verified against its own published source.
- Missing support: No independent document confirms either value.


### Limitations and next steps
- Verify the original source documents and definitions of each measure.
- Check denominators, reporting periods, and estimation methodology.
- A source link does not independently verify its contents.
- Do not treat a remembered claim as confirmation of a current finding.

## Finding 4: Cameroon MCV1 (2023)

- **Observation A:** WUENIC estimate — 71.0%
- **Observation B:** Administrative coverage — 82.0%
- **Absolute gap:** 11.0 percentage points
- **Deterministic decision:** REVIEW
- **Final disposition:** REVIEW
- **Reason:** The observed gap meets the review threshold; investigate definitions, denominators, reporting quality, and estimation methods.

### Sources

- [WUENIC country profile 2023 revision](https://cdn.who.int/media/docs/default-source/country-profiles/immunization/2024-country-profiles/immunization-2024-cmr.pdf?download=true&sfvrsn=fb0d6c18_3)
  - Verification status: SOURCE_DOCUMENT_RETRIEVED (the document was retrieved so it can be inspected; its contents and values are not verified)
  - Matching table page: 20
  - WUENIC estimate: claim=71.0%, table=71.0%, matched=yes
  - Retrieved document: application/pdf, 444677 bytes
  - Limitation: Text matching does not validate the underlying data.
  - Limitation: PDF extraction can fail or reorder table values.
  - Limitation: A match does not establish which measure is more accurate.
  - Limitation: Workbook matching compares the claim with a local WUENIC extract; it does not prove the estimate is correct or more accurate than administrative coverage.
  - Limitation: Retrieving a source document shows that it exists; it does not verify the values inside it.
- [WUENIC country profile 2023 revision](https://data.unicef.org/resources/dataset/immunization/)
  - Verification status: SOURCE_DOCUMENT_RETRIEVED (the document was retrieved so it can be inspected; its contents and values are not verified)
  - Matching table page: 20
  - WUENIC estimate: claim=71.0%, table=71.0%, matched=yes
  - Retrieved document: application/pdf, 444677 bytes
  - Limitation: Text matching does not validate the underlying data.
  - Limitation: PDF extraction can fail or reorder table values.
  - Limitation: A match does not establish which measure is more accurate.
  - Limitation: Workbook matching compares the claim with a local WUENIC extract; it does not prove the estimate is correct or more accurate than administrative coverage.
  - Limitation: Retrieving a source document shows that it exists; it does not verify the values inside it.

### Adjudication
- **Baseline disposition:** REVIEW
- **Final disposition:** REVIEW
- **Proposed verdict:** none
- **Proposal rejected:** MODEL_NOT_REQUESTED
- **What this means:** The discrepancy stands but is not resolved; a human has to look at the definitions, denominators, reporting quality and estimation methods.

### Unresolved uncertainty

These are the questions the evidence still leaves open, so the finding is not resolved:

- The document behind 'WUENIC country profile 2023 revision' was retrieved but its values were not checked.
- 'WUENIC country profile 2023 revision' was never verified against its own published source.
- Missing support: No independent document confirms either value.


### Limitations and next steps
- Verify the original source documents and definitions of each measure.
- Check denominators, reporting periods, and estimation methodology.
- A source link does not independently verify its contents.
- Do not treat a remembered claim as confirmation of a current finding.
