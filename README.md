# Cross-Examiner

An agent that tells a public-health programme planner which reported
immunization-coverage figure to trust.

Built by Team RadixMente.

Three numbers are published for the same country, antigen and year: the
WHO/UNICEF reconciled estimate, the administrative figure from the
national reporting system, and the figure a household survey found. They
routinely disagree. A planner has to pick one to target outreach with,
and the sources do not say which one to believe.

Cross-Examiner reads the figures through one Zetaris unified semantic
layer, checks each one against the publication it came from, counts the
sources that share an upstream once instead of many, cross-examines the
administrative figure with an independent household measurement, remembers
what it found, and returns a recommendation with its provenance - or an
honest "unresolved, a human has to look at this".

It never claims to know the true coverage. It says what the evidence
supports and what it does not.

**The example.** Cameroon, MCV1, 2020:

| Line | Value | What produced it |
|---|---|---|
| WUENIC estimate | 63% | A reconciliation of administrative, survey and other evidence |
| Administrative coverage | 74% | Facility and district reports against a population denominator |
| Household survey coverage | 54% | A sample of households |

The agent's answer: the administrative figure is **20 points above an
independent household measurement** of the same year, so it is not
usable as the coverage level. Use the survey figure, with caveats. It
does not say the WUENIC estimate is right - it says the two published
figures disagree, that the disagreement is real, and what an independent
measurement says about it.

For 2023 there is no household measurement in the same year, so the
agent has nothing independent to compare against and says so.

**Ethiopia, the harder case.** MCV1, 2017:

| Line | Value |
|---|---|
| WUENIC estimate (2025 revision) | 59% |
| Administrative coverage | 92% |
| Household survey coverage | 58% |

The administrative figure is **34 points above the household
measurement**, and the measurement *agrees with the reconciled
estimate* (58 against 59). Here the two independent processes point the
same way, and the administrative line is the outlier. The agent says so.

It also says something subtler: the country profile publishes the
**2023 revision** of the estimate (58 for 2017) while the workbook
publishes the **2025 revision** (59). That is a revision, not a
conflict, and the layer records it as such.

---

## What it will not do

- It will not call a source independent when the source merely
  republishes another series. The World Bank and the UNICEF data
  warehouse both republish the WUENIC estimate (63 and 71 for Cameroon
  MCV1, identical to the workbook), so they are one line of evidence, not
  two. That rule is data, in `data/sources.json`, and it is enforced in
  SQL, in the semantic layer, not in a Python helper.
- It will not dispose of a finding that is built on generated records.
- It will not read the evaluation answer key.
- It will not invent a figure where none was published. A year with no
  independent measurement comes back as an explicit review, with the open
  questions listed.

---

## Architecture

```
   a planner                    the Cross-Examiner service                  the platform
      │                                     │                                     │
      │  POST /run                           │                                     │
      ├────────────────────────────────────►│                                     │
      │                                      │  read the evidence                   │
      │                                      ├────────────────────────────────────►│
      │                                      │   Zetaris unified semantic layer    │
      │                                      │   lightning.metastore.cross_examiner │
      │                                      │   .coverage_observations             │
      │                                      │   .coverage_observation              │
      │                                      │                                     │
      │                                      │  one row per reported number, with   │
      │                                      │  its lineage: source, series,        │
      │                                      │  derivation, independence, synthetic │
      │                                      │                                     │
      │                                      ├─────► Meterless (Nightshift) ───────►│
      │                                      │        the model proposes, it never │
      │                                      │        decides                      │
      │                                      │                                     │
      │                                      ├─────► H-MEM ─────────────────────►│
      │                                      │        what an earlier run found    │
      │                                      │                                     │
      │  200 OK                               │                                     │
      │  findings, lineage, evidence ids,    │                                     │
      │  confidence, review status, run id   │                                     │
      │◄────────────────────────────────────┤                                     │
      │                                     │                                     │
      │  GET /traces/<run_id>                │                                     │
      ├────────────────────────────────────►│   logs/trace-<run_id>.jsonl          │
```

The parts, and what each one is for:

