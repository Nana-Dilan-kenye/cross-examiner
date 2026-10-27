"""Deterministic checks on district programme reports.

These are the checks the synthetic programme reports are planted with, and
they run the same way on real district returns. Every check names the
contradiction it detects and says what it saw, so a flag can be checked
against the published record rather than taken on trust.

The codes are the ones the project's own plan uses:

``C01_DENOMINATOR_SUSPECT``
    Coverage above 100 percent. The target population is wrong.
``C02_INTERNAL_INCONSISTENCY``
    A dose that cannot be given is missing: first doses below third doses.
``C05_DENOMINATOR_MISMATCH``
    The same numerator counted against two different denominators.
``C06_UNIT_MISMATCH``
    A fraction where a percentage belongs.
``C07_SUSPECTED_YEAR_SHIFT``
    A value that belongs to the neighbouring year.
``C09_IMPLAUSIBLE_TREND``
    A jump of more than twenty points on the previous year.
``C10_MISSING_EVIDENCE``
    No return at all for a district, antigen and year.
"""

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROGRAMME_REPORTS = ROOT / "data" / "synthetic_programme_reports.csv"

MAX_COVERAGE = 100.0
TREND_THRESHOLD = 20.0
UNIT_THRESHOLD = 1.0


def load_reports(path=None):
    """The programme reports, as a list of dicts."""
    target = Path(path) if path else PROGRAMME_REPORTS
    if not target.exists():
        return []
    with target.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _key(row):
    return (
        str(row.get("district", "")),
        str(row.get("antigen", "")),
        str(row.get("year", "")),
    )


def _out_of_range(value):
    """True when a coverage value cannot be a percentage."""
    if value is None:
        return False
    return value > MAX_COVERAGE or 0 < value < UNIT_THRESHOLD


