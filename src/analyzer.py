import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "cameroon_mcv1_evidence.csv"


def analyze_records(records, threshold=5):
    groups = defaultdict(dict)

    for row in records:
        key = (row["country"], row["antigen"], str(row["year"]))
        groups[key][row["measure"]] = row

    findings = []
    for (country, antigen, year), measures in groups.items():
        if len(measures) < 2:
            continue

        rows = list(measures.values())
        for i, left in enumerate(rows):
            for right in rows[i + 1:]:
                a = float(left["value_percent"])
                b = float(right["value_percent"])
                gap = abs(a - b)

                findings.append({
                    "country": country,
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
                    "sources": [
                        {
                            "name": left.get("source", ""),
                            "url": left.get("source_url", ""),
                        },
                        {
                            "name": right.get("source", ""),
                            "url": right.get("source_url", ""),
                        },
                    ],
                })

    return findings


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
    parser.add_argument(
    "--question",
    help="The question to answer",
    )
    parser.add_argument("--report", help="Write a Markdown report to this path")
    args = parser.parse_args()

    if args.source == "zetaris":
        from src.zetaris_source import load_records
        records = load_records()
    else:
        with open(DATA, newline="", encoding="utf-8") as f:
            records = list(csv.DictReader(f))

    findings = analyze_records(records, args.threshold)
    from src.arbiter import arbitrate
    # decisions = [arbitrate(finding, args.threshold) for finding in findings]
    remembered = []
    memory_context = None
    if args.question:
        from src.memory_bridge import query
        memory_context = query(args.question)
    decisions = [
        arbitrate(finding, args.threshold, memory_context)
        for finding in findings
    ]
    if args.remember:
        from src.memory_bridge import remember
        for finding in findings:
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
            memory_context = None
            if args.question:
                from src.memory_bridge import query
                memory_context = query(args.question)
            result = remember(
                content,
                source=(
                    f"cross-examiner:{finding['country']}:"
                    f"{finding['antigen']}:{finding['year']}"
                ),
                refs=refs,
                tags=[
                    finding["country"],
                    finding["antigen"],
                    finding["year"],
                    finding["status"],
                ],
            )
            remembered.append(result)

    result = {
        "source": args.source,
        "records_loaded": len(records),
        "threshold_percentage_points": args.threshold,
        "question": args.question,
        "memory_context": memory_context,
        "findings": findings,
        "decisions": decisions,
        "remembered": remembered,
    }

    if args.report:
        from src.reporter import write_report
        write_report(result, args.report)
        import sys; print(f"Markdown report written to {args.report}", file=sys.stderr)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