| Part | Where | What it does |
|---|---|---|
| **The semantic layer** | Zetaris, `lightning.metastore.cross_examiner.coverage_observations` | One row per reported number, with its lineage. Compiled, deployed, activated. |
| **The registry** | `data/sources.json` | Which publication is which, which series it belongs to, whether it is derived or generated. |
| **The connector layer** | `src/zetaris_source.py` | Reads the layer; falls back to the ordinary view, then to the local files. |
| **The runner** | `src/runner.py` | One investigation: read, analyse, investigate, remember, trace. |
| **The critics** | `src/critic.py`, `src/evidence_ledger.py` | Check each number against its own publication; decide how far each check reaches. |
| **The investigator** | `src/investigator.py` | The model proposes which evidence to gather next. It never decides. |
| **The adjudicator** | `src/adjudicator.py` | The gate that decides, and the recommendation. |
| **The memory** | `src/memory_bridge.py`, `src/memory_policy.py` | What an earlier run found, and what it changes about this one. |
| **The API** | `src/app.py` | `GET /health`, `POST /run`, `GET /traces/<run_id>`, and the page at `/ui/`. |
| **The checks** | `src/programme_checks.py` | The checks on district programme returns. |
| **The trace** | `src/tracing.py` | Every run writes `logs/trace-<run_id>.jsonl`. |

### The evidence scopes

| Scope | What it means |
|---|---|
| `INDEPENDENT_VERIFICATION` | The value was checked against the source's own published table, from a different series than the one it came from. |
| `SELF_CONSISTENCY` | The value was compared with the extract it came from, or with another publication of the same series. It proves the extraction worked. |
| `INDEPENDENT_MEASUREMENT` | The number comes from a measurement that does not derive from the numbers it is compared with - a household survey rather than administrative reporting. Independent evidence about the level, not a verification of the other numbers. |
| `DOCUMENT_PRESENCE` | The document was retrieved so it could be inspected. Its contents are not verified. |
| `CONTEXT_ONLY` | Context. Context is never treated as proof. |

Only the first scope may support a positive disposition.

---

## The unified semantic layer

The layer is a real Zetaris USL, not a view with a reassuring name.

```
namespace  lightning.metastore.cross_examiner
USL        coverage_observations
table      coverage_observation          25 columns, 262 rows
query it   SELECT * FROM lightning.metastore.cross_examiner.coverage_observations.coverage_observation
```

Its table carries the lineage of every row: `source_id`, `source_type`,
`source_name`, `source_ref`, `origin_id`, `origin_label`,
`derived_from`, `is_derived`, `is_synthetic`, `independent_capable`,
`verification_scope`, `verification_status`, alongside the country,
antigen, year, measure, value, unit, denominator and definition.

| Source | Connector | Where it is read from |
|---|---|---|
| the published coverage figures | REST / JSON | the project's evidence API |
| the WUENIC workbook extract | REST / JSON | the project's evidence API |
| the compiled household-survey sheet | REST / JSON | the project's evidence API |
| the World Bank `SH.IMM.MEAS` series | REST / JSON | `api.worldbank.org`, reached by the engine itself |
| the generated district returns | JDBC / SQLite | the shared volume |
| a public NOAA file | filestore / CSV | `s3a://noaa-ghcn-pds`, proving the filestore connector works |

Four connector types, seven sources, nine upstream origins. The layer
holds 267 rows for Cameroon and Ethiopia.

`docs/USL.md` has the column mapping and the objects in the instance.
`data/registry/` holds every statement, one file per source type plus
the runbook, with what was tried and what is blocked recorded in it.

### Verifying it

```sh
python3 scripts/verify_usl.py             # live: 18 checks against the instance
python3 -m unittest tests.test_usl_offline  # offline: the same rules, with fixtures
```

---

## The memory: what an earlier run changes

The memory store is not a log.

- **First run.** The agent finds that the administrative figure for
  Cameroon MCV1 2020 sits 20 points above the household survey, and
  stores that in H-MEM, together with what is still open.
- **Later run.** The agent retrieves it, and the plan changes: instead of
  re-reading the estimate first, it goes for the survey evidence, and
  its reason says that an earlier investigation of the same country,
  antigen and year already found the conflict, so the question now is
  whether it still holds.

That difference is proved deterministically in
`tests/test_memory_workflow.py`, and live by
`scripts/verify_journey.py`. Both the retrieval and the write are on the
trace (`memory.recalled`, `memory.stored`).

The memory store is the Meterless H-MEM engine, reached through
`my-agent/cross_examiner_memory.ts`. It needs Node 18 or newer:

```sh
export PATH="$HOME/.nvm/versions/node/v24.22.1/bin:$PATH"
```

---

## Repository layout

