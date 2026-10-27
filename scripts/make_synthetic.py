#!/usr/bin/env python3
"""Generate the synthetic district programme reports.

The reports stand in for a fictional organisation's internal district
returns. They exist so the agent's checks can be measured: every planted
contradiction has a known answer, and there are as many clean records as
there are planted ones, so a false positive on a clean record is visible.

Everything this writes is synthetic. The rows carry ``is_synthetic=true``
and the source label ``SYNTHETIC district programme reports``; the answer
key is written separately and only the evaluation harness reads it.

    python3 scripts/make_synthetic.py

Regenerating with the same seed produces the same file.
"""

import csv
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "synthetic_programme_reports.csv"
DATABASE = ROOT / "data" / "synthetic_programme_reports.db"
ANSWER_KEY = ROOT / "eval" / "answer_key.json"

SEED = 20261026
PROGRAMME = "Meridian Immunisation Programme"
COUNTRY = "Meridia"
SOURCE_ID = "synthetic_programme_reports"
SOURCE_NAME = "SYNTHETIC district programme reports"
SOURCE_REF = "synthetic://meridian-immunisation-programme/district-returns"

DISTRICTS = [
    "North Ridge", "South Ridge", "East Basin", "West Basin",
    "Central Plain", "Lakeside", "Highlands", "Delta",
    "Coast West", "Coast East", "Foothills", "Mesa Verde",
]
ANTIGENS = ["MCV1", "DTP3", "DTP1"]
YEARS = [2019, 2020, 2021, 2022, 2023]

FIELDS = [
    "programme", "district", "country", "antigen", "year", "measure",
    "value_percent", "numerator", "denominator", "source_id", "source_ref",
    "is_synthetic", "notes",
]


class Random:
    """A tiny deterministic generator, so the file never depends on the
    Python version's random implementation."""

    def __init__(self, seed):
        self.state = seed & 0xFFFFFFFFFFFF

    def next(self):
        # A xorshift step: same sequence on every platform and version.
        x = self.state
        x ^= (x << 13) & 0xFFFFFFFFFFFF
        x ^= x >> 7
        x ^= (x << 17) & 0xFFFFFFFFFFFF
        self.state = x
        return x

    def below(self, limit):
        return self.next() % limit

    def between(self, low, high):
        return low + self.below(high - low + 1)

    def chance(self, percent):
        return self.below(100) < percent


def baseline(rng, district, antigen, year):
    """A smooth, plausible administrative coverage value.

    The series rises by at least one point a year, so two neighbouring
    years never carry the same number. That is what makes a repeated value
    a signal rather than a coincidence.
    """
    base = 52 + (DISTRICTS.index(district) * 3) % 24
    drift = (year - YEARS[0]) * 3
    wobble = rng.between(-1, 1)
    value = base + drift + wobble
    if antigen == "DTP1":
        value += 6
    if antigen == "DTP3":
        value += 2
    return max(45, min(97, value))


