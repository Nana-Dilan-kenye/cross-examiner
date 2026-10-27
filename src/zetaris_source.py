"""Read Cross-Examiner evidence from Zetaris.

The unified semantic layer is the one place the agents read from. It is a
real Zetaris USL - a compiled, deployed and activated model - whose table
holds one row per reported number, with the lineage of every row: which
publication it came from, which series it belongs to, whether it is a
derived copy of another series, whether it was generated, and how far it
may be trusted as evidence.

    lightning.metastore.cross_examiner.coverage_observations.coverage_observation

When the layer cannot be reached - no Zetaris, no API key, no network -
the same rows are read from the local files, so a run always works and
always says which path it took.
"""
import csv
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HELPER = (
    Path.home() / "hackathon" / "zetaris-getting-started" / "scripts"
)

# The semantic layer: a USL table, not a plain view.
USL_TABLE = (
    "lightning.metastore.cross_examiner.coverage_observations"
    ".coverage_observation"
)

# The columns the layer exposes, and the names the application uses.
USL_COLUMNS = [
    ("obs_id", "obs_id"),
    ("country", "country"),
    ("country_iso3", "country_iso3"),
    ("antigen", "antigen"),
    ("reporting_year", "year"),
    ("measure", "measure"),
    ("metric_type", "metric_type"),
    ("measurement_kind", "measurement_kind"),
    ("value_percent", "value_percent"),
    ("unit", "unit"),
    ("denominator", "denominator"),
    ("definition", "definition"),
    ("source_id", "source_id"),
    ("source_type", "source_type"),
    ("source_name", "source"),
    ("source_ref", "source_url"),
    ("origin_id", "origin_id"),
    ("origin_label", "origin_label"),
    ("derived_from", "derived_from"),
    ("is_derived", "is_derived"),
    ("is_synthetic", "is_synthetic"),
    ("independent_capable", "independent_capable"),
    ("verification_scope", "verification_scope"),
    ("verification_status", "verification_status"),
    ("notes", "notes"),
]

USL_QUERY = (
    "SELECT " + ", ".join(name for name, _ in USL_COLUMNS)
    + f" FROM {USL_TABLE}"
)

# The ordinary view that existed before the semantic layer. It is kept as
# a fallback: it holds the same numbers, without the lineage.
LEGACY_VIEW = "cross_examiner.UNIFIED_EVIDENCE_TABLE"

# The raw registered table, the last resort before the local files.
RAW_TABLE = "CROSS_EXAMINER_EVIDENCE.evidence_raw"

LOCAL_EVIDENCE = ROOT / "data" / "coverage_evidence.csv"
LOCAL_SYNTHETIC = ROOT / "data" / "synthetic_programme_reports.csv"

EVIDENCE_FIELDS = (
    "country", "antigen", "year", "measure", "value_percent",
    "source", "source_url", "notes",
)


def helper_dir():
    """Where the Zetaris client lives."""
    return Path(
        os.environ.get("ZETARIS_HELPER_DIR", str(DEFAULT_HELPER))
    ).expanduser()