```
run.py                    the programmatic entry point: service, --once, --health
engine/
  cross_examiner_memory.ts  the H-MEM bridge
  src/engine.ts            the engine loader
  vendor/hmem/             the Meterless H-MEM reference (Apache-2.0)
  .notebook/               the memory store
src/
  app.py                  the HTTP API
  runner.py               one investigation, shared by the CLI and the API
  tracing.py              the JSONL trace and the secret redaction
  memory_policy.py        what a remembered investigation changes
  analyzer.py             the command line
  zetaris_source.py       reads the semantic layer
  evidence_sources.py     which sources were read
  source_registry.py      the lineage of every number
  critic.py               the checks, and how far each one reaches
  evidence_ledger.py      the registry of what was gathered
  investigator.py         the model proposes, it never decides
  adjudicator.py          the gate, and the recommendation
  arbiter.py              the deterministic decision
  coordination.py         the bounded investigation loop
  reporter.py             the report
  model_client.py         Nightshift, behind an adapter
  memory_bridge.py        the H-MEM engine
  programme_checks.py     the checks on district returns
data/
  sources.json            the registry: every source, series and derivation
  sources.csv             the same registry, flattened
  survey_figures.csv      the compiled household-survey sheet
  coverage_evidence.csv      the published coverage figures
  synthetic_programme_reports.csv  the generated district returns
  registry/               the Lightning SQL, one file per source type, plus the runbook
  README.md               every source, its licence and its lineage
docs/
  USL.md                  the semantic layer and the column mapping
  DEMO_SCRIPT.md          the 1-4 minute demo, segment by segment
  SLIDES.md               the deck, one slide per required point
  SUBMISSION_CHECKLIST.md every mandatory step, and what needs a human
scripts/
  verify_usl.py           18 checks against the running instance
  verify_journey.py       the eight steps of the user journey
  verify_container.sh     the container against the running instance
  secret_scan.py          no key in the repository or in the traces
  make_synthetic.py       the seeded generator
  generate_usl_sql.py     the USL SQL, from the registry
  generate_examples.py    runs the examples and writes the outputs
  export_sources.py       the registry, flattened
eval/run_eval.py          the evaluation harness
ui/                       the investigation page, served at /ui/
input_examples/           five example requests
output_examples/          five answers, from real runs
logs/                     the traces of the runs
tests/                    256 tests
```

---

## Running it

### Setup

```sh
cd ~/hackathon/cross-examiner
python3 -m pip install -r requirements.txt     # needed for sample and live mode

# Live mode only: the H-MEM engine's TypeScript runner
cd engine && npm install && cd ..
```

Note for this submission: `data/wuenic2025rev_web-update.xlsx` is not bundled because its redistribution permission is unconfirmed. The WUENIC rows used in sample mode come from `data/coverage_evidence.csv`; the optional `src/evidence_api.py` `/wuenic` endpoint returns an empty result when the workbook is absent.

That is the whole setup. The engine's source is vendored in
`engine/vendor/hmem` (Apache-2.0, no runtime dependencies), so `npm
install` only fetches the TypeScript runner. Node 18 or newer is needed
for the memory; without it the application runs and says the memory is
unavailable.

### The API

```sh
cd ~/hackathon/cross-examiner

# live: the deployed semantic layer and the memory store
python3 -m src.app                    # http://0.0.0.0:8000

# offline: no credentials, no network
SAMPLE_MODE=true python3 -m src.app
```

```sh
curl -s http://127.0.0.1:8000/health | python3 -m json.tool

curl -s -X POST http://127.0.0.1:8000/run \
  -H 'Content-Type: application/json' \
  -d @input_examples/example_1_cameroon_mcv1_2020.json | python3 -m json.tool
```

`POST /run` takes:

| field | default | meaning |
|---|---|---|
| `question` | - | the planner's question |
| `country`, `antigen`, `year` | - | narrow the investigation to one country, antigen and year |
| `source` | `auto` | `auto`, `zetaris` or `local` |
| `model` | `auto` | `auto`, `off`, or a model id |
| `use_memory` | `true` | read the memory store |
| `remember` | `false` | write what this run found into the memory store |
| `threshold` | `5` | the gap, in percentage points, that counts as a discrepancy |
| `max_iterations` | `4` | the cap on the investigation loop |
| `include_synthetic` | `false` | also read the generated district returns |

and returns the run id, the status, the findings with their lineage, the
evidence ids, the confidence and the review status, the conflicts, the
recommendation, what was recalled from memory, the stop reason and the
trace file. An invalid request comes back as a `400` with a message that
says what to change.

### The web UI

