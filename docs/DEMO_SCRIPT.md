# The demo script

**1 to 4 minutes.** The recommended length is 2:30 to 3:30. The
segments below add up to about 3:10.

The rules that bind it (`demo-video-guide.md`): MP4 preferred, 1080p
preferred, **audio required**, no API keys or `.env` contents on screen,
and "the input and output must be real". A wait may be cut; a fake
result may not.

Every command below is one that was run on this machine. Run them
before you record, so nothing surprises you.

Sample-mode note: the commands in "Before you record" assume the live
Zetaris instance and the Meterless H-MEM engine are running. If only
the sample-mode path is available, replace `python3 -m src.app` with
`SAMPLE_MODE=true python3 -m src.app`, replace `python3 scripts/verify_usl.py`
with `python3 -m unittest tests.test_usl_offline`, and use
`SAMPLE_MODE=true python3 -m src.analyzer --source csv --model off`.
Sample mode does not exercise live H-MEM persistence or live Nightshift
model calls.

---

## Before you record

```sh
cd ~/hackathon/cross-examiner
export PATH="$HOME/.nvm/versions/node/v24.22.1/bin:$PATH"

# 1. the evidence API, which the Zetaris tables read
python3 -m src.evidence_api &

# 2. the semantic layer, live
python3 scripts/verify_usl.py

# 3. the checks and the tests, so you know the state
python3 -m unittest discover -s tests
python3 scripts/secret_scan.py
```

Have these ready in separate terminals, with the output trimmed to what
matters:

| Terminal | Command | Why |
|---|---|---|
| A | `python3 -m src.app` | the API |
| B | `tail -f logs/trace-*.jsonl` | the live trace |
| C | `python3 scripts/verify_usl.py` | the semantic layer |
| D | a browser on `http://127.0.0.1:8000/ui/` | the same runs on the page, for a viewer who should not have to read JSON |

Terminal A serves the page too: it is not a separate server, and it is
checked by `python3 -m unittest tests.test_ui`.

---

## Segment 1 — The problem (0:15–0:25)

**Say:** Track 1, Solving Fragmented Intelligence. The user is a
programme planner in a health ministry who has to choose one coverage
figure to fund outreach with. For Cameroon MCV1 in 2020, three numbers
are published: the reconciled estimate 63, the administrative figure 74,
and the household survey 54. The planner has to pick one, and the
sources do not say which.

**Show:** the three numbers on screen. Nothing else.

---

## Segment 2 — The solution (0:20–0:30)

**Say:** Cross-Examiner reads every published figure through a Zetaris
semantic layer that carries each number's lineage. It tells a derived
republication apart from an independent measurement, cross-examines the
administrative figure against the survey, and remembers what it found.

**Show:** the schema of the semantic layer - the columns that carry the
lineage.

```sh
python3 scripts/query_zetaris.py \
  "SELECT source_id, source_type, origin_id, is_derived, verification_scope, COUNT(*) AS rows FROM lightning.metastore.cross_examiner.coverage_observations.coverage_observation GROUP BY 1,2,3,4,5 ORDER BY 1"
```

---

## Segment 3 — The agents and how they interact (0:30–0:45)

**Say:** Four agents and a memory. The investigator proposes which
evidence to gather, the critic checks every number against the
publication it came from, the arbiter decides, and the adjudicator
gates what the model is allowed to conclude. The memory hands a later
investigation what an earlier one found.

**Show:** a short trace excerpt with the agents and the handovers.

```sh
python3 - <<'PY'
import json, glob
path = sorted(glob.glob("logs/trace-*.jsonl"))[-1]
for line in open(path):
    e = json.loads(line)
    if e.get("agent_name") == "orchestrator" and e.get("action") == "run.started":
        continue
    print(f"{e['agent_name']:>13} -> {e.get('target_agent') or '-':<13} {e['action']}")
PY
```

---

## Segment 4 — A live run (0:45–1:05)

**Say:** Here is the planner's question, going into the running system.

**Show:** the API call and the answer. Cut the wait, but keep the real
input and the real output.

```sh
curl -s -X POST http://127.0.0.1:8000/run \
  -H 'Content-Type: application/json' \
  -d @input_examples/example_1_cameroon_mcv1_2020.json | python3 -m json.tool
```

**Point at:**
- `"source_id": "lightning.metastore.cross_examiner.coverage_observations.coverage_observation"`
  in `semantic_layer` - the layer answered, not a local file;
