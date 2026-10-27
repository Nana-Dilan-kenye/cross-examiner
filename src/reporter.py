"""Generate a readable, evidence-conscious investigation report."""

from src.findings import finding_label


STATUS_QUALIFIERS = {
    "EXTRACT_CONSISTENT": (
        "EXTRACT_CONSISTENT (self-consistency check against the local WUENIC "
        "workbook extract, which is where the claimed value came from; this is "
        "not independent verification)"
    ),
    "EXTRACT_CONFLICT": (
        "EXTRACT_CONFLICT (the claimed value disagrees with the local WUENIC "
        "workbook extract; this is a self-consistency check, not independent "
        "verification)"
    ),
    "SOURCE_DOCUMENT_RETRIEVED": (
        "SOURCE_DOCUMENT_RETRIEVED (the document was retrieved so it can be "
        "inspected; its contents and values are not verified)"
    ),
}


def status_label(status):
    """Human label for a source-check status."""
    return STATUS_QUALIFIERS.get(status, status)


def _lineage_rows(findings):
    """One row per reported number, with the lineage the registry declares."""
    rows = []
    seen = set()
    for finding in findings:
        for observation in finding.get("observations") or []:
            lineage = observation.get("lineage") or {}
            key = (
                observation.get("measure"),
                observation.get("value"),
                lineage.get("source_id"),
            )
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "measure": observation.get("measure"),
                "value": observation.get("value"),
                "source_name": lineage.get("source_name")
                or observation.get("measure"),
                "origin": observation.get("origin")
                or lineage.get("origin"),
                "origin_label": observation.get("origin_label")
                or lineage.get("origin_label"),
                "derived_from": lineage.get("derived_from"),
                "source_type": lineage.get("source_type"),
                "is_synthetic": bool(observation.get("is_synthetic")),
            })
    return rows