The same server also serves a page, for a judge who does not want the
terminal:

```sh
cd ~/hackathon/cross-examiner
SAMPLE_MODE=true python3 -m src.app    # offline: cached data, no credentials
python3 -m src.app                      # live: needs the Zetaris instance
```

Then open http://127.0.0.1:8000/ui/. (`http://127.0.0.1:8000/ui` without
the slash redirects there.) The page asks the planner's question,
prefilled with the Cameroon MCV1 2020 example; the example buttons fill in
the others. It calls `POST /run` and shows what came back: the evidence and
its lineage, the trace from `GET /traces/<run_id>`, the conclusion and
review status, and the run details with the raw JSON.

The page is three static files, `ui/index.html`, `ui/styles.css` and
`ui/app.js`, with no build step and no dependencies. The same server serves
them, so the page calls the API it was loaded from. If the API is not
running, the page says so and shows how to start it. A failed run never
leaves an earlier answer on the page.

"Store what this run finds in memory" is off by default. Ticking it writes
to the H-MEM store, as `--remember` does on the command line. It is disabled
in sample mode, which does not use the memory store. The UI's tests are
`python3 -m unittest tests.test_ui`.

### The programmatic entry point

`run.py` is the entry point a judge can drive without clicking through
a screen:

```sh
python3 run.py                       # the service on 0.0.0.0:8000
python3 run.py --health              # one health check, as JSON
python3 run.py --once request.json   # one investigation, as JSON
```

The request may be flat or wrapped:

```json
{"question": "...", "country": "Cameroon", "antigen": "MCV1", "year": "2020"}
{"run_id": "...", "input": {...}, "options": {...}}
```

and the answer carries `run_id`, `status`, `output`, `agents`,
`trace_id`, `log_file` and `execution_time_seconds`. A request that
cannot be honoured comes back as a structured error, not a stack trace.

### The command line

```sh
# the deterministic run, no model, no network
python3 -m src.analyzer --source csv --model off --report reports/report.md

# the same thing through the entry point
python3 run.py --once input_examples/example_1_cameroon_mcv1_2020.json

# through the semantic layer, with the model, remembering what it finds
python3 -m src.analyzer --source zetaris \
  --question "Cameroon MCV1 coverage discrepancy 2020" \
  --model auto --remember --report reports/report.md

# the generated data and the evaluation
python3 scripts/make_synthetic.py
python3 eval/run_eval.py

# the checks
python3 -m unittest discover -s tests
python3 scripts/verify_usl.py
python3 scripts/verify_journey.py
python3 scripts/secret_scan.py
```

### The submission material

| Artifact | Where |
|---|---|
| the demo, segment by segment | `docs/DEMO_SCRIPT.md` |
| the deck, one slide per required point | `docs/SLIDES.md` |
| every mandatory step, and what needs a human | `docs/SUBMISSION_CHECKLIST.md` |

### The trace

Every run writes `logs/trace-<run_id>.jsonl`: one object per line, with
`timestamp`, `run_id`, `agent_name`, `action`, `input_summary`,
`output_summary`, `target_agent`, `confidence`, `retry_count` and
`status`. The service writes the log to stdout as well as to the file.

Four agents take part, and the handovers between them are visible:

| Agent | What it does | Hands over to |
|---|---|---|
| `investigator` | proposes which evidence to gather next | `critic` |
| `critic` | checks every number against the publication it came from, and raises the challenge | `arbiter` |
| `arbiter` | makes the deterministic decision | `adjudicator` |
| `adjudicator` | gates the model's proposed disposition | `reporter` |
| `memory` | reads and writes the persistent memory | `investigator` |

A trace therefore shows more than a single pass, and it shows the
feedback loop: a challenge that would change the verdict is handed back
to the `investigator`.

### Docker

```sh
docker build -t cross-examiner .
docker run --rm -p 8000:8000 cross-examiner        # sample mode
```

The image installs its dependencies while it is built, never while it
runs, and starts in sample mode, so it answers without credentials and
without a network.

Against the running Zetaris instance, with the memory:

```sh
bash scripts/verify_container.sh
```

which builds the image, starts the container with the Zetaris client
mounted and the API key passed as a runtime variable, and checks that
the container read the deployed semantic layer. It was run on 26 October
2026: the container answered `/health` with 262 rows from the layer and
the memory store available.

---

## Live and offline modes

