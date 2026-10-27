#!/usr/bin/env python3
"""Walk the user journey and check every step of it.

Eight steps, each checked against what actually happened:

1. A user submits an investigation.
2. The application queries the deployed semantic layer.
3. The evidence is deduplicated by upstream origin.
4. Independent evidence is told apart from derived copies.
5. Contradictions trigger an iterative investigation.
6. H-MEM changes a later run.
7. The result and the trace can be inspected.
8. Missing independent evidence produces an explicit review outcome
   rather than an invented answer.

    python3 scripts/verify_journey.py            # live, needs Zetaris
    SAMPLE_MODE=true python3 scripts/verify_journey.py   # offline

The script prints what it checked and exits non-zero when a step fails.
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.app import run_payload  # noqa: E402
from src.memory_policy import CONFLICT_PREFIX  # noqa: E402
from src.tracing import read_trace  # noqa: E402

USL_TABLE = (
    "lightning.metastore.cross_examiner.coverage_observations"
    ".coverage_observation"
)


class Journey:
    def __init__(self):
        self.steps = []

    def step(self, number, name, passed, detail="", skipped=False):
        self.steps.append({
            "number": number,
            "name": name,
            "passed": bool(passed) or skipped,
            "skipped": bool(skipped),
            "detail": str(detail),
        })
        return passed

    @property
    def failed(self):
        return [step for step in self.steps if not step["passed"]]


def main():
    journey = Journey()
    sample = str(os.environ.get("SAMPLE_MODE", "")).lower() in (
        "1", "true", "yes", "on"
    )

    # 1. A user submits an investigation.
    payload = run_payload({
        "question": (
            "Which Cameroon MCV1 coverage figure should we plan against "
            "for 2020?"
        ),
        "country": "Cameroon",
        "antigen": "MCV1",
        "year": "2020",
        "source": "auto",
        "model": "off",
        "use_memory": False,
    })
    journey.step(
        1,
        "a user submits an investigation",
        bool(payload.get("run_id")) and payload.get("status") in (
            "review", "resolved", "abstained",
        ),
        f"run {payload.get('run_id')}, status {payload.get('status')}",
    )

    # 2. The application queries the deployed semantic layer.
    layer = (payload.get("semantic_layer") or [{}])[0]
    if sample:
        layer_ok = layer.get("origin") == "local"
        layer_detail = (
            f"sample mode: origin={layer.get('origin')}, "
            f"read from {layer.get('read_from')}"
        )
        layer_skipped = True
    else:
        layer_ok = (
            layer.get("origin") == "zetaris_usl"
            and layer.get("read_from") == USL_TABLE
        )
        layer_detail = (
            f"origin={layer.get('origin')}, object={layer.get('read_from')}"
        )
        layer_skipped = False
    journey.step(
        2,
        "the application queries the deployed semantic layer",
        layer_ok,
        layer_detail,
        skipped=layer_skipped,
    )

    # 3. The evidence is deduplicated by upstream origin.
    finding = (payload.get("findings") or [{}])[0]
    lineage = finding.get("lineage") or []
    estimates = [
        item for item in lineage if item.get("measure") == "WUENIC estimate"
    ]
    origins = {item.get("origin") for item in estimates}
    journey.step(
        3,
        "the evidence is deduplicated by upstream origin",
        len(estimates) <= 1,
        f"{len(estimates)} estimate line(s) in the finding, "
        f"origins {sorted(o for o in origins if o)}",
    )

    # 4. Independent evidence is told apart from derived copies.
    derived_independent = [
        item for item in lineage
        if item.get("is_derived") and item.get("independent_capable")
    ]
    survey = [
        item for item in lineage
        if item.get("measurement_kind") == "household_survey"
    ]
    journey.step(
        4,
        "independent evidence is told apart from derived copies",
        not derived_independent,
        f"{len(derived_independent)} derived lines marked independent, "
        f"{len(survey)} household-survey line(s)",
    )

    # 5. Contradictions trigger an iterative investigation.
    actions = payload.get("executed_actions") or []
    journey.step(
        5,
        "contradictions trigger an iterative investigation",
        bool(actions),
        f"{len(actions)} action(s) executed: "
        f"{[action.get('action') for action in actions][:4]}",
    )

    # 6. H-MEM changes a later run.
    memory_ok = False
    memory_detail = "the memory store was not available in this run"
    if not sample:
        from src.memory_bridge import query
        stored = query("Cameroon MCV1 coverage discrepancy 2020")
        conflicts = [
            memory for memory in (stored.get("memories") or [])
            if str(memory.get("source", "")).startswith(CONFLICT_PREFIX)
        ]
        if conflicts:
            warm = run_payload({
                "question": "Cameroon MCV1 coverage discrepancy 2020",
                "country": "Cameroon",
                "antigen": "MCV1",
                "year": "2020",
                "source": "auto",
                "model": "off",
                "use_memory": True,
            })
            recall = (warm.get("findings") or [{}])[0].get("memory_recall") or {}
            memory_ok = bool(recall.get("has_prior_conflict"))
            memory_detail = (
                f"a remembered conflict was recalled and changed the plan "
                f"to {recall.get('preferred_action')}"
                if memory_ok else
                "a remembered conflict was not recalled"
            )
        else:
            memory_detail = (
                "no conflict memory in the store yet; run "
                "python3 -m src.analyzer --remember first"
            )
    else:
        memory_detail = "sample mode does not use the memory store"

    journey.step(
        6,
        "H-MEM changes a later run",
        memory_ok,
        memory_detail,
        skipped=sample,
    )

    # 7. The result and the trace can be inspected.
    events = read_trace(payload["run_id"])
    trace_ok = bool(events) and any(
        event.get("action") == "run.finished" for event in events
    )
    # The log has to show more than one agent and the handovers between
    # them, or it does not show how the answer was reached.
    from src.tracing import agent_names, handoffs
    trace_ok = (
        trace_ok
        and len(agent_names(events)) >= 2
        and bool(handoffs(events))
    )
    from src.tracing import agent_names, handoffs
    journey.step(
        7,
        "the result and the trace can be inspected",
        trace_ok and bool(payload.get("findings")),
        f"{len(events)} trace events, "
        f"{len(agent_names(events))} agents, "
        f"{len(handoffs(events))} handovers, "
        f"in {payload.get('trace')}",
    )

    # 8. Missing independent evidence produces an explicit review outcome.
    without_survey = run_payload({
        "question": "Cameroon MCV1 coverage 2023",
        "country": "Cameroon",
        "antigen": "MCV1",
        "year": "2023",
        "source": "auto",
        "model": "off",
        "use_memory": False,
    })
    year_finding = (without_survey.get("findings") or [{}])[0]
    has_survey = any(
        item.get("measurement_kind") == "household_survey"
        for item in year_finding.get("lineage") or []
    )
    explicit = (
        year_finding.get("review_status") in ("REVIEW", "ABSTAIN")
        and year_finding.get("recommendation") is None
        and bool(year_finding.get("uncertainties"))
    )
    journey.step(
        8,
        "missing independent evidence produces an explicit review outcome",
        explicit and not has_survey,
        f"2023: review_status={year_finding.get('review_status')}, "
        f"survey line={has_survey}, "
        f"{len(year_finding.get('uncertainties') or [])} open question(s)",
    )

    width = max(len(step["name"]) for step in journey.steps)
    for step in journey.steps:
        if step.get("skipped"):
            mark = "SKIP"
        elif step["passed"]:
            mark = "PASS"
        else:
            mark = "FAIL"
        print(f"[{mark}] {step['number']}. {step['name']:<{width}}  {step['detail']}")

    skipped = [step for step in journey.steps if step.get("skipped")]
    print()
    print(
        f"{len(journey.steps) - len(journey.failed)}/{len(journey.steps)} steps passed"
        + (f", {len(skipped)} not applicable offline" if skipped else "")
    )
    if journey.failed:
        print("FAILED: " + ", ".join(
            f"{step['number']}. {step['name']}" for step in journey.failed
        ))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
