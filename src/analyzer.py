import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from src import source_registry

DATA = Path(__file__).resolve().parent.parent / "data" / "coverage_evidence.csv"

# Order in which the plan statuses of the individual iterations are folded
# into one status for the run.
STATUS_PRIORITY = ("used", "fallback", "rejected", "unavailable", "disabled")

# Which measurement kinds are preferred for the pair the finding is built
# on: the reconciled estimate and the administrative figure are the two
# published coverage numbers a planner has to choose between. A household
# survey is a third kind of number, not a third publication, so it is
# carried alongside them instead of competing with them.
PRIMARY_KINDS = ("reconciled_estimate", "administrative_reporting")

KIND_ORDER = (
    "reconciled_estimate",
    "administrative_reporting",
    "government_estimate",
    "household_survey",
    "synthetic",
)


def aggregate_status(statuses):
    """The most informative plan status of a whole run."""
    for status in STATUS_PRIORITY:
        if status in statuses:
            return status
    return "disabled"


def _kind_order(kind):
    try:
        return KIND_ORDER.index(kind)
    except ValueError:
        return len(KIND_ORDER)


def build_observation(row):
    """One reported number, with the lineage the registry declares for it.

    The semantic layer already carries the lineage, so it is used when it
    is there. The registry is the fallback, and the source of truth for
    the local path.
    """
    source = {"name": row.get("source", ""), "url": row.get("source_url", "")}
    measure = row.get("measure", "")
    origin = row.get("origin_id") or source_registry.origin_for(source, measure)
    origin_info = source_registry.origin_entry(origin) if origin else None
    try:
        value = float(row.get("value_percent"))
    except (TypeError, ValueError):
        value = None

    def flag(name, fallback=None):
        raw = row.get(name)
        if raw is None:
            return fallback
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("true", "1", "yes")

    return {
        "measure": measure,
        "value": value,
        "source": source,
        "notes": row.get("notes", ""),
        "origin": origin,
        "origin_label": row.get("origin_label") or (
            origin_info.get("label") if origin_info else None
        ),
        "measurement_kind": row.get("measurement_kind") or (
            origin_info.get("kind") if origin_info else None
        ),
        "metric_type": row.get("metric_type") or "",
        "source_id": row.get("source_id", ""),
        "is_derived": bool(flag("is_derived", False)),
        "is_synthetic": bool(flag(
            "is_synthetic", source_registry.is_synthetic(source)
        )),
        "independent_capable": bool(flag("independent_capable", False)),
        "verification_scope": row.get("verification_scope", ""),
        "lineage": source_registry.lineage(source, measure),
    }


def pick_primary(observations):
    """The two observations the discrepancy is about.

    The reconciled estimate and the administrative figure are the pair a
    planner is choosing between, so they are preferred; among the available
    pairs the widest gap is the one worth investigating. Every other
    observation is carried alongside as a corroborating line.
    """
    pairs = []
    for i in range(len(observations)):
        for j in range(i + 1, len(observations)):
            left = observations[i]
            right = observations[j]
            if left["value"] is None or right["value"] is None:
                continue
            kinds = {left["measurement_kind"], right["measurement_kind"]}
            preferred = kinds == set(PRIMARY_KINDS)
            pairs.append((preferred, abs(left["value"] - right["value"]), i, j))

    if not pairs:
        return None, None

    preferred_pairs = [pair for pair in pairs if pair[0]]
    pool = preferred_pairs or pairs
    best = max(pool, key=lambda pair: (pair[1], -pair[2], -pair[3]))
    left = observations[best[2]]
    right = observations[best[3]]

    # Keep the estimate on the A side and the other measure on the B side,
    # so the report keeps reading the way it always did.
    if _kind_order(right["measurement_kind"]) < _kind_order(left["measurement_kind"]):
        left, right = right, left
    return left, right


def _is_own_publication(observation):
    """True when the observation's source is where its series is published."""
    source = observation.get("source", {})
    origin = observation.get("origin")
    if not origin:
        return False
    entry = source_registry.entry_for(source)
    if not entry:
        return False
    return origin in (entry.get("own_publications") or [])


def dedupe_by_origin(observations):
    """One observation per series.

    A series can be published more than once - the WUENIC estimate is in
    the workbook, in the UNICEF data warehouse and in the World Bank.
    Those are one line of evidence, not three, so the series is counted
    once, with the publication that is the origin's own.
    """
    chosen = {}
    order = []

    for observation in observations:
        key = (observation.get("origin"), observation.get("measure"))
        if key not in chosen:
            chosen[key] = observation
            order.append(key)
            continue
        current = chosen[key]
        if (
            _is_own_publication(observation)
            and not _is_own_publication(current)
        ):
            chosen[key] = observation

    return [chosen[key] for key in order]