| | live | sample |
|---|---|---|
| the semantic layer | the deployed USL | the same rows from `data/` |
| the memory store | H-MEM, read and written | not touched |
| the model | Nightshift through Meterless | the deterministic rules only |
| the response says | `"mode": "live"` | `"mode": "sample"`, and every finding is marked `data_kind: "sample:..."` |
| what it needs | a Zetaris instance and the API key | nothing |

`SAMPLE_MODE=true` never reaches the network, whatever the caller asks
for. Generated records are excluded from the findings unless they are
asked for, and when they are included they are marked `data_kind:
"synthetic"` and are checked by their own rules - they never become a
finding about a real country.

---

## The sources

`data/README.md` has the full table: what each source is, where it comes
from, which series it belongs to, and whether it is derived or generated.
`docs/USL.md` has the source-column mapping and the objects in the
instance.

The short version:

- The WUENIC workbook (XLSX) and the WHO/UNICEF country profiles (PDF,
  one per country) are the two published figures, and they share an
  upstream.
- The country profiles also publish a **household-survey row**, which
  does not derive from administrative reporting. It is the independent
  line.
- The DHS survey report is a second independent line, for the year the
  Cameroon country profile does not cover.
- The World Bank and the UNICEF data warehouse republish the estimate.
- The district programme returns are generated, labelled, and never
  evidence.
- The country profiles publish an **earlier revision** of the estimates
  than the workbook. The registry gives each revision its own origin and
  the same series, so a revision can neither confirm nor contradict the
  other - it is a revision.

---

## The generated data

`scripts/make_synthetic.py` writes a fictional programme's district
returns with a fixed seed: planted contradictions with known answers and
an equal number of clean controls, so a false positive is visible.

- Every row carries `is_synthetic=true` and the source label
  `SYNTHETIC district programme reports`.
- The generator is seeded, so the same seed always produces the same
  file.
- The answer key lives in `eval/` and only the harness reads it. A test
  fails if anything under `src/` refers to it.

`python3 eval/run_eval.py` measures the checks against it:

```
planted contradictions detected: 6/6 (1.0)
false positives on clean controls: 0/12 (0.0)
```

---

## A short demo walkthrough

1. **Show the question.** Three numbers for Cameroon MCV1 2020:
   administrative 74, WUENIC 63, household survey 54. Which do we plan
   against? (Ethiopia 2017 is the sharper case: administrative 92,
   estimate 59, survey 58.)
2. **Show the layer.** `python3 scripts/verify_usl.py` - the USL is
   deployed and activated, five sources contribute, the World Bank's copy
   of the estimate shares the estimate's origin, and every generated
   record is marked.
3. **Run it.** `curl -s -X POST http://127.0.0.1:8000/run -d
   @input_examples/example_1_cameroon_mcv1_2020.json` - the response
   carries the three numbers with their lineage, the conflict, the
   recommendation (use the survey, 54, with caveats), the confidence
   (`moderate`), the review status (`REVIEW`) and the run id.
4. **Show the critique.** The trace at `logs/trace-<run_id>.jsonl` shows
   the evidence that was checked, what the model proposed, what the
   coordinator did and why it stopped.
5. **Show the memory.** Run it twice with `--remember`. The second run's
   plan starts with the survey evidence, because the first run's finding
   is in the store.
6. **Show the honesty.** Ask about 2023: there is no independent line for
   that year, so the answer is an explicit review with three open
   questions, and no number is invented.

The example requests are in `input_examples/`, and what they answered -
generated by real runs - is in `output_examples/`.

---

## Limitations

- The published reports from the DHS Program cannot be parsed in this
  environment, so a survey figure transcribed from one is labelled
  `transcribed_from_publication` and is not re-read during a run.
- The survey figure the country profile publishes was read from a
  publication that also carries the administrative line. It is an
  independent *measurement*, not an independently verified number.
- There is no same-year household survey for Cameroon MCV1 2020 or 2023
  in a source that can be reached from here, so those years cannot be
  closed.
- The filestore connector on this instance only accepts `s3a://` paths,
  so the project's own files cannot be registered as file tables. The
  compiled survey sheet goes through the REST connector instead. The
  evidence and the reasoning are in
  `data/registry/05_survey_filestore_create.sql`.
- The memory store lives with the engine, in `engine/.notebook`. A
  container that is not given a volume keeps its memories for the life
  of the container.
- The World Bank answers `[meta, data]`, which the REST connector does
  not unwrap; the observation view decodes it with the documented
  `get_json_object` and `from_json` pattern.
- Three of the six sources still travel through the project's own
  evidence API. The World Bank series is the one the engine reaches on
  its own. The response says which path was used.