def build_rows():
    """The generated records and the planted contradictions."""
    rng = Random(SEED)
    records = []
    planted = []
    controls = []

    def target_of(district):
        return 1000 * (DISTRICTS.index(district) + 1)

    def record(district, antigen, year, value, notes="", numerator=None,
               denominator=None):
        target = target_of(district)
        if denominator is None:
            denominator = target
        if numerator is None:
            numerator = round(target * value / 100)
        return {
            "programme": PROGRAMME,
            "district": district,
            "country": COUNTRY,
            "antigen": antigen,
            "year": year,
            "measure": "Administrative coverage",
            "value_percent": value,
            "numerator": numerator,
            "denominator": denominator,
            "source_id": SOURCE_ID,
            "source_ref": SOURCE_REF,
            "is_synthetic": "true",
            "notes": notes,
        }

    index_of = {}

    for district in DISTRICTS:
        for antigen in ANTIGENS:
            for year in YEARS:
                value = baseline(rng, district, antigen, year)
                row = record(district, antigen, year, value)
                records.append(row)
                index_of[(district, antigen, year)] = row

    def replace(district, antigen, year, value, notes, numerator=None,
                denominator=None):
        """Rewrite one generated return in place."""
        row = index_of[(district, antigen, year)]
        row["value_percent"] = value
        row["notes"] = notes
        if numerator is not None:
            row["numerator"] = numerator
        if denominator is not None:
            row["denominator"] = denominator
        else:
            row["numerator"] = round(
                row["denominator"] * value / 100
            )
        return row

    # C01 - administrative coverage above 100 percent. The denominator is
    # wrong, so the figure cannot be a coverage level.
    replace(
        "Mesa Verde", "MCV1", 2022, 118,
        "Doses delivered against a target population that was too small",
        numerator=1180, denominator=1000,
    )
    planted.append(("Mesa Verde", "MCV1", 2022, "C01_DENOMINATOR_SUSPECT"))

    # C06 - a unit mismatch: the same kind of number written as a fraction.
    replace(
        "Delta", "MCV1", 2021, 0.78,
        "Fraction of the target population, not a percentage",
        numerator=780, denominator=1000,
    )
    planted.append(("Delta", "MCV1", 2021, "C06_UNIT_MISMATCH"))

    # C05 - the same doses counted against two different target
    # populations. The doses are right; the denominator is not.
    original = index_of[("Lakeside", "DTP3", 2020)]
    doses = original["numerator"]
    records.append(record(
        "Lakeside", "DTP3", 2020, round(doses / 2000 * 100, 1),
        "Same doses as the main return, counted against a different target",
        numerator=doses, denominator=2000,
    ))
    planted.append(("Lakeside", "DTP3", 2020, "C05_DENOMINATOR_MISMATCH"))

    # C09 - an implausible jump from one year to the next. The year before
    # is pulled down so the jump lands on 2022.
    future = index_of[("Highlands", "MCV1", 2022)]["value_percent"]
    replace(
        "Highlands", "MCV1", 2021, max(45, future - 25),
        "Coverage collapsed in one year",
    )
    replace(
        "Highlands", "MCV1", 2022, future,
        "A jump of more than twenty points on the previous year",
    )
    planted.append(("Highlands", "MCV1", 2022, "C09_IMPLAUSIBLE_TREND"))

    # C02 - DTP1 below DTP3, which cannot happen.
    replace(
        "Foothills", "DTP1", 2021, 38,
        "Fewer first doses than third doses",
    )
    planted.append(("Foothills", "DTP1", 2021, "C02_INTERNAL_INCONSISTENCY"))

    # C07 - the year is shifted: the value is the previous year's.
    shifted = index_of[("Coast West", "MCV1", 2021)]
    replace(
        "Coast West", "MCV1", 2021, index_of[("Coast West", "MCV1", 2020)]["value_percent"],
        "The value belongs to the previous year",
    )
    planted.append(("Coast West", "MCV1", 2021, "C07_SUSPECTED_YEAR_SHIFT"))

    # Clean controls: ordinary returns that must not be flagged.
    for district, antigen, year in [
        ("North Ridge", "MCV1", 2020),
        ("South Ridge", "DTP3", 2021),
        ("East Basin", "MCV1", 2022),
        ("West Basin", "DTP3", 2020),
        ("Central Plain", "MCV1", 2021),
        ("Coast East", "DTP1", 2023),
        ("Delta", "DTP3", 2023),
        ("Mesa Verde", "MCV1", 2020),
        ("Lakeside", "MCV1", 2019),
        ("Highlands", "DTP3", 2019),
        ("Foothills", "MCV1", 2023),
        ("Coast West", "DTP3", 2023),
    ]:
        controls.append((district, antigen, year))

    return records, planted, controls


def write_database(records):
    """The same rows in a SQLite file, for the datasource connector."""
    if DATABASE.exists():
        DATABASE.unlink()
    connection = sqlite3.connect(DATABASE)
    try:
        connection.execute(
            "CREATE TABLE synthetic_programme_reports ("
            + ", ".join(FIELDS)
            + ")"
        )
        connection.executemany(
            "INSERT INTO synthetic_programme_reports VALUES ("
            + ", ".join("?" for _ in FIELDS)
            + ")",
            [tuple(str(row.get(field, "")) for field in FIELDS)
             for row in records],
        )
        connection.commit()
    finally:
        connection.close()


def main():
    records, planted, controls = build_rows()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in records:
            writer.writerow(row)

    write_database(records)

    key = {
        "generated_by": "scripts/make_synthetic.py",
        "seed": SEED,
        "programme": PROGRAMME,
        "country": COUNTRY,
        "note": (
            "Only the evaluation harness may read this file. The "
            "application must not import or read it."
        ),
        "planted": [
            {
                "district": district,
                "antigen": antigen,
                "year": year,
                "code": code,
            }
            for district, antigen, year, code in planted
        ],
        "controls": [
            {"district": district, "antigen": antigen, "year": year}
            for district, antigen, year in controls
        ],
    }

    ANSWER_KEY.parent.mkdir(parents=True, exist_ok=True)
    with ANSWER_KEY.open("w", encoding="utf-8") as handle:
        json.dump(key, handle, indent=2)
        handle.write("\n")

    print(f"Wrote {len(records)} synthetic rows to {OUTPUT}")
    print(f"Wrote the same rows to {DATABASE}")
    print(f"Planted contradictions: {len(planted)}; clean controls: {len(controls)}")
    print(f"Answer key: {ANSWER_KEY}")


if __name__ == "__main__":
    main()