- the finding's `lineage` - three measures, each with its origin, its
  `is_derived` flag and its `verification_scope`;
- `"recommendation"` - use the household survey figure (54) for the
  coverage level, with the caveats;
- `"confidence": "moderate"` and `"review_status": "REVIEW"` - it is
  corroborated but not settled, and it says so;
- `"uncertainties"` - what is still open.

**Or show the same run on the page.** The page at `http://127.0.0.1:8000/ui/`
sends the same `POST /run`; nothing speeds it up or fakes it. Choose the
Cameroon example, press **Investigate**, and the same answer is on screen
as the evidence table with its lineage, the trace timeline, the
conclusion with its review status, and the run details with the raw JSON.

Then the harder case, which is the one to spend the time on:

```sh
curl -s -X POST http://127.0.0.1:8000/run \
  -H 'Content-Type: application/json' \
  -d @input_examples/example_5_ethiopia_mcv1_2017.json | python3 -m json.tool
```

**Say:** Ethiopia, 2017. The administrative figure is 92, the
reconciled estimate 59, and the household survey 58. The two
independent processes agree with each other and the administrative line
is the outlier, 34 points out. And notice the estimate: the country
profile publishes the 2023 revision and the workbook publishes the 2025
revision, so the layer records a **revision difference** rather than a
conflict.

Then the one that matters for the track:

**Say:** The World Bank publishes the same estimate. It is not a second
opinion: the layer records it as derived from the same series, so it
cannot be counted as confirmation.

```sh
python3 scripts/query_zetaris.py \
  "SELECT source_id, origin_id, is_derived, independent_capable, COUNT(*) FROM lightning.metastore.cross_examiner.coverage_observations.coverage_observation WHERE metric_type='wuenic' GROUP BY 1,2,3,4"
```

---

## Segment 5 — The sponsors doing real work (0:20–0:30)

**Say:** Zetaris is the data backbone: one semantic layer over four
connector types - REST, filestore, JDBC and Schema Store View - and the
agent asks one question of it. Meterless does two things: H-MEM is the
persistent memory, and Nightshift is the AI provider behind the
proposals and the critiques.

**Show:** the trace's Zetaris and model calls, live.

```sh
tail -f logs/trace-*.jsonl | grep -E '"agent_name":"(memory|investigator)"'
```

Then the memory, which is the strongest single piece of evidence:

```sh
# the first run stores what it found
python3 -m src.analyzer --source zetaris --model off \
  --question "Cameroon MCV1 coverage discrepancy 2020" --remember

# the second run retrieves it and changes its plan
python3 -m src.analyzer --source zetaris --model off \
  --question "Cameroon MCV1 coverage discrepancy 2020"
```

**Say:** The second run does not start from scratch. It recalls the
conflict the first run found and goes for the survey evidence first.

**Show:** the `recall.prior_findings` line in the second trace, and the
`plan.fetch_source_document` line that follows it.

---

## Segment 6 - The output, and why it matters (0:30–0:40)

**Say:** For 2020 the answer is a recommendation with its provenance:
use the survey figure for the coverage level, with caveats, and do not
use the administrative figure. For 2023 there is no independent
measurement in the same year, so the system says "unresolved" and lists
what is open instead of inventing an answer.

**Show:** the 2023 answer.

```sh
curl -s -X POST http://127.0.0.1:8000/run \
  -H 'Content-Type: application/json' \
  -d @input_examples/example_2_cameroon_mcv1_2023.json | python3 -m json.tool
```

or the 2023 example on the page, where the open questions sit under the
verdict instead of inside the JSON.

---

## Segment 7 - The evaluation and the limits (0:20–0:30)

**Say:** The checks are measured against generated records with planted
contradictions and an equal number of clean controls.

```sh
python3 eval/run_eval.py
```

**Say:** And here is what it cannot do, stated plainly.

```sh
python3 scripts/verify_journey.py
```

The last line of the demo should be the honest one: for 2023 the answer
is unresolved, and that is the point.

---

## Recording notes

- **Audio is required.** Record the narration.
- **No keys on screen.** The terminal frames around `.env` and
  `export` are the usual accident. `python3 scripts/secret_scan.py`
  checks the repository and the traces, not the video.
- **Do not show a trace you edited.** If a run is slow, cut the wait.
- **Keep the track name in the first segment.** The README, the deck
  and the video must name the same track.
- **Back up the video.** Host it somewhere that opens without a
  request, keep a local copy, and put the link in the README.