- The API is built on the standard library only, so it is not
  FastAPI; the project installs nothing at run time.

---

## Disclosure

Required by the hackathon's AI usage policy. Kept in one place, and kept
true.

**1. Model providers and models used.** Meterless Nightshift, reached
through the Meterless Runtime's OpenAI-compatible endpoint
(`POST /v1/chat/completions`). The model is whatever the Runtime routes
to; the project pins `nvidia/nemotron-3-ultra-550b-a55b` so the NVIDIA
contribution is unambiguous, and `meterless/auto` by default. The model
proposes which evidence to gather and challenges a claim. It never
decides: every number is checked by the deterministic code, and a
proposal that names an action outside the allowlist is rejected and the
rejection is recorded.

**2. Agent frameworks used.** None. The agents are ordinary Python
functions with an explicit allowlist, a bounded loop and a shared
ledger. That is a deliberate choice: the evidence discipline is the
point of the project, and a framework would have hidden it.

**3. How the sponsor technologies are used.**
- **Zetaris** - the backbone. The evidence is read through a compiled,
  deployed and activated Unified Semantic Layer
  (`lightning.metastore.cross_examiner.coverage_observations.coverage_observation`),
  whose table carries the lineage of every row. Four connector types:
  REST, filestore, JDBC and Schema Store View. The World Bank series is
  reached by the engine itself.
- **Meterless (H-MEM)** - the engine. It is the persistent memory: the
  first run stores what it found, and a later run retrieves it and
  changes its plan because of it. The engine lives in `my-agent/` and is
  reached through `src/memory_bridge.py`.
- **Meterless Nightshift** - the AI provider, behind an adapter with a
  timeout and a deterministic fallback.
- **Cursor** - the development environment. The repository scaffolding,
  the Zetaris adapter and the tests were written with Cursor's Agent
  chat, and every change was reviewed before it was accepted.
- **NVIDIA** - the Nemotron model behind the Nightshift lane, which
  powers the investigation proposals and the critiques.

**4. External tools and libraries.** `pypdf` (reading the WHO country
profile) and `openpyxl` (reading the WUENIC workbook). Everything else
is the Python standard library, so nothing is installed at run time.

**5. Data sources, and what is sample or synthetic.**
- The WHO/UNICEF country profile for Cameroon (PDF, public).
- The WHO/UNICEF Estimates of National Immunization Coverage, 2025
  revision (XLSX, public).
- The World Bank Indicators `SH.IMM.MEAS` series (public REST/JSON).
- The DHS Program's Cameroon DHS 2018 summary report: one figure,
  transcribed by hand into `data/survey_figures.csv` with its citation,
  because the report is not machine-readable here.
- `data/synthetic_programme_reports.csv` is **generated** by
  `scripts/make_synthetic.py`. It is labelled synthetic everywhere, it is
  excluded from the findings unless it is asked for, and it never
  substantiates a real-world conclusion.

**6. Open-source code or templates materially adapted.** The H-MEM
reference engine, vendored by the Meterless starter into `my-agent/`
unchanged, and the Zetaris getting-started repository, used as the
source of the Lightning SQL recipes and the client helper. Nothing else
was copied.

**7. Known limitations.** Listed in full below, and repeated in the
report the application writes: the DHS report cannot be parsed here, the
survey figure the country profile publishes was read from a publication
that also carries the administrative line, there is no same-year
household survey for 2020 or 2023, the filestore connector only accepts
`s3a://` paths, and three of the six sources still travel through the
project's own evidence API.

**8. Fallback and sample-mode behaviour.** `SAMPLE_MODE=true` runs the
whole application with no credentials and no network: the local files
answer instead of the layer, the memory store is not touched, the
deterministic rules replace the model, and every finding is marked
`data_kind: "sample:..."` so a reader can tell at a glance. It runs
real agent logic on the cached data - it does not replay a saved answer.

---

## Required technologies

| | |
|---|---|
| Zetaris | the unified semantic layer: the backbone of the evidence |
| Meterless Engine (H-MEM) | what an earlier run found, and what it changes |
| Meterless Nightshift | the model that proposes and challenges |
| NVIDIA (optional) | the Nemotron lane behind Nightshift |

Everything secret comes from the environment. `.env.example` lists the
model runtime settings; the Zetaris client reads `.env.local` from the
getting-started repository, the same convention that repository uses.

Never commit a key. If one ever reaches a commit, rotate it.
