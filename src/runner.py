"""One investigation, run.

The command line and the HTTP API both come through here, so what a
judge sees over HTTP is exactly what ``python3 -m src.analyzer`` does.

The run returns everything that was gathered: the findings with their
lineage, the evidence ledger, what was retrieved from memory, what was
written back to it, and the trace file.
"""

import os

from src.tracing import Trace

# The default mode: read the deployed semantic layer when it is
# reachable, and the local files when it is not.
SOURCE_CHOICES = ("auto", "zetaris", "local")


def sample_mode():
    """True when the project runs without live credentials.

    In sample mode nothing reaches the network: the local files answer
    and the memory store is not touched.
    """
    value = str(os.environ.get("SAMPLE_MODE", "")).strip().lower()
    return value in ("1", "true", "yes", "on")


def confidence_for(decision):
    """How much the evidence supports the finding.

    The scale is deliberately coarse and it is never "the true coverage":
    it says how well the finding is corroborated.

    ``high``
        An independent source confirmed both published values.
    ``moderate``
        An independent measurement contradicts one of them, so the finding
        is characterised but not settled.
    ``low``
        The numbers were only checked against their own publications.
    ``none``
        The finding was withheld.
    """
    from src.evidence_ledger import (
        SCOPE_INDEPENDENT,
        SCOPE_INDEPENDENT_MEASUREMENT,
    )

    disposition = str(decision.get("disposition") or "").upper()
    if disposition == "ABSTAIN":
        return "none"

    critic = decision.get("critic") or {}
    scopes = {
        check.get("verification_scope")
        for check in critic.get("source_checks") or []
    }
    scopes.update(
        observation.get("verification_scope")
        for observation in critic.get("observations") or []
    )
    if SCOPE_INDEPENDENT in scopes:
        return "high"
    if SCOPE_INDEPENDENT_MEASUREMENT in scopes:
        return "moderate"
    return "low"


def _filter_findings(findings, country=None, antigen=None, year=None):
    """Keep the findings the caller asked about."""
    selected = findings
    if country:
        selected = [
            item for item in selected
            if str(item.get("country", "")).casefold() == str(country).casefold()
        ]
    if antigen:
        selected = [
            item for item in selected
            if str(item.get("antigen", "")).casefold() == str(antigen).casefold()
        ]
    if year:
        selected = [
            item for item in selected
            if str(item.get("year", "")) == str(year)
        ]
    return selected


def run_investigation(
    question=None,
    country=None,
    antigen=None,
    year=None,
    source="auto",
    model="off",
    use_memory=True,
    remember=False,
    threshold=5,
    max_iterations=4,
    model_max_calls=12,
    include_synthetic=False,
    trace=None,
    echo="stderr",
):
    """Run one investigation and return everything about it."""
    from src.analyzer import analyze_records, build_model_client
    from src.arbiter import arbitrate
    from src.coordination import investigate
    from src.evidence_sources import load_records
    from src.investigator import CallBudget

    if source not in SOURCE_CHOICES:
        raise ValueError(
            f"unknown source {source!r}; use one of {', '.join(SOURCE_CHOICES)}"
        )

    # Sample mode never reaches the network, whatever the caller asked
    # for.
    if sample_mode():
        source = "local"
    prefer_zetaris = source in ("auto", "zetaris")
    records, source_trace = load_records(
        prefer_zetaris=prefer_zetaris,
        include_synthetic=include_synthetic,
    )
    if source == "auto" and not any(
        entry.get("origin") == "zetaris_usl" for entry in source_trace
    ):
        # The layer was not reachable, so the local files answered.
        source = "local"

    findings = analyze_records(records, threshold)
    findings = _filter_findings(findings, country, antigen, year)

    own_trace = trace is None
    if trace is None:
        trace = Trace(
            mode="sample" if source == "local" else "live",
            question=question or "",
            # A service logs to stdout; a one-shot command keeps stdout for
            # its result and logs to stderr.
            echo=echo,
        )
    trace.event(
        "evidence.read",
        records=len(records),
        source=source,
        trace=source_trace,
    )

    memory_context = None
    if use_memory and not sample_mode() and (question or findings):
        from src.memory_bridge import query

        topics = " ".join(sorted({
            f"{finding.get('country')} {finding.get('antigen')} "
            f"{finding.get('year')}"
            for finding in findings
        }))
        memory_context = query(f"{question or ''} {topics}".strip())
        trace.event(
            "memory.retrieved",
            available=bool((memory_context or {}).get("available")),
            memories=len((memory_context or {}).get("memories") or []),
            error=(memory_context or {}).get("error"),
        )

    decisions = [
        arbitrate(finding, threshold, memory_context)
        for finding in findings
    ]

    client, model_trace = build_model_client(model)
    model_trace["max_calls"] = model_max_calls
    budget = CallBudget(model_max_calls)

    outcome = investigate(
        question=question or "",
        findings=findings,
        decisions=decisions,
        client=client,
        budget=budget,
        threshold=threshold,
        memory_context=memory_context,
        max_iterations=max_iterations,
        trace=trace,
    )

    decisions = outcome["decisions"]

    # The generated district returns are checked by their own rules. They
    # never enter the findings: they are generated, so they can never
    # substantiate a real-world conclusion.
    programme_checks = []
    if include_synthetic:
        from src.programme_checks import check_records, load_reports
        programme_checks = check_records(load_reports())

    remembered = []
    if remember:
        remembered = _remember(findings, decisions, outcome, trace)

    if own_trace:
        trace.close(
            findings=len(findings),
            stop_reason=outcome.get("stop_reason"),
        )

    return {
        "run_id": trace.run_id,
        "trace_file": str(trace.path),
        "source": source,
        "records_loaded": len(records),
        "threshold_percentage_points": threshold,
        "question": question,
        "findings": findings,
        "decisions": decisions,
        "dispositions": [
            decision.get("disposition") for decision in decisions
        ],
        "confidence": [
            confidence_for(decision) for decision in decisions
        ],
        "evidence_trace": source_trace,
        "evidence_ledger": outcome["ledger"],
        "executed_actions": outcome["executed_actions"],
        "iterations": outcome["iterations"],
        "revisions": outcome["revisions"],
        "uncertainties": outcome["uncertainties"],
        "stop_reason": outcome["stop_reason"],
        "stop_detail": outcome["stop_detail"],
        "model": model_trace,
        "memory_context": {
            "available": bool((memory_context or {}).get("available")),
            "memories": len((memory_context or {}).get("memories") or []),
            "error": (memory_context or {}).get("error"),
        },
        "remembered": remembered,
        "programme_checks": programme_checks,
    }


def _remember(findings, decisions, outcome, trace):
    """Write what this run learned into the memory store."""
    from src.findings import finding_label
    from src.memory_bridge import remember
    from src.memory_policy import conflict_memory, question_memory

    uncertainties = outcome.get("uncertainties") or {}
    remembered = []

    def store(content, source, refs, tags, kind):
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
        refs = [
            item["url"] for item in finding.get("sources", [])
            if item.get("url")
        ]
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
    return remembered