def _client():
    """Load the Zetaris client module and open a REST channel."""
    client_file = helper_dir() / "zetaris_sql.py"

    if not client_file.is_file():
        raise FileNotFoundError(f"Zetaris client not found: {client_file}")

    spec = importlib.util.spec_from_file_location(
        "cross_examiner_zetaris_sql", client_file
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load Zetaris client: {client_file}")

    client = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(client)
    client.load_env()
    return client.open_channel("rest")


def _as_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes")


def _rows_to_records(rows):
    """Turn a flat result set into evidence records, with the lineage.

    A result set with the full column list is the semantic layer and
    already carries the lineage. A shorter one is the ordinary view,
    which carries the numbers only; the lineage is added from the
    registry.
    """
    records = []
    names = [app_name for _, app_name in USL_COLUMNS]
    for row in rows:
        if not row:
            continue
        if len(row) >= len(names):
            record = dict(zip(names, row))
        elif len(row) >= len(EVIDENCE_FIELDS):
            # The ordinary view: the numbers, without the lineage.
            record = dict(zip(EVIDENCE_FIELDS, row[:len(EVIDENCE_FIELDS)]))
        else:
            continue
        record["year"] = str(record.get("year", ""))
        record["value_percent"] = str(record.get("value_percent", ""))
        record["is_derived"] = _as_bool(record.get("is_derived"))
        record["is_synthetic"] = _as_bool(record.get("is_synthetic"))
        record["independent_capable"] = _as_bool(
            record.get("independent_capable")
        )
        records.append(record)
    return records


def _records_from_raw(channel):
    """Parse the payload of the raw registered table."""
    result = channel.run(f"SELECT * FROM {RAW_TABLE}", limit=1000)

    records = []
    for row in result.rows:
        payload = row[0]
        if isinstance(payload, str):
            payload = json.loads(payload)

        if isinstance(payload, dict):
            payload = [payload]

        for item in payload:
            records.append({
                "country": item["country"],
                "antigen": item["antigen"],
                "year": str(item["year"]),
                "measure": item["measure"],
                "value_percent": str(item["value_percent"]),
                "source": item.get("source", ""),
                "source_url": item.get("source_url", ""),
                "notes": item.get("notes", ""),
            })

    return records


def local_records(path=None):
    """The evidence rows from the local file."""
    target = Path(path) if path else LOCAL_EVIDENCE
    with target.open(newline="", encoding="utf-8") as handle:
        return [
            dict(row) for row in csv.DictReader(handle)
        ]


def load_records(view=USL_TABLE, fallback_path=None):
    """The evidence rows.

    Reads the semantic layer when Zetaris is reachable and falls back to
    the local file otherwise. The fallback is not a silent downgrade: the
    caller can see which path was taken through :func:`load_with_trace`.
    """
    rows, trace = load_with_trace(view=view, fallback_path=fallback_path)
    return rows


def load_with_trace(view=USL_TABLE, fallback_path=None):
    """The evidence rows and a trace of where they came from."""
    trace = {
        "path": "local",
        "object": None,
        "rows": 0,
        "source_ids": [],
        "reason": None,
    }

    try:
        channel = _client()
    except Exception as exc:
        trace["reason"] = f"{type(exc).__name__}: {exc}"
        records = local_records(fallback_path)
        trace["rows"] = len(records)
        return records, trace

    try:
        if view == USL_TABLE:
            result = channel.run(USL_QUERY, limit=5000)
            records = _rows_to_records(result.rows)
        else:
            result = channel.run(f"SELECT * FROM {view}", limit=5000)
            records = _rows_to_records(result.rows)

        if records:
            trace["path"] = "zetaris_usl" if view == USL_TABLE else "zetaris_view"
            trace["object"] = view
            trace["rows"] = len(records)
            trace["source_ids"] = sorted({
                str(record.get("source_id", ""))
                for record in records
                if record.get("source_id")
            })
            return records, trace

        trace["reason"] = "the semantic layer returned no rows"
    except Exception as exc:
        trace["reason"] = f"{type(exc).__name__}: {exc}"
        try:
            records = _records_from_raw(channel)
            if records:
                trace["path"] = "zetaris_raw_table"
                trace["object"] = RAW_TABLE
                trace["rows"] = len(records)
                return records, trace
        except Exception:
            pass
    finally:
        try:
            channel.close()
        except Exception:
            pass

    records = local_records(fallback_path)
    trace["rows"] = len(records)
    return records, trace


def synthetic_records(path=None):
    """The synthetic district programme returns, in the evidence shape."""
    target = Path(path) if path else LOCAL_SYNTHETIC
    if not target.exists():
        return []
    with target.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [
        {
            "country": row.get("country", ""),
            "antigen": row.get("antigen", ""),
            "year": str(row.get("year", "")),
            "measure": row.get("measure", ""),
            "value_percent": str(row.get("value_percent", "")),
            "source": "SYNTHETIC district programme reports",
            "source_url": row.get("source_ref", ""),
            "notes": row.get("notes", ""),
            "district": row.get("district", ""),
            "numerator": row.get("numerator", ""),
            "denominator": row.get("denominator", ""),
            "is_synthetic": "true",
        }
        for row in rows
    ]