def render_report(results):
    lines = [
        "# Cross-Examiner Investigation Report",
        "",
        f"Question: {results.get('question') or 'Not specified'}",
        f"Evidence source: {results.get('source', 'Unknown')}",
        f"Records analyzed: {results.get('records_loaded', 0)}",
        f"Discrepancies identified: {len(results.get('findings', []))}",
        "",
        "> A discrepancy signals a question to investigate; it does not, by itself, establish which source is correct.",
        "",
    ]

    lineage_rows = _lineage_rows(results.get("findings") or [])
    synthetic_rows = [
        row for row in lineage_rows if row.get("is_synthetic")
    ]

    evidence_trace = results.get("evidence_trace") or []
    if evidence_trace:
        lines.extend([
            "## Where the evidence came from",
            "",
        ])
        for entry in evidence_trace:
            lines.append(
                f"- **{entry.get('source_id')}**: {entry.get('records')} "
                f"records from {entry.get('read_from')}"
                + (
                    f" ({entry.get('origin')})"
                    if entry.get("origin") else ""
                )
                + (
                    f" — {entry.get('reason')}"
                    if entry.get("reason") else ""
                )
            )
        lines.append("")

    if synthetic_rows:
        lines.extend([
            "## SYNTHETIC DATA",
            "",
            "> This run reads synthetic records. They are generated, not "
            "observed, and they never count as evidence.",
            "",
        ])
        for row in synthetic_rows:
            lines.append(
                f"- {row.get('measure')} ({row.get('value')}%) — "
                f"{row.get('source_name')}"
            )
        lines.append("")

    if lineage_rows:
        lines.extend([
            "## Sources and their lineage",
            "",
            "> Every reported number comes from one of these sources. A "
            "source that republishes another series is counted once with "
            "the series it republishes, so it can never confirm the "
            "numbers it was derived from.",
            "",
            "| Measure | Source | Series it comes from | Republishes | "
            "Type |",
            "|---|---|---|---|---|",
        ])
        for row in lineage_rows:
            lines.append(
                f"| {row.get('measure')} ({row.get('value')}%) "
                f"| {row.get('source_name')} "
                f"| {row.get('origin_label') or 'not declared'}"
                + (f" (`{row.get('origin')}`)" if row.get("origin") else "")
                + f" "
                f"| {row.get('derived_from') or '-'} "
                f"| {row.get('source_type')} |"
            )
        lines.append("")

    # Memory is context from previous investigations, not verified evidence.
    memory_context = results.get("memory_context") or {}
    memories = memory_context.get("memories", [])

    lines.extend(["## Relevant Prior Memories", ""])

    if memories:
        lines.append(
            "> These are retrieved records from previous investigations. "
            "They provide context but are not independent verification."
        )
        lines.append("")

        for memory in memories:
            content = memory.get("content", "No memory content available.")
            memory_id = memory.get("id", "unknown")
            confidence = memory.get("confidence")

            lines.append(f"- **{memory_id}**: {content}")
            if confidence is not None:
                lines.append(f"  - Stored confidence: {confidence}")
    else:
        lines.append("No relevant prior memories were retrieved.")

    if memory_context.get("available") is False:
        lines.append("")
        lines.append(
            f"> Memory was unavailable for this run: "
            f"{memory_context.get('error', 'unknown reason')}"
        )

    lines.append("")
    model = results.get("model") or {}
    lines.extend(["## Model-driven investigation", ""])
    if model:
        lines.append(
            "> The model proposes which evidence to gather and may challenge a "
            "claim. Its output is advisory: trusted Python code fetches the "
            "evidence, validates the numbers, and makes the decision."
        )
        lines.append("")
        lines.append(
            f"- Model runtime: `{model.get('model') or 'not configured'}` "
            f"at `{model.get('base_url') or 'n/a'}`"
        )
        if model.get("transport"):
            lines.append(
                f"- Transport: {model.get('transport')} "
                f"(used: {model.get('transport_used') or 'none'})"
            )
        lines.append(
            f"- Model calls made: {model.get('calls', 0)} "
            f"(budget {model.get('max_calls', 0)})"
        )
        lines.append(f"- Model status: {model.get('status', 'unknown')}")
        if model.get("note"):
            lines.append(f"- Note: {model['note']}")

        proposals = model.get("proposals") or []
        if proposals:
            lines.append("")
            lines.append("### Proposed evidence actions")
            for proposal in proposals:
                action = proposal.get("action")
                origin = proposal.get("source", "deterministic")
                line = (
                    f"- **{proposal.get('country')} {proposal.get('antigen')} "
                    f"({proposal.get('year')})**: {action} "
                    f"(proposed by: {origin})"
                )
                if proposal.get("reason"):
                    line += f" — {proposal['reason']}"
                if proposal.get("fallback_reason"):
                    line += f" [fallback: {proposal['fallback_reason']}]"
                lines.append(line)

        challenges = model.get("challenges") or []
        if challenges:
            lines.append("")
            lines.append("### Model challenges")
            for challenge in challenges:
                lines.append(
                    f"- **{challenge.get('country')} {challenge.get('antigen')} "
                    f"({challenge.get('year')})** "
                    f"(challenged by: {challenge.get('source', 'deterministic')}):"
                )
                for item in challenge.get("challenges") or []:
                    lines.append(f"  - {item}")
                for item in challenge.get("missing_support") or []:
                    lines.append(f"  - Missing support: {item}")
                if challenge.get("fallback_reason"):
                    lines.append(
                        f"  - Fallback reason: {challenge['fallback_reason']}"
                    )
    else:
        lines.append("No model runtime was used for this run.")

    lines.append("")
    revisions = results.get("revisions") or []
    lines.extend(["## Revision loop", ""])
    if revisions:
        lines.append(
            "> After the critic ran, the investigator requested extra evidence "
            "or stopped. This is a recorded decision, not a verdict about which "
            "coverage figure is correct."
        )
        lines.append("")
        for revision in revisions:
            year = revision.get("year", "unknown year")
            country = revision.get("country", "")
            antigen = revision.get("antigen", "")
            lines.append(
                f"- **{country} {antigen} ({year})**: "
                f"action={revision.get('action')}; "
                f"outcome={revision.get('outcome')}; "
                f"stop reason={revision.get('stop_reason')}"
            )
    else:
        lines.append("No revision step was recorded.")
    lines.append("")

    iterations = results.get("iterations") or []
    lines.extend(["## Investigation trace", ""])
    if iterations:
        lines.append(
            "> One iteration is one pass of the loop: the coordinator planned "
            "the next step, the trusted code executed it, the critic "
            "challenged the result and the arbiter adjudicated it."
        )
        lines.append("")
        for record in iterations:
            lines.append(f"### Iteration {record.get('iteration')}")
            lines.append("")
            active = record.get("active_findings") or []
            if active:
                lines.append(f"- Active findings: {', '.join(active)}")
            for step in record.get("proposed") or []:
                lines.append(
                    f"- Proposed for {step.get('finding')}: "
                    f"{step.get('action')} (proposed by: {step.get('source')}"
                    + (
                        f", {step.get('fallback_reason')}"
                        if step.get("fallback_reason") else ""
                    )
                    + ")"
                )
            for step in record.get("next_steps") or []:
                lines.append(
                    f"- Next step for {step.get('finding')}: "
                    f"{step.get('action')} (chosen by: {step.get('source')}) "
                    f"— {step.get('reason')}"
                )
            for action in record.get("executed") or []:
                lines.append(
                    f"- Executed: {action.get('action')} for "
                    f"{action.get('finding')} — outcome="
                    f"{action.get('outcome')}, stop reason="
                    f"{action.get('stop_reason')}"
                )
            for rejected in record.get("rejected_proposals") or []:
                asked = rejected.get("rejected_action") or rejected.get("action")
                lines.append(
                    f"- Rejected proposal: the model asked for {asked} for "
                    f"{rejected.get('finding')} — "
                    f"{rejected.get('fallback_reason')}"
                )
            for challenge in record.get("challenges") or []:
                reused = (
                    " (carried forward: the decision did not change)"
                    if challenge.get("reused") else ""
                )
                lines.append(
                    f"- Challenge for {challenge.get('finding')} "
                    f"(raised by: {challenge.get('source')}){reused}: "
                    + "; ".join(challenge.get("challenges") or [])
                )
            for adjudication in record.get("adjudications") or []:
                outcome = (
                    "accepted" if adjudication.get("accepted") else "rejected"
                )
                lines.append(
                    f"- Adjudication for {adjudication.get('finding')}: "
                    f"{adjudication.get('baseline_disposition')} → "
                    f"{adjudication.get('final_disposition')} "
                    f"(proposed {adjudication.get('proposed_verdict') or 'none'}; "
                    f"{outcome}: {adjudication.get('validation_reason')})"
                )
            if record.get("stop_reason"):
                lines.append(
                    f"- Iteration stop reason: {record.get('stop_reason')}"
                )
            lines.append("")
    else:
        lines.append("No investigation iterations were recorded.")
        lines.append("")

    ledger = results.get("evidence_ledger") or []
    lines.extend(["## Evidence ledger", ""])
    if ledger:
        lines.append(
            "> Every row is an item the trusted code registered. The id is "
            "what a model proposal is checked against, so a citation that "
            "names an item that was never gathered is rejected."
        )
        lines.append("")
        for item in ledger:
            lines.append(
                f"- **{item.get('evidence_id')}**: {item.get('name')} "
                f"— status={item.get('status')}, scope={item.get('scope')}"
            )
            if item.get("url"):
                lines.append(f"  - {item['url']}")
    else:
        lines.append("No evidence was registered.")
    lines.append("")

    if results.get("stop_reason"):
        lines.extend(["## Stopping reason", ""])
        lines.append(f"- Investigation stopped: **{results['stop_reason']}**")
        if results.get("stop_detail"):
            lines.append(f"- {results['stop_detail']}")

        closing = results.get("closing") or {}
        unresolved = [
            label for label, item in closing.items()
            if item.get("disposition") not in ("ACCEPT", "REJECT")
        ]
        if closing:
            lines.append("- Findings still open: "
                         + (", ".join(unresolved) if unresolved else "none"))
            for label, item in closing.items():
                lines.append(
                    f"  - {label}: {item.get('cause')} — {item.get('reason')}"
                )
        lines.append("")

    decisions = results.get("decisions", [])

    if not results.get("findings"):
        lines.append("No discrepancies met the configured threshold.")
        return "\n".join(lines) + "\n"

    for index, finding in enumerate(results["findings"], start=1):
        decision = decisions[index - 1] if index <= len(decisions) else {}

        lines.extend([
            f"## Finding {index}: {finding.get('country', 'Unknown')} "
            f"{finding.get('antigen', '')} ({finding.get('year', 'Unknown')})",
            "",
        ])

        if finding.get("synthetic"):
            lines.extend([
                "**SYNTHETIC RECORD** — this finding is built from generated "
                "data. It is here to exercise the checks and it is never "
                "evidence.",
                "",
            ])

        lines.extend([
            f"- **Observation A:** {finding.get('measure_a')} — {finding.get('value_a')}%",
            f"- **Observation B:** {finding.get('measure_b')} — {finding.get('value_b')}%",
            f"- **Absolute gap:** {finding.get('gap_percentage_points')} percentage points",
            f"- **Deterministic decision:** {decision.get('decision', 'UNASSESSED')}",
            f"- **Final disposition:** {decision.get('disposition', 'UNASSESSED')}",
            f"- **Reason:** {decision.get('reason', 'No decision supplied.')}",
            "",
        ])

        corroborating = finding.get("corroborating_observations") or []
        if corroborating:
            lines.extend([
                "",
                "### Other reported numbers for this country and year",
                "",
                "> These are not a third publication of the same series. Each "
                "one comes from a different kind of measurement, so it says "
                "something the two published figures cannot.",
                "",
            ])
            for observation in corroborating:
                lines.append(
                    f"- **{observation.get('measure')}**: "
                    f"{observation.get('value')}% "
                    f"({observation.get('origin_label') or 'origin not declared'})"
                )
                if observation.get("notes"):
                    lines.append(f"  - Note: {observation['notes']}")
            lines.append("")

        recommendation = decision.get("recommendation")
        conflicts = (decision.get("critic") or {}).get("conflicts") or []
        if conflicts:
            lines.extend([
                "",
                "### Conflicts between lines that do not share an upstream",
                "",
            ])
            for conflict in conflicts:
                lines.append(
                    f"- **{conflict.get('code')}**: "
                    f"{conflict.get('measure_a')} {conflict.get('value_a')}% "
                    f"against {conflict.get('measure_b')} "
                    f"{conflict.get('value_b')}% — "
                    f"{conflict.get('gap_percentage_points')} percentage points"
                )
                lines.append(f"  - {conflict.get('note')}")
            lines.append("")

        recommendation = decision.get("recommendation")
        if recommendation:
            lines.extend([
                "",
                "### Recommendation for the coverage level",
                "",
                f"- **Use for the coverage level:** "
                f"{recommendation.get('recommended_measure')} — "
                f"{recommendation.get('recommended_value')}%",
                f"- **Do not use as the coverage level:** "
                f"{recommendation.get('not_recommended_measure')} — "
                f"{recommendation.get('not_recommended_value')}%",
                f"- **Difference:** "
                f"{recommendation.get('gap_percentage_points')} percentage points",
                f"- **Why:** {recommendation.get('basis')}",
            ])
            for caveat in recommendation.get("caveats") or []:
                lines.append(f"- Caveat: {caveat}")
            lines.append("")

        adjudication = decision.get("adjudication") or {}
        uncertainties = (results.get("uncertainties") or {}).get(
            finding_label(finding)
        )

        lines.extend(["### Sources", ""])
        sources = finding.get("sources", [])
        if not sources:
            lines.append("- No source records attached.")

        source_checks = (
            decision.get("critic", {}).get("source_checks", [])
        )

        for source in sources:
            name = source.get("name", source.get("source", "Unnamed source"))
            url = source.get("url", "")

            check = next(
                (
                    item for item in source_checks
                    if item.get("name") == name
                ),
                None,
            )

            lines.append(
                f"- [{name}]({url})" if url else f"- {name} (URL unavailable)"
            )

            if not url:
                lines.append("  - Verification status: MISSING URL")
            elif not check:
                lines.append("  - Verification status: NOT CHECKED")
            else:
                lines.append(
                    f"  - Verification status: "
                    f"{status_label(check.get('status', 'UNKNOWN'))}"
                )

                if check.get("table_page") is not None:
                    lines.append(
                        f"  - Matching table page: {check['table_page']}"
                    )

                for matched in check.get("matched_values", []):
                    if matched.get("revision_difference"):
                        lines.append(
                            f"  - {matched.get('measure')}: "
                            f"claim={matched.get('expected')}%, "
                            f"table={matched.get('table_value')}% — "
                            "revision difference, not a conflict"
                        )
                        continue
                    lines.append(
                        f"  - {matched.get('measure')}: "
                        f"claim={matched.get('expected')}%, "
                        f"table={matched.get('table_value')}%, "
                        f"matched={'yes' if matched.get('found_in_expected_year_row') else 'no'}"
                    )

                document = check.get("document")
                if document:
                    mentions = document.get("mentions") or {}
                    lines.append(
                        f"  - Retrieved document: "
                        f"{document.get('content_type') or 'unknown type'}, "
                        f"{document.get('bytes')} bytes"
                    )
                    if mentions:
                        lines.append(
                            f"  - Document mentions antigen: "
                            f"{bool(mentions.get('antigen'))}; country: "
                            f"{bool(mentions.get('country'))}"
                        )

                for limitation in check.get("limitations", []):
                    lines.append(f"  - Limitation: {limitation}")

        if adjudication:
            outcome = "accepted" if adjudication.get("accepted") else "rejected"
            lines.extend([
                "",
                "### Adjudication",
                f"- **Baseline disposition:** {adjudication.get('baseline_disposition')}",
                f"- **Final disposition:** {adjudication.get('final_disposition')}",
                f"- **Proposed verdict:** "
                f"{adjudication.get('proposed_verdict') or 'none'}",
                f"- **Proposal {outcome}:** {adjudication.get('validation_reason')}",
            ])
            if adjudication.get("reason"):
                lines.append(
                    f"- **Proposal reason:** {adjudication['reason']}"
                )
            if adjudication.get("citations"):
                lines.append(
                    f"- **Cited evidence:** "
                    f"{', '.join(str(item) for item in adjudication['citations'])}"
                )
            if decision.get("disposition_meaning"):
                lines.append(
                    f"- **What this means:** {decision['disposition_meaning']}"
                )
            lines.append("")

        if uncertainties:
            resolved = decision.get("disposition") in ("ACCEPT", "REJECT")
            lines.extend([
                "### Standing caveats" if resolved else "### Unresolved uncertainty",
                "",
            ])
            if not resolved:
                lines.append(
                    "These are the questions the evidence still leaves open, "
                    "so the finding is not resolved:"
                )
                lines.append("")
            for item in uncertainties:
                lines.append(f"- {item}")
            lines.append("")

        lines.extend([
            "",
            "### Limitations and next steps",
            "- Verify the original source documents and definitions of each measure.",
            "- Check denominators, reporting periods, and estimation methodology.",
            "- A source link does not independently verify its contents.",
            "- Do not treat a remembered claim as confirmation of a current finding.",
            "",
        ])

    return "\n".join(lines).rstrip() + "\n"


def write_report(results, output_path):
    from pathlib import Path

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(results), encoding="utf-8")
    return str(path)