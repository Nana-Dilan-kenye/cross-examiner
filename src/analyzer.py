import csv
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "cameroon_mcv1_evidence.csv"

def analyze(path=DATA, threshold=5):
    groups = defaultdict(dict)

    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["country"], row["antigen"], row["year"])
            groups[key][row["measure"]] = row

    findings = []
    for (country, antigen, year), measures in groups.items():
        if len(measures) < 2:
            continue

        rows = list(measures.values())
        for i, left in enumerate(rows):
            for right in rows[i + 1:]:
                a, b = float(left["value_percent"]), float(right["value_percent"])
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
                        "reporting quality and estimate methodology. This alone does "
                        "not establish which figure is correct."
                    ),
                })
    return findings

if __name__ == "__main__":
    import json
    print(json.dumps(analyze(), indent=2))