def analyze_records(records, threshold=5):
    groups = defaultdict(list)

    for row in records:
        # District programme returns are district-level, so they are
        # compared within a district, not across a whole country.
        key = (
            row["country"],
            row.get("district", "") or "",
            row["antigen"],
            str(row["year"]),
        )
        groups[key].append(row)

    findings = []
    for (country, district, antigen, year), rows in groups.items():
        if len(rows) < 2:
            continue

        observations = dedupe_by_origin([
            build_observation(row) for row in rows
        ])
        left, right = pick_primary(observations)
        if left is None:
            continue

        a = float(left["value"])
        b = float(right["value"])
        gap = abs(a - b)

        used = {id(left), id(right)}

        sources = []
        seen_urls = set()
        for observation in observations:
            url = observation["source"]["url"]
            key_url = url.split("?", 1)[0].rstrip("/")
            if key_url in seen_urls:
                continue
            seen_urls.add(key_url)
            sources.append(observation["source"])

        # Every reported number for this country, antigen and year, with
        # the lineage the registry declares for it. The two the finding is
        # built on are value_a and value_b; any further line is a
        # corroborating observation with its own field.
        observations_out = []
        next_field = 2
        for observation in observations:
            if observation is left:
                field = "value_a"
            elif observation is right:
                field = "value_b"
            else:
                field = f"value_{chr(ord('a') + next_field)}"
                next_field += 1
            observations_out.append(dict(observation, field=field))

        measure_sources = {
            observation["field"]: observation["source"]
            for observation in observations_out
        }

        findings.append({
            "country": country,
            "district": district,
            "antigen": antigen,
            "year": year,
            "measure_a": left["measure"],
            "value_a": a,
            "measure_b": right["measure"],
            "value_b": b,
            "gap_percentage_points": gap,
            "status": "REVIEW" if gap >= threshold else "WITHIN_THRESHOLD",
            "interpretation": (
                "Difference detected; investigate definitions, denominators, "
                "reporting quality and estimation methodology. This alone "
                "does not establish which figure is correct."
            ),
            "sources": sources,
            # Which source each measured value was taken from. The
            # verification scope depends on it: a value checked
            # against the document it came from is a self-consistency
            # check, not independent verification.
            "measure_sources": measure_sources,
            "observations": observations_out,
            # A finding built from generated records is not evidence. It is
            # tagged so nothing downstream can dispose of it.
            "synthetic": any(
                observation.get("is_synthetic") for observation in observations_out
            ),
            "corroborating_observations": [
                observation
                for observation in observations_out
                if observation["field"] not in ("value_a", "value_b")
            ],
        })
    return findings


def build_model_client(mode="auto"):
    """Build the model client. Returns (client, trace).

    A client is only returned when a model was requested. The trace records
    what was configured so the report can show it; the API key is never
    included.
    """
    trace = {
        "status": "disabled",
        "model": None,
        "base_url": None,
        "calls": 0,
        "max_calls": 0,
        "note": None,
        "proposals": [],
        "challenges": [],
    }

    if mode == "off":
        trace["note"] = "MODEL_DISABLED_BY_FLAG"
        return None, trace

    try:
        from src.model_client import MeterlessClient
    except Exception as exc:  # pragma: no cover - import guard
        trace["status"] = "unavailable"
        trace["note"] = f"MODEL_CLIENT_IMPORT_FAILED: {exc}"
        return None, trace

    try:
        client = MeterlessClient(model=None if mode == "auto" else mode)
    except Exception as exc:
        trace["status"] = "unavailable"
        trace["note"] = f"MODEL_CLIENT_SETUP_FAILED: {exc}"
        return None, trace

    trace["status"] = "enabled"
    trace["model"] = client.model
    trace["base_url"] = client.base_url
    config = client.config()
    trace["transport"] = config.get("transport")
    trace["transports_available"] = config.get("transports_available")
    return client, trace


def analyze(path=DATA, threshold=5):
    with open(path, newline="", encoding="utf-8") as f:
        return analyze_records(list(csv.DictReader(f)), threshold)


