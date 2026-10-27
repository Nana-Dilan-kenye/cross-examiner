# The slide deck

Eight required points (`submission-requirements.md` §3.2). One slide
each, plus a title and a closing slide. The deck explains what the demo
cannot, and it must not claim anything the code does not do
(`submission-form-preview.md` §3.6).

Every figure below is one the code produced. The commands are there so
the number can be re-checked while the deck is being prepared.

---

## Title

**Cross-Examiner**
*Which coverage figure should we plan against?*

Track 1 - Solving Fragmented Intelligence · Open Agent Hackathon 2026 · Radixmente

> Visual: the three Cameroon MCV1 2020 numbers, 74 / 63 / 54, with the
> series each one comes from.

---

## Slide 1 - The problem and the target user

**The user:** a public-health programme planner in a health ministry, an
NGO or a donor agency. They have to choose one immunization-coverage
figure for one country and year, to target outreach and allocate
resources with.

**The problem:** several systems publish coverage for the same country
and year and they routinely disagree.

| Cameroon, MCV1, 2020 | |
|---|---|
| WUENIC estimate | 63% |
| Administrative coverage | 74% |
| Household survey | 54% |

Nobody says which one to believe. The differences are not noise: they
come from different measurement processes, and the administrative line
rests on population denominators that can be wrong.

> Source: `data/sources.json`, the registry.

---

## Slide 2 - The solution

An agent that reads every published figure through one semantic layer
that carries its lineage, tells a derived republication apart from an
independent measurement, cross-examines the administrative figure against
the household survey, remembers what it found, and returns a
recommendation with its provenance - or an explicit "unresolved".

**The answer for 2020:** the administrative figure is 20 points above an
independent household measurement of the same year. Do not use it as the
coverage level; use the survey figure, with caveats.

**For 2023 there is no same-year survey**, so the answer is unresolved,
with the open questions listed. No number is invented.

> Source: `output_examples/example_1_cameroon_mcv1_2020_output.json`.

---

## Slide 3 - The agent workflow and architecture

```
planner ──POST /run──► orchestrator
                          │
                          ├─► investigator  ─proposes evidence─► critic
                          │                                       │
                          │                    verifies every number against
                          │                    the publication it came from
                          │                                       │
                          │                                       ▼
                          │                                   arbiter
                          │                                       │
                          │                                       ▼
                          │                                  adjudicator
                          │                                       │
                          │                                       ▼
                          └─◄── memory (H-MEM) ──◄──────── reporter
```

- **investigator** proposes which evidence to gather next - it never decides.
- **critic** checks every number against the publication it came from, and
  raises the challenge. A challenge that would change the verdict goes
  back to the investigator.
- **arbiter** makes the deterministic decision.
- **adjudicator** gates the model's proposed disposition against the
  evidence.
- **memory** (H-MEM) hands a later investigation what an earlier one found.

Every step is on the trace, with the agents and the handovers.

The planner can also send the question from the investigation page at
`/ui/`, which the same server hosts - it makes the same `POST /run`.

> Source: `logs/trace-<run_id>.jsonl`, `src/coordination.py`.

---

## Slide 4 - The technical stack

| | |
|---|---|
| Data | **Zetaris** - a compiled, deployed and activated Unified Semantic Layer over four connector types: REST, filestore, JDBC, Schema Store View |
| AI | **Meterless Nightshift** through the Meterless Runtime, behind an adapter with a timeout and a deterministic fallback |
| Memory | **Meterless H-MEM** - the persistent memory the agent learns from |
| Model | **NVIDIA Nemotron** behind the Nightshift lane |
| Language | Python, standard library plus `pypdf` and `openpyxl`. Nothing is installed at run time. |
| Interface | `run.py`: an HTTP service, a one-shot command, or a health check; the same server hosts the investigation page at `/ui/` |

> Visual: the semantic layer's lineage columns, and the trace's agent
> handover lines.

---

## Slide 5 - How Zetaris was used

**It is the backbone, not a mirror.** The agent asks one question of one
table:

```
lightning.metastore.cross_examiner.coverage_observations.coverage_observation
```

- 262 rows: **one row per reported number**, from five sources over
  four connector types.
- Every row carries its lineage: the source and its type, the series the
  number comes from, whether it is a derived copy, whether it was
  generated, and how far it may be trusted.
- The **World Bank** series is reached by the engine itself, over the
  public API.
- The **generated** district returns live in their own source, are
  labelled synthetic, and never become a finding about a real country.

> Command: `python3 scripts/verify_usl.py` - 18/18 checks.

---

## Slide 6 - How Meterless was used, and what was unique

**H-MEM is the engine in a working feature.** The first investigation
stores what it found:

```
cross-examiner:conflict:Cameroon:MCV1:2020
```

and the next investigation of the same country, antigen and year
retrieves it and **changes its plan**: it goes for the survey evidence
first, because an earlier run already found the conflict. That
difference is proved deterministically (`tests/test_memory_workflow.py`)
and live (`scripts/verify_journey.py`).

**Nightshift** proposes the evidence and raises the challenge, behind an
adapter.

**What was unique:** the lineage is not decoration in the report, it is
a column in the layer, and the agent counts a series once with its
origin. The World Bank and the UNICEF data warehouse both republish the
WUENIC estimate, so three publications of one series are **one** line of
evidence, not three. Revisions are handled the same way: the country
profiles publish the 2023 revision of the estimates and the workbook the
2025 one, so the layer records a revision difference, not a conflict. An independent measurement is a different thing
altogether, and it is the only thing that can say which figure to act
on. Most RAG applications cannot tell those two cases apart.

---

## Slide 7 - Product visuals

- The investigation page at `/ui/`: the run on screen - the evidence
  table with its lineage, the trace timeline, the conclusion with its
  review status, and the run details with the raw JSON.
- The API response for 2020: the three numbers, their lineage, the
  conflict, the recommendation, the confidence and the open questions.
- The trace excerpt: `critic -> arbiter`, `memory -> investigator`.
- The evaluation: 6/6 planted contradictions detected, 0/12 false
  positives on clean controls.

> Source: the page served by `src/app.py` at `/ui/`; `output_examples/`,
> `logs/`, `eval/results.json`.

---

## Slide 8 - Future enhancements

- **The same lineage model over more countries.** The layer is already
  a common schema; adding a country is a source registration and a
  registry entry.
- **A second engine.** H-MEM carries a fact across runs; a Markovian
  engine would carry a long investigation across bounded steps, and the
  two compose.
- **The survey's own report, re-read.** The DHS reports are not
  machine-readable here. With a parser, the survey figure would be
  verified against the survey's own table and become independently
  verified rather than independently measured.
- **Watchdogs on the denominators.** The administrative line is the one
  that fails, and it fails because of the target population. A check
  that flags a denominator change against the previous year would catch
  it before the gap does.

---

## Closing slide

**Cross-Examiner** - one semantic layer, one registry, and an agent
that says what the evidence supports.

- The layer: `lightning.metastore.cross_examiner.coverage_observations.coverage_observation`
- The engine: H-MEM, and what it changes in a later run
- The measure: 252 tests, 18/18 live layer checks, 6/6 contradictions
  caught, 0/12 false positives
- The honest part: for 2023 the answer is unresolved, and the system
  says so.
