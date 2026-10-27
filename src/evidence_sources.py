"""Every evidence record the agent works with, and where it came from.

The project reads more than one kind of source. This module is the one
place that says which sources were read, which one answered, and what had
to be read from a local file because the unified semantic layer could not
be reached. The agent never touches a file or an endpoint directly.

The semantic layer carries the lineage of every row: which publication it
came from, which series it belongs to, whether it is a derived copy of
another series, whether it was generated, and how far it may be trusted
as evidence. The local files carry the same lineage, taken from the
registry in ``data/sources.json``, so both paths produce the same
records.
"""

import csv
from pathlib import Path

from src import source_registry

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

EVIDENCE_FILE = DATA / "coverage_evidence.csv"
SURVEY_FILE = DATA / "survey_figures.csv"
SYNTHETIC_FILE = DATA / "synthetic_programme_reports.csv"

# The compiled sheet carries the survey figures with their own citation,
# so it needs the source name and url the evidence rows use.
SURVEY_SOURCE_NAME = "Cameroon DHS 2018 survey report"


def _read(path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _with_lineage(row, measure=None):
    """Attach the lineage the registry declares for one row."""
    source = {"name": row.get("source", ""), "url": row.get("source_url", "")}
    label = measure if measure is not None else row.get("measure", "")
    origin = source_registry.origin_for(source, label)
    origin_info = source_registry.origin_entry(origin) if origin else None
    entry = source_registry.entry_for(source) or {}

    row = dict(row)
    row.setdefault("source_id", entry.get("source_id", ""))
    row.setdefault("source_type", entry.get("source_type", ""))
    row.setdefault("origin_id", origin or "")
    row.setdefault("origin_label", (origin_info or {}).get("label", ""))
    row.setdefault("measurement_kind", (origin_info or {}).get("kind", ""))
    row.setdefault("metric_type", source_registry.METRIC_TYPES.get(label, ""))
    row.setdefault("derived_from", entry.get("derived_from") or "")
    row.setdefault(
        "is_derived",
        str(bool(entry.get("derived_from"))).lower(),
    )
    row.setdefault(
        "is_synthetic",
        str(bool(entry.get("is_synthetic"))).lower(),
    )
    row.setdefault(
        "independent_capable",
        str(bool(entry.get("independent_capable"))).lower(),
    )
    row.setdefault(
        "verification_scope",
        source_registry.scope_for(entry, origin, origin_info),
    )
    row.setdefault(
        "verification_status",
        source_registry.verification_status(entry),
    )
    return row


def evidence_rows():
    """The published coverage figures."""
    return [
        _with_lineage(row)
        for row in _read(EVIDENCE_FILE)
    ]


def survey_rows():
    """The compiled household-survey figures."""
    rows = []
    for row in _read(SURVEY_FILE):
        rows.append(_with_lineage({
            "country": row.get("country", ""),
            "antigen": row.get("antigen", ""),
            "year": str(row.get("year", "")),
            "measure": row.get("measure", ""),
            "value_percent": str(row.get("value_percent", "")),
            "source": row.get("source_id", SURVEY_SOURCE_NAME),
            "source_url": row.get("source_ref", ""),
            "notes": row.get("notes", ""),
        }))
    return rows


def synthetic_rows():
    """The generated district returns, in the evidence shape."""
    rows = []
    for row in _read(SYNTHETIC_FILE):
        rows.append(_with_lineage({
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
        }))
    return rows


def load_records(prefer_zetaris=False, include_synthetic=False):
    """Every evidence record, and a trace of where each group came from.

    When the unified semantic layer is reachable the records come from
    there, and the trace names the object that was queried. Otherwise the
    same records are read from the local files, with the lineage taken
    from the registry.
    """
    trace = []

    if prefer_zetaris:
        from src.zetaris_source import load_with_trace
        records, layer_trace = load_with_trace()
        trace.append({
            "source_id": "unified_semantic_layer",
            "records": layer_trace.get("rows", 0),
            "read_from": layer_trace.get("object") or "local files",
            "origin": layer_trace.get("path"),
            "reason": layer_trace.get("reason"),
            "source_ids": layer_trace.get("source_ids") or [],
        })
        if layer_trace.get("path") != "zetaris_usl":
            records = evidence_rows() + survey_rows()
    else:
        records = evidence_rows()
        trace.append({
            "source_id": "published_coverage_figures",
            "records": len(records),
            "read_from": EVIDENCE_FILE.name,
            "origin": "local",
            "reason": None,
        })

        survey = survey_rows()
        records = records + survey
        trace.append({
            "source_id": "compiled_survey_figures",
            "records": len(survey),
            "read_from": SURVEY_FILE.name,
            "origin": "local",
            "reason": None,
        })

    if include_synthetic:
        synthetic = synthetic_rows()
        records = records + synthetic
        trace.append({
            "source_id": "synthetic_programme_reports",
            "records": len(synthetic),
            "read_from": SYNTHETIC_FILE.name,
            "origin": "local",
            "reason": "synthetic records are labelled and never evidence",
        })
    else:
        # The semantic layer holds the generated records too. They are only
        # evidence when they are asked for.
        kept = [row for row in records if not _is_synthetic(row)]
        if len(kept) != len(records):
            trace.append({
                "source_id": "synthetic_programme_reports",
                "records": len(records) - len(kept),
                "read_from": "the semantic layer",
                "origin": "excluded",
                "reason": "generated records are never evidence",
            })
        records = kept

    return records, trace


def _is_synthetic(row):
    """True when a record is generated."""
    value = row.get("is_synthetic")
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes")
