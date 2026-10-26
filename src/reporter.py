"""Generate a readable, evidence-conscious investigation report."""


def render_report(results):
    lines = [
        "# Cross-Examiner Investigation Report",
        "",
        f"Records analyzed: {results.get('records_loaded', 0)}",
        f"Discrepancies identified: {len(results.get('findings', []))}",
        "",
        "> A discrepancy signals a question to investigate; it does not, by itself, establish which source is correct.",
        "",
    ]

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
        for source in sources:
            name = source.get("name", source.get("source", "Unnamed source"))
            url = source.get("url", "")
            lines.append(f"- [{name}]({url})" if url else f"- {name} (URL unavailable)")

        lines.extend([
            "",
            "### Limitations and next steps",
            "- Verify the original source documents and the definitions of each measure.",
            "- Check denominators, reporting periods, and estimation methodology before drawing conclusions.",
            "- The presence of a source link does not independently verify its contents.",
            "",
        ])

    return "\n".join(lines).rstrip() + "\n"


def write_report(results, output_path):
    from pathlib import Path
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(results), encoding="utf-8")
    return str(path)