def check_records(records, expected_years=None, expected_pairs=None):
    """Run every check over a set of programme returns.

    ``expected_years`` and ``expected_pairs`` describe what should have
    been reported. Without them the missing-evidence check cannot run,
    because nothing says which district and antigen were supposed to
    report.

    Returns a list of flags, each with the record it belongs to.
    """
    flags = []
    by_district_antigen = {}
    by_numerator = {}

    for row in records:
        value = _number(row.get("value_percent"))
        numerator = _number(row.get("numerator"))
        denominator = _number(row.get("denominator"))

        if value is not None and value > MAX_COVERAGE:
            flags.append({
                "code": "C01_DENOMINATOR_SUSPECT",
                "district": row.get("district"),
                "antigen": row.get("antigen"),
                "year": row.get("year"),
                "detail": (
                    f"Coverage of {value} percent is above 100 percent, so "
                    "the target population cannot be right."
                ),
            })

        if value is not None and 0 < value < UNIT_THRESHOLD:
            flags.append({
                "code": "C06_UNIT_MISMATCH",
                "district": row.get("district"),
                "antigen": row.get("antigen"),
                "year": row.get("year"),
                "detail": (
                    f"The value {value} is a fraction where a percentage "
                    "belongs."
                ),
            })

        if numerator is not None and denominator:
            by_numerator.setdefault(numerator, set()).add(denominator)

        by_district_antigen.setdefault(
            (str(row.get("district", "")), str(row.get("antigen", ""))), []
        ).append(row)

    for numerator, denominators in by_numerator.items():
        if len(denominators) > 1:
            for row in records:
                if _number(row.get("numerator")) != numerator:
                    continue
                # The same doses counted against two different targets is a
                # denominator problem, not a duplicate: the rows are in the
                # same district.
                same_district = [
                    other for other in records
                    if _number(other.get("numerator")) == numerator
                    and str(other.get("district")) == str(row.get("district"))
                ]
                if len(same_district) < 2:
                    continue
                flags.append({
                    "code": "C05_DENOMINATOR_MISMATCH",
                    "district": row.get("district"),
                    "antigen": row.get("antigen"),
                    "year": row.get("year"),
                    "detail": (
                        f"The same {int(numerator)} doses are counted "
                        f"against {len(denominators)} different target "
                        "populations."
                    ),
                })

    for (district, antigen), rows in by_district_antigen.items():
        by_year = {}
        for row in rows:
            # A district can report the same year twice; the first return
            # is the one the series is built from.
            by_year.setdefault(str(row.get("year")), row)
        years = sorted(by_year)

        # C02 - first doses cannot be fewer than third doses.
        dpt1 = by_year.get("2021")
        for year in years:
            first = by_year.get(year)
            if not first:
                continue
            if str(first.get("antigen")) != "DTP1":
                continue
            value = _number(first.get("value_percent"))
            for other in rows:
                if str(other.get("antigen")) != "DTP3":
                    continue
                if str(other.get("year")) != year:
                    continue
                other_value = _number(other.get("value_percent"))
                if value is None or other_value is None:
                    continue
                if value < other_value:
                    flags.append({
                        "code": "C02_INTERNAL_INCONSISTENCY",
                        "district": district,
                        "antigen": "DTP1",
                        "year": year,
                        "detail": (
                            f"First doses ({value} percent) are below third "
                            f"doses ({other_value} percent) for the same "
                            "district and year."
                        ),
                    })

        # C09 - a jump of more than twenty points on the previous year.
        # A year whose own value is already out of range is not used to
        # judge its neighbours: the out-of-range value is the finding.
        for index in range(1, len(years)):
            previous = _number(by_year[years[index - 1]].get("value_percent"))
            current = _number(by_year[years[index]].get("value_percent"))
            if previous is None or current is None:
                continue
            if _out_of_range(previous) or _out_of_range(current):
                continue
            if abs(current - previous) > TREND_THRESHOLD:
                flags.append({
                    "code": "C09_IMPLAUSIBLE_TREND",
                    "district": district,
                    "antigen": antigen,
                    "year": years[index],
                    "detail": (
                        f"Coverage moved from {previous} to {current} percent "
                        f"in one year, a change of "
                        f"{abs(current - previous):.1f} points."
                    ),
                })

        # C07 - the value belongs to the neighbouring year. A series that
        # moves every year repeats a value only when the year was shifted.
        for index in range(1, len(years)):
            previous = _number(by_year[years[index - 1]].get("value_percent"))
            current = _number(by_year[years[index]].get("value_percent"))
            if previous is None or current is None:
                continue
            if _out_of_range(previous) or _out_of_range(current):
                continue
            if current == previous:
                flags.append({
                    "code": "C07_SUSPECTED_YEAR_SHIFT",
                    "district": district,
                    "antigen": antigen,
                    "year": years[index],
                    "detail": (
                        f"The value {current} percent for {years[index]} is "
                        f"the value of {years[index - 1]}."
                    ),
                })

    # C10 - a district, antigen and year with no return at all.
    if expected_years:
        pairs = set(expected_pairs or [])
        for row in records:
            pairs.add(
                (str(row.get("district", "")), str(row.get("antigen", "")))
            )
        for district, antigen in sorted(pairs):
            reported = {
                str(row.get("year"))
                for row in records
                if str(row.get("district")) == district
                and str(row.get("antigen")) == antigen
            }
            for year in expected_years:
                if str(year) not in reported:
                    flags.append({
                        "code": "C10_MISSING_EVIDENCE",
                        "district": district,
                        "antigen": antigen,
                        "year": year,
                        "detail": (
                            f"No programme return for {district} "
                            f"{antigen} {year}."
                        ),
                    })

    return flags


def flags_by_record(flags):
    """Flags grouped by the record they belong to."""
    grouped = {}
    for flag in flags:
        key = (flag.get("district"), flag.get("antigen"), str(flag.get("year")))
        grouped.setdefault(key, []).append(flag)
    return grouped