def main():
    parser = argparse.ArgumentParser(description="Cross-Examiner evidence analysis")
    parser.add_argument(
        "--source",
        choices=["csv", "zetaris"],
        default="csv",
        help="Evidence source (default: csv)",
    )
    parser.add_argument("--threshold", type=float, default=5)
    parser.add_argument("--remember", action="store_true", help="Persist findings in H-MEM")
    parser.add_argument("--question", help="The question to answer")
    parser.add_argument("--report", help="Write a Markdown report to this path")
    parser.add_argument(
        "--model",
        default="auto",
        help=(
            "Model runtime: 'auto' uses the configured model, 'off' disables "
            "the model, or pass a model id such as "
            "'nvidia/nemotron-3-ultra-550b-a55b'"
        ),
    )
    parser.add_argument(
        "--model-max-calls",
        type=int,
        default=12,
        help="Shared maximum number of model calls per investigation "
             "(default: 12)",
    )
    parser.add_argument(
        "--include-synthetic",
        action="store_true",
        help="Also read the generated district programme reports. They are "
             "labelled synthetic and never count as evidence.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=4,
        help="Maximum number of investigation iterations (default: 4)",
    )
    args = parser.parse_args()

    if args.source == "zetaris":
        from src.evidence_sources import load_records
        records, source_trace = load_records(
            prefer_zetaris=True, include_synthetic=args.include_synthetic
        )
    else:
        from src.evidence_sources import load_records
        records, source_trace = load_records(
            prefer_zetaris=False, include_synthetic=args.include_synthetic
        )

    findings = analyze_records(records, args.threshold)

    from src.arbiter import arbitrate
    from src.coordination import investigate
    from src.investigator import CallBudget
    from src.tracing import Trace

    remembered = []
    memory_context = None
    if args.question or findings:
        from src.memory_bridge import query

        # The store ranks every memory it holds, so the question alone is
        # not enough: the topics of the findings go into the query too,
        # and the recall filters by topic afterwards.
        topics = " ".join(sorted({
            f"{finding.get('country')} {finding.get('antigen')} "
            f"{finding.get('year')}"
            for finding in findings
        }))
        memory_context = query(f"{args.question or ''} {topics}".strip())

    trace = Trace(
        mode="sample" if args.source == "csv" else "live",
        question=args.question or "",
        # stdout carries the result of the run; the log goes to stderr and
        # to the file, so the result stays pipeable.
        echo="stderr",
    )
    for entry in source_trace:
        trace.event(
            "evidence.read",
            source_id=entry.get("source_id"),
            records=entry.get("records"),
            read_from=entry.get("read_from"),
            origin=entry.get("origin"),
            reason=entry.get("reason"),
        )

    # The deterministic baseline. The coordinator may adjudicate a different
    # final disposition on top of it, but this decision is never rewritten.
    decisions = [
        arbitrate(finding, args.threshold, memory_context)
        for finding in findings
    ]

    client, model_trace = build_model_client(args.model)
    model_trace["max_calls"] = args.model_max_calls
    budget = CallBudget(args.model_max_calls)

    outcome = investigate(
        question=args.question or "",
        findings=findings,
        decisions=decisions,
        client=client,
        budget=budget,
        threshold=args.threshold,
        memory_context=memory_context,
        max_iterations=args.max_iterations,
        trace=trace,
    )

    decisions = outcome["decisions"]
    revisions = outcome["revisions"]

    plan_statuses = [
        record.get("plan_status")
        for record in outcome["iterations"]
        if record.get("plan_status")
    ]
    plan_notes = [
        record.get("plan_note")
        for record in outcome["iterations"]
        if record.get("plan_note")
    ]

    if client is None:
        model_trace["status"] = "disabled"
    else:
        model_trace["status"] = aggregate_status(plan_statuses)
    if plan_notes:
        model_trace["note"] = plan_notes[0]
    elif client is None:
        model_trace["note"] = "MODEL_DISABLED_BY_FLAG"
    model_trace["calls"] = budget.calls
    model_trace["proposals"] = outcome["proposals"]
    model_trace["challenges"] = outcome["challenges"]
    model_trace["iterations"] = outcome["iterations"]
    if client is not None:
        model_trace["transport_used"] = getattr(client, "last_transport", None)

    dispositions = [
        decision.get("disposition")
        for decision in decisions
    ]

    if args.remember:
        from src.memory_bridge import remember
        from src.memory_policy import conflict_memory, question_memory
        from src.findings import finding_label

        uncertainties = outcome.get("uncertainties") or {}

        def store(content, source, refs, tags, kind):
            """Write one memory and put it on the record."""
            result = remember(content, source=source, refs=refs, tags=tags)
            remembered.append(result)
            trace.event(
                "memory.stored",
                kind=kind,
                source=source,
                ok=bool(result.get("ok")),
                error=result.get("error"),
            )
            return result

        for finding, decision in zip(findings, decisions):
            content = (
                f"Observed a {finding['gap_percentage_points']:.1f} percentage-point "
                f"gap between {finding['measure_a']} ({finding['value_a']:.1f}%) "
                f"and {finding['measure_b']} ({finding['value_b']:.1f}%) for "
                f"{finding['country']} {finding['antigen']} in {finding['year']}. "
                "This difference requires investigation and does not establish "
                "which figure is correct."
            )
            refs = [
                item["url"] for item in finding["sources"]
                if item.get("url")
            ]
            store(
                content,
                source=(
                    f"cross-examiner:finding:{finding['country']}:"
                    f"{finding['antigen']}:{finding['year']}"
                ),
                refs=refs,
                tags=[
                    finding["country"],
                    finding["antigen"],
                    finding["year"],
                    finding["status"],
                ],
                kind="finding",
            )
            if decision.get("disposition"):
                store(
                    (
                        f"Final disposition for {finding['country']} "
                        f"{finding['antigen']} {finding['year']}: "
                        f"{decision.get('disposition')} "
                        f"(deterministic decision {decision.get('decision')}). "
                        "A disposition does not establish which figure is "
                        "correct."
                    ),
                    source=(
                        f"cross-examiner:disposition:{finding['country']}:"
                        f"{finding['antigen']}:{finding['year']}"
                    ),
                    refs=refs,
                    tags=[
                        finding["country"],
                        finding["antigen"],
                        finding["year"],
                        "DISPOSITION",
                        str(decision.get("disposition")),
                    ],
                    kind="disposition",
                )
            for conflict in (decision.get("critic") or {}).get("conflicts") or []:
                store(
                    conflict_memory(finding, conflict),
                    source=(
                        f"cross-examiner:conflict:{finding['country']}:"
                        f"{finding['antigen']}:{finding['year']}"
                    ),
                    refs=refs,
                    tags=[
                        finding["country"],
                        finding["antigen"],
                        finding["year"],
                        "CONFLICT",
                        str(conflict.get("code")),
                    ],
                    kind="conflict",
                )

            open_items = uncertainties.get(finding_label(finding)) or []
            if open_items:
                store(
                    question_memory(finding, open_items),
                    source=(
                        f"cross-examiner:question:{finding['country']}:"
                        f"{finding['antigen']}:{finding['year']}"
                    ),
                    refs=refs,
                    tags=[
                        finding["country"],
                        finding["antigen"],
                        finding["year"],
                        "OPEN",
                    ],
                    kind="question",
                )

            revision = decision.get("revision") or {}
            if revision.get("action") and revision.get("action") != "NO_ADDITIONAL_EVIDENCE":
                store(
                    (
                        f"Revision for {finding['country']} {finding['antigen']} "
                        f"{finding['year']}: action={revision.get('action')}, "
                        f"outcome={revision.get('outcome')}, "
                        f"stop reason={revision.get('stop_reason')}."
                    ),
                    source=(
                        f"cross-examiner:revision:{finding['country']}:"
                        f"{finding['antigen']}:{finding['year']}"
                    ),
                    refs=refs,
                    tags=[
                        finding["country"],
                        finding["antigen"],
                        finding["year"],
                        "REVISION",
                        str(revision.get("action")),
                    ],
                    kind="revision",
                )

        for challenge in outcome["challenges"]:
            if challenge.get("source") != "model":
                continue
            challenge_refs = [
                item["url"]
                for source in findings
                if (
                    str(source.get("country")) == str(challenge.get("country"))
                    and str(source.get("antigen")) == str(challenge.get("antigen"))
                    and str(source.get("year")) == str(challenge.get("year"))
                )
                for item in source.get("sources", [])
                if item.get("url")
            ]
            store(
                (
                    f"Model challenge for {challenge.get('country')} "
                    f"{challenge.get('antigen')} {challenge.get('year')}: "
                    + " ".join(challenge.get("challenges") or [])[:600]
                ),
                source=(
                    f"cross-examiner:challenge:{challenge.get('country')}:"
                    f"{challenge.get('antigen')}:{challenge.get('year')}"
                ),
                refs=challenge_refs,
                tags=[
                    str(challenge.get("country")),
                    str(challenge.get("antigen")),
                    str(challenge.get("year")),
                    "CHALLENGE",
                ],
                kind="challenge",
            )

    trace.close(
        findings=len(findings),
        stop_reason=outcome.get("stop_reason"),
    )

    result = {
        "source": args.source,
        "run_id": trace.run_id,
        "trace_file": str(trace.path),
        "evidence_trace": source_trace,
        "records_loaded": len(records),
        "threshold_percentage_points": args.threshold,
        "question": args.question,
        "memory_context": memory_context,
        "findings": findings,
        "decisions": decisions,
        "dispositions": dispositions,
        "revisions": revisions,
        "iterations": outcome["iterations"],
        "evidence_ledger": outcome["ledger"],
        "executed_actions": outcome["executed_actions"],
        "closing": outcome["closing"],
        "stop_reason": outcome["stop_reason"],
        "stop_detail": outcome["stop_detail"],
        "uncertainties": outcome["uncertainties"],
        "model": model_trace,
        "remembered": remembered,
    }

    if args.report:
        from src.reporter import write_report
        write_report(result, args.report)
        import sys; print(f"Markdown report written to {args.report}", file=sys.stderr)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
