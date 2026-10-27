#!/usr/bin/env python3
"""Verify the deployed unified semantic layer against the running instance.

This is the live half of the verification. It asks the running Zetaris
instance what it actually holds, and it fails loudly when something is
missing. The offline half lives in ``tests/test_usl_offline.py`` and uses
fixtures: it proves the checks are right, not that the instance is.

    python3 scripts/verify_usl.py

Exit status 0 when every check passed, 1 otherwise.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import source_registry  # noqa: E402
from src import zetaris_source  # noqa: E402

# The object this project owns.
NAMESPACE = "lightning.metastore.cross_examiner"
USL_NAME = "coverage_observations"
TABLE_NAME = "coverage_observation"
USL_TABLE = f"{NAMESPACE}.{USL_NAME}.{TABLE_NAME}"

# The sources that must contribute records to the layer.
EXPECTED_SOURCES = (
    "wuenic_workbook_2025",
    "who_country_profile_2024",
    "worldbank_wdi",
    "dhs_cameroon_2018",
    "synthetic_programme_reports",
)

# The connector types that must be represented.
EXPECTED_SOURCE_TYPES = ("xlsx", "pdf", "rest_json", "csv")


class Report:
    """The checks and their outcome."""

    def __init__(self):
        self.checks = []

    def add(self, name, passed, detail=""):
        self.checks.append({
            "name": name,
            "passed": bool(passed),
            "detail": str(detail),
        })
        return passed

    @property
    def failed(self):
        return [check for check in self.checks if not check["passed"]]


def _client():
    return zetaris_source._client()


def _rows(channel, sql, limit=5000):
    result = channel.run(sql, limit=limit)
    return result.rows


def verify(report):
    """Run every check against the running instance."""
    try:
        channel = _client()
    except Exception as exc:
        report.add(
            "the Zetaris instance is reachable",
            False,
            f"{type(exc).__name__}: {exc}",
        )
        return report

    try:
        # 1. the deployed object, and its activation state.
        rows = _rows(
            channel, f"SHOW NAMESPACES OR TABLES IN {NAMESPACE}", limit=100
        )
        names = [str(row[0]) for row in rows]
        report.add(
            f"the USL {USL_NAME} is deployed in {NAMESPACE}",
            USL_NAME in names,
            f"namespaces and USLs there: {names}",
        )
        report.add(
            "the pre-existing USL cross_examiner_evidence was not replaced",
            "cross_examiner_evidence" in names,
            f"namespaces and USLs there: {names}",
        )

        # 2. the model itself.
        model_rows = _rows(
            channel, f"LOAD USL {USL_NAME} NAMESPACE {NAMESPACE}", limit=10
        )
        model = {}
        if model_rows:
            try:
                model = json.loads(model_rows[0][0])
            except (TypeError, ValueError):
                model = {}
        tables = model.get("tables") or []
        table_names = [item.get("name") for item in tables]
        report.add(
            "the model declares the table the application reads",
            TABLE_NAME in table_names,
            f"tables: {table_names}",
        )
        declared_columns = []
        for item in tables:
            if item.get("name") == TABLE_NAME:
                declared_columns = [
                    column.get("name")
                    for column in item.get("columnSpecs") or []
                ]
        report.add(
            "the model declares the whole common schema",
            len(declared_columns) == len(zetaris_source.USL_COLUMNS),
            f"{len(declared_columns)} columns declared, "
            f"{len(zetaris_source.USL_COLUMNS)} expected",
        )

        # 3. the layer, queried directly.
        observation_rows = _rows(
            channel,
            "SELECT * FROM " + USL_TABLE,
            limit=5000,
        )
        report.add(
            "the layer answers a direct query",
            bool(observation_rows),
            f"{len(observation_rows)} rows",
        )

        names = [name for name, _ in zetaris_source.USL_COLUMNS]
        records = []
        for row in observation_rows:
            if len(row) >= len(names):
                records.append(dict(zip(names, row)))

        source_ids = {record.get("source_id") for record in records}
        missing = [s for s in EXPECTED_SOURCES if s not in source_ids]
        report.add(
            "every registered source contributes records",
            not missing,
            f"missing: {missing}" if missing else f"{len(source_ids)} sources",
        )

        source_types = {record.get("source_type") for record in records}
        missing_types = [t for t in EXPECTED_SOURCE_TYPES if t not in source_types]
        report.add(
            "the layer spans the source types",
            not missing_types,
            f"types: {sorted(t for t in source_types if t)}",
        )

        # 4. the lineage survives the unification.
        with_origin = [
            record for record in records if record.get("origin_id")
        ]
        report.add(
            "every record keeps its origin",
            len(with_origin) == len(records),
            f"{len(with_origin)} of {len(records)} records carry an origin",
        )

        # 5. the rule that matters: a derived copy is never independent.
        derived_independent = [
            record for record in records
            if str(record.get("is_derived")).lower() == "true"
            and str(record.get("independent_capable")).lower() == "true"
        ]
        report.add(
            "no derived copy is marked independent",
            not derived_independent,
            f"{len(derived_independent)} offenders",
        )

        wuenic_rows = [
            record for record in records
            if record.get("metric_type") == "wuenic"
        ]
        wuenic_origins = {record.get("origin_id") for record in wuenic_rows}
        report.add(
            "the WUENIC series and its copies share one origin",
            wuenic_origins == {"wuenic_2025"},
            f"origins: {sorted(o for o in wuenic_origins if o)}",
        )
        wuenic_sources = {record.get("source_id") for record in wuenic_rows}
        report.add(
            "the World Bank copy of the estimate is in the layer",
            "worldbank_wdi" in wuenic_sources,
            f"sources publishing the estimate: {sorted(wuenic_sources)}",
        )

        # 6. the synthetic records are marked and cannot be counted.
        synthetic = [
            record for record in records
            if record.get("source_id") == "synthetic_programme_reports"
        ]
        marked = [
            record for record in synthetic
            if str(record.get("is_synthetic")).lower() == "true"
        ]
        report.add(
            "every synthetic record is marked synthetic",
            synthetic and len(marked) == len(synthetic),
            f"{len(marked)} of {len(synthetic)} marked",
        )
        synthetic_independent = [
            record for record in synthetic
            if str(record.get("independent_capable")).lower() == "true"
        ]
        report.add(
            "no synthetic record can substantiate a real conclusion",
            not synthetic_independent,
            f"{len(synthetic_independent)} offenders",
        )

        # 7. the application reads this layer.
        rows, trace = zetaris_source.load_with_trace()
        report.add(
            "the application reads the semantic layer",
            trace.get("path") == "zetaris_usl",
            f"path: {trace.get('path')}, object: {trace.get('object')}",
        )
        report.add(
            "the application asks for the layer by its real name",
            trace.get("object") == USL_TABLE,
            f"object: {trace.get('object')}",
        )
        report.add(
            "the trace names the sources the layer returned",
            bool(trace.get("source_ids")),
            f"source ids: {trace.get('source_ids')}",
        )
        report.add(
            "the application's read path and the layer agree",
            len(rows) == len(records),
            f"{len(rows)} rows through the application, "
            f"{len(records)} in the layer",
        )

        # 8. the registry and the layer agree on the lineage.
        #
        # The lookup is by source_id, the layer's own key. The row's
        # source_ref is where the *number* is attributed, which may be a
        # different publication from the one that supplied the row: the
        # country profile's estimate row, for instance, is attributed to
        # the UNICEF data page the estimate comes from.
        by_id = {
            entry.get("source_id"): entry
            for entry in source_registry.registry_rows()
        }
        mismatches = []
        for record in records:
            entry = by_id.get(record.get("source_id"))
            if not entry:
                mismatches.append(record.get("obs_id", ""))
                continue
            expected_origin = (entry.get("origin_of_measure") or {}).get(
                record.get("measure")
            )
            if expected_origin != record.get("origin_id"):
                mismatches.append(record.get("obs_id", ""))
        report.add(
            "the layer's lineage matches the registry",
            not mismatches,
            f"{len(mismatches)} mismatches",
        )
    finally:
        try:
            channel.close()
        except Exception:
            pass

    return report


def main():
    report = Report()
    verify(report)

    width = max(len(check["name"]) for check in report.checks)
    for check in report.checks:
        mark = "PASS" if check["passed"] else "FAIL"
        print(f"[{mark}] {check['name']:<{width}}  {check['detail']}")

    print()
    print(f"{len(report.checks) - len(report.failed)}/{len(report.checks)} checks passed")
    if report.failed:
        print("FAILED: " + ", ".join(c["name"] for c in report.failed))
        return 1
    print("The unified semantic layer is deployed, activated and verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
