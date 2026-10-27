#!/usr/bin/env python3
"""Generate the SQL for the unified semantic layer.

The semantic layer is a real Zetaris object: a USL whose table is
compiled, deployed and activated, and whose columns carry the lineage of
every number. This script generates the SQL that builds it from
``data/sources.json``, so the lineage in the layer and the lineage in the
repository cannot drift apart.

Three files are written:

``data/registry/06_usl_views.sql``
    One view per source and measure. Each view returns the common schema
    with the lineage of that source filled in as literals, so the layer
    carries the origin, the derivation and the independence
    classification of every row.

``data/registry/07_usl_compile.sql`` and ``08_usl_activate.sql``
    The USL definition, the compilation, the deployment and the
    activation.

``data/registry/09_usl_verify.sql``
    The queries that prove what the layer holds.

    python3 scripts/generate_usl_sql.py

The recipes below say how each registered source is read. They are the
only place where the difference between a REST table, a filestore table
and a JDBC datasource is expressed.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "data" / "sources.json"
REGISTRY_DIR = ROOT / "data" / "registry"

NAMESPACE = "lightning.metastore.cross_examiner"
USL_NAME = "coverage_observations"
TABLE_NAME = "coverage_observation"
CONTAINER = "cross_examiner"

# The common schema. Every source is mapped onto it.
COLUMNS = [
    ("obs_id", "varchar(200)"),
    ("country", "varchar(100)"),
    ("country_iso3", "varchar(8)"),
    ("antigen", "varchar(40)"),
    ("reporting_year", "varchar(8)"),
    ("measure", "varchar(100)"),
    ("metric_type", "varchar(60)"),
    ("measurement_kind", "varchar(60)"),
    ("value_percent", "double"),
    ("unit", "varchar(20)"),
    ("denominator", "varchar(200)"),
    ("definition", "varchar(400)"),
    ("source_id", "varchar(120)"),
    ("source_type", "varchar(40)"),
    ("source_name", "varchar(200)"),
    ("source_ref", "varchar(600)"),
    ("origin_id", "varchar(120)"),
    ("origin_label", "varchar(300)"),
    ("derived_from", "varchar(120)"),
    ("is_derived", "boolean"),
    ("is_synthetic", "boolean"),
    ("independent_capable", "boolean"),
    ("verification_scope", "varchar(40)"),
    ("verification_status", "varchar(40)"),
    ("notes", "varchar(600)"),
]

# How each registered source is read, and what its rows mean.
#
# ``select``     the FROM clause that produces the rows.
# ``columns``    how the source's own columns map onto the common schema.
# ``filter``     an optional WHERE clause, so one table can feed several
#                measures through several views.
RECIPES = {
    "wuenic_workbook_2025": {
        "select": (
            "wuenic_workbook.wuenic_raw LATERAL VIEW explode(evidence) AS item"
        ),
        "columns": {
            "country": "item.country",
            "antigen": "item.antigen",
            "reporting_year": "item.year",
            "value_percent": "CAST(item.value_percent AS DOUBLE)",
            "source_ref": "item.source_url",
            "notes": "item.notes",
        },
        "filter": "item.measure = '{measure}'",
        "country": None,
        "country_iso3": "CASE WHEN item.country = 'Cameroon' THEN 'CMR' ELSE '' END",
        "denominator": "'Children 12-23 months'",
        "definition": "'WHO UNICEF reconciled estimate of MCV1 coverage'",
    },
    "who_country_profile_2024": {
        "select": (
            "cross_examiner_evidence.evidence_raw LATERAL VIEW explode(evidence) AS item"
        ),
        "columns": {
            "country": "item.country",
            "antigen": "item.antigen",
            "reporting_year": "item.year",
            "value_percent": "CAST(item.value_percent AS DOUBLE)",
            "source_ref": "item.source_url",
            "notes": "item.notes",
        },
        "filter": "item.measure = '{measure}'",
        "country": "Cameroon",
        "country_iso3": "CASE WHEN item.country = 'Cameroon' THEN 'CMR' ELSE '' END",
        "denominator": "'Children 12-23 months'",
        "definition": "'Coverage published in the WHO UNICEF country profile'",
    },
    "worldbank_wdi": {
        "select": (
            "world_bank_indicators.cmr_measles_coverage LATERAL VIEW explode("
            "from_json(get_json_object(_corrupt_record, '$[1]'), "
            "'array<struct<indicator:struct<id:string,value:string>,"
            "country:struct<id:string,value:string>,countryiso3code:string,"
            "date:string,value:string,unit:string,obs_status:string,"
            "decimal:int>>')) AS item"
        ),
        "columns": {
            "country": "'Cameroon'",
            "country_iso3": "item.countryiso3code",
            "antigen": "'MCV1'",
            "reporting_year": "item.date",
            "value_percent": "CAST(item.value AS DOUBLE)",
            "source_ref": "'https://api.worldbank.org/v2/country/CMR/indicator/SH.IMM.MEAS'",
            "notes": "'Indicator SH.IMM.MEAS, measles vaccination coverage'",
        },
        "denominator": "'Children 12-23 months'",
        "definition": "'World Bank indicator SH.IMM.MEAS'",
    },
    "dhs_cameroon_2018": {
        "select": (
            "cross_examiner_evidence.survey_figures_raw LATERAL VIEW explode(evidence) AS item"
        ),
        "columns": {
            "country": "item.country",
            "antigen": "item.antigen",
            "reporting_year": "item.year",
            "value_percent": "CAST(item.value_percent AS DOUBLE)",
            "source_ref": "item.source_url",
            "notes": "item.notes",
        },
        "filter": "item.measure = '{measure}'",
        "country": "Cameroon",
        "country_iso3": "CASE WHEN item.country = 'Cameroon' THEN 'CMR' ELSE '' END",
        "denominator": "'Children 12-23 months'",
        "definition": "'Measles (MCV1) coverage from a household survey'",
    },
    "who_country_profile_2024_ethiopia": {
        "select": (
            "cross_examiner_evidence.evidence_raw LATERAL VIEW explode(evidence) AS item"
        ),
        "columns": {
            "country": "item.country",
            "antigen": "item.antigen",
            "reporting_year": "item.year",
            "value_percent": "CAST(item.value_percent AS DOUBLE)",
            "source_ref": "item.source_url",
            "notes": "item.notes",
        },
        "filter": "item.measure = '{measure}'",
        "country": "Ethiopia",
        "country_iso3": "CASE WHEN item.country = 'Ethiopia' THEN 'ETH' ELSE '' END",
        "denominator": "'Children 12-23 months'",
        "definition": "'Coverage published in the WHO UNICEF country profile'",
    },
    "synthetic_programme_reports": {
        "select": "cross_examiner_synthetic.synthetic_programme_reports",
        "columns": {
            "country": "country",
            "antigen": "antigen",
            "reporting_year": "CAST(year AS VARCHAR(8))",
            "value_percent": "CAST(value_percent AS DOUBLE)",
            "denominator": "CAST(denominator AS VARCHAR(200))",
            "notes": "notes",
        },
        "country_iso3": "'MER'",
        "country": "Meridia",
        "definition": "'Administrative coverage reported by a district'",
    },
}

sys.path.insert(0, str(ROOT))

from src import source_registry  # noqa: E402

METRIC_TYPES = source_registry.METRIC_TYPES
VERIFICATION_STATUS = source_registry.VERIFICATION_STATUS


def _sql(value):
    """A SQL string literal."""
    if value is None:
        return "''"
    return "'" + str(value).replace("'", "''") + "'"


def _bool(value):
    return "true" if value else "false"


def load():
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    origins = registry.get("origins") or {}
    return registry, origins


def view_name(source_id, measure):
    """The view name for one source and measure."""
    slug = (
        measure.lower()
        .replace("(", "")
        .replace(")", "")
        .replace(" ", "_")
        .replace(",", "")
    )
    return f"obs_{source_id}_{slug}"[:60]


def scope_for(entry, origin_id, origin_info):
    """The declared verification scope of one source and measure line."""
    return source_registry.scope_for(entry, origin_id, origin_info)


def projection(source_id, measure, entry, origin_id, origin_info):
    """The (column, expression) pairs of one source and measure.

    The view returns these columns. The activation query adds the
    observation id, because the view grammar only accepts plain column
    expressions while the activation query is ordinary SQL.
    """
    recipe = RECIPES[source_id]
    columns = recipe.get("columns", {})
    empty = "''"

    def pick(name, fallback=None):
        if name in columns:
            return columns[name]
        if fallback is not None:
            return fallback
        return empty

    return [
        ("country", pick("country")),
        ("country_iso3", pick("country_iso3", recipe.get("country_iso3"))),
        ("antigen", pick("antigen")),
        ("reporting_year", pick("reporting_year")),
        ("measure", _sql(measure)),
        ("metric_type", _sql(METRIC_TYPES.get(measure, "other"))),
        ("measurement_kind", _sql((origin_info or {}).get("kind", "unknown"))),
        ("value_percent", pick("value_percent", "NULL")),
        ("unit", "'percent'"),
        ("denominator", pick("denominator", recipe.get("denominator"))),
        ("definition", recipe.get("definition", empty)),
        ("source_id", _sql(source_id)),
        ("source_type", _sql(entry.get("source_type"))),
        ("source_name", _sql(entry.get("name"))),
        ("source_ref", pick("source_ref", _sql(entry.get("origin_url")))),
        ("origin_id", _sql(origin_id)),
        ("origin_label", _sql((origin_info or {}).get("label"))),
        ("derived_from", _sql(entry.get("derived_from"))),
        ("is_derived", _bool(entry.get("derived_from"))),
        ("is_synthetic", _bool(entry.get("is_synthetic"))),
        ("independent_capable", _bool(entry.get("independent_capable"))),
        ("verification_scope", _sql(scope_for(entry, origin_id, origin_info))),
        ("verification_status", _sql(VERIFICATION_STATUS.get(source_id, "not_checked"))),
        ("notes", pick("notes", _sql(entry.get("notes")))),
    ]


def obs_id_expression(source_id, measure):
    """The observation id of one row: source, country, antigen, year, measure."""
    return (
        f"concat({_sql(source_id)}, '|', country, '|', antigen, '|', "
        f"reporting_year, '|', {_sql(measure)})"
    )


def views(registry, origins):
    """Every source and measure that has a recipe."""
    out = []
    for entry in registry.get("sources", []):
        source_id = entry.get("source_id")
        if source_id not in RECIPES:
            continue
        for measure, origin_id in (entry.get("origin_of_measure") or {}).items():
            out.append((
                source_id,
                measure,
                entry,
                origin_id,
                origins.get(origin_id) or {},
            ))
    out.sort(key=lambda item: (item[0], item[1]))
    return out


def write_views(registry, origins):
    """The file with the observation views."""
    parts = [
        "-- =============================================================================",
        "-- Generated by scripts/generate_usl_sql.py from data/sources.json.",
        "-- Do not edit by hand: change the registry and regenerate.",
        "--",
        "-- One view per source and measure. Each one returns the common schema",
        "-- with the lineage of that source filled in, so the semantic layer carries",
        "-- the origin, the derivation and the independence classification of every",
        "-- row it holds.",
        "-- =============================================================================",
        "",
    ]
    for source_id, measure, entry, origin_id, origin_info in views(registry, origins):
        recipe = RECIPES[source_id]
        pairs = projection(source_id, measure, entry, origin_id, origin_info)
        lines = [
            f"CREATE OR REPLACE SCHEMASTORE VIEW {view_name(source_id, measure)} "
            f"WITH CONTAINER {CONTAINER} AS",
            "SELECT",
        ]
        lines.append(",\n".join(
            f"    {expression} AS {name}" for name, expression in pairs
        ))
        lines.append(f"FROM {recipe['select']}")
        conditions = []
        if recipe.get("filter"):
            conditions.append(recipe["filter"].format(measure=measure))
        if recipe.get("country"):
            column = (
                "country" if recipe["select"].startswith("cross_examiner_synthetic")
                else "item.country"
            )
            conditions.append(f"{column} = '{recipe['country']}'")
        # A view reads exactly the rows its own source published, so the
        # same table can feed several views without them borrowing each
        # other's rows.
        urls = entry.get("source_urls") or []
        if urls and "explode(evidence)" in recipe["select"]:
            conditions.append(
                f"item.source_url = '{str(urls[0]).replace(chr(39), chr(39) * 2)}'"
            )
        if conditions:
            lines.append("WHERE " + " AND ".join(conditions))
        parts.append("\n".join(lines) + ";")
        parts.append("")
    return "\n".join(parts)


def write_compile(registry, origins):
    """The file with the USL definition and the deployment."""
    columns = ",\n".join(f"  {name} {kind}" for name, kind in COLUMNS)
    branches = []
    for source_id, measure, entry, origin_id, origin_info in views(registry, origins):
        pairs = projection(source_id, measure, entry, origin_id, origin_info)
        selected = ",\n    ".join(
            [f"{obs_id_expression(source_id, measure)} AS obs_id"]
            + [name for name, expression in pairs]
        )
        branches.append(
            "SELECT\n    " + selected
            + f"\nFROM {CONTAINER}.{view_name(source_id, measure)}"
        )
    union = "\nUNION ALL\n".join(branches)

    parts = [
        "-- =============================================================================",
        "-- Generated by scripts/generate_usl_sql.py from data/sources.json.",
        "-- Do not edit by hand: change the registry and regenerate.",
        "--",
        "-- The semantic layer itself: a USL with one table, the common schema for",
        "-- every reported number, whatever published it.",
        "--",
        "-- Lifecycle: the namespace must exist, the model is compiled and deployed",
        "-- into it, and the table is activated with the query that fills it.",
        "-- =============================================================================",
        "",
        f"CREATE NAMESPACE IF NOT EXISTS {NAMESPACE};",
        "",
        f"COMPILE USL {USL_NAME} DEPLOY NAMESPACE {NAMESPACE} DDL",
        f"CREATE TABLE {TABLE_NAME} (",
        columns,
        ");",
        "",
    ]
    return "\n".join(parts)


def write_activate(registry, origins):
    """The file that binds the deployed USL table to the query that fills it."""
    branches = []
    for source_id, measure, entry, origin_id, origin_info in views(registry, origins):
        pairs = projection(source_id, measure, entry, origin_id, origin_info)
        selected = ",\n    ".join(
            [f"{obs_id_expression(source_id, measure)} AS obs_id"]
            + [name for name, expression in pairs]
        )
        branches.append(
            "SELECT\n    " + selected
            + f"\nFROM {CONTAINER}.{view_name(source_id, measure)}"
        )
    union = "\nUNION ALL\n".join(branches)

    parts = [
        "-- =============================================================================",
        "-- Generated by scripts/generate_usl_sql.py from data/sources.json.",
        "-- Do not edit by hand: change the registry and regenerate.",
        "--",
        "-- Binds the deployed USL table to the query that fills it: one row per",
        "-- reported number, from every registered source, with its lineage.",
        "-- =============================================================================",
        "",
        f"ACTIVATE USL TABLE {NAMESPACE}.{USL_NAME}.{TABLE_NAME} AS",
        union,
        "",
    ]
    return "\n".join(parts)


def write_verify(registry, origins):
    """The file with the verification queries."""
    parts = [
        "-- =============================================================================",
        "-- Generated by scripts/generate_usl_sql.py from data/sources.json.",
        "--",
        "-- What the semantic layer holds, and the checks that prove it.",
        "-- =============================================================================",
        "",
        "-- 1. The deployed object, with its activation state.",
        f"SHOW NAMESPACES OR TABLES IN {NAMESPACE}",
        "",
        "-- 2. The model itself: columns, order and materialisation.",
        f"LOAD USL {USL_NAME} NAMESPACE {NAMESPACE}",
        "",
        "-- 3. The layer, queried directly.",
        f"SELECT * FROM {NAMESPACE}.{USL_NAME}.{TABLE_NAME}",
        "",
        "-- 4. One row per source, with the lineage.",
        "SELECT source_id, source_type, origin_id, is_derived, is_synthetic,",
        "       independent_capable, verification_scope, COUNT(*) AS rows",
        f"FROM {NAMESPACE}.{USL_NAME}.{TABLE_NAME}",
        "GROUP BY source_id, source_type, origin_id, is_derived, is_synthetic,",
        "         independent_capable, verification_scope",
        "ORDER BY source_id",
        "",
        "-- 5. The check that matters: the WUENIC estimate and the World Bank's",
        "--    copy of it are the same series, so they are counted once.",
        "SELECT origin_id, COUNT(DISTINCT source_id) AS sources, COUNT(*) AS rows",
        f"FROM {NAMESPACE}.{USL_NAME}.{TABLE_NAME}",
        "WHERE metric_type = 'wuenic'",
        "GROUP BY origin_id",
        "",
        "-- 6. Nothing derived is ever marked independent.",
        "SELECT COUNT(*) AS derived_marked_independent",
        f"FROM {NAMESPACE}.{USL_NAME}.{TABLE_NAME}",
        "WHERE is_derived AND independent_capable",
        "",
        "-- 7. Every synthetic row is marked synthetic.",
        "SELECT COUNT(*) AS synthetic_rows,",
        "       SUM(CASE WHEN is_synthetic THEN 1 ELSE 0 END) AS marked_synthetic",
        f"FROM {NAMESPACE}.{USL_NAME}.{TABLE_NAME}",
        "WHERE source_id = 'synthetic_programme_reports'",
        "",
        "-- 8. The independent measurement, and what it says about the",
        "--    administrative figure.",
        "SELECT reporting_year, metric_type, value_percent, origin_id, verification_scope",
        f"FROM {NAMESPACE}.{USL_NAME}.{TABLE_NAME}",
        "WHERE country = 'Cameroon' AND reporting_year IN ('2020', '2021', '2023')",
        "ORDER BY reporting_year, metric_type",
        "",
    ]
    return "\n".join(parts)


def main():
    registry, origins = load()
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)

    files = {
        "06_usl_views.sql": write_views(registry, origins),
        "07_usl_compile.sql": write_compile(registry, origins),
        "08_usl_activate.sql": write_activate(registry, origins),
        "09_usl_verify.sql": write_verify(registry, origins),
    }
    for name, text in files.items():
        (REGISTRY_DIR / name).write_text(text, encoding="utf-8")
        print(f"Wrote {REGISTRY_DIR / name}")


if __name__ == "__main__":
    main()
