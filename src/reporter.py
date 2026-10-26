"""Generate a readable, evidence-conscious investigation report."""


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
            f"- **Observation A:** {finding.get('measure_a')} — {finding.get('value_a')}%",
            f"- **Observation B:** {finding.get('measure_b')} — {finding.get('value_b')}%",
            f"- **Absolute gap:** {finding.get('gap_percentage_points')} percentage points",
            f"- **Decision:** {decision.get('decision', 'UNASSESSED')}",
            f"- **Reason:** {decision.get('reason', 'No decision supplied.')}",
            "",
            "### Sources",
        ])

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
                    f"  - Verification status: {check.get('status', 'UNKNOWN')}"
                )

                if check.get("table_page") is not None:
                    lines.append(
                        f"  - Matching table page: {check['table_page']}"
                    )

                for limitation in check.get("limitations", []):
                    lines.append(f"  - Limitation: {limitation}")

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