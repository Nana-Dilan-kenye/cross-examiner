#!/usr/bin/env python3
"""Export the source registry as a flat CSV.

The registry in ``data/sources.json`` is the authoritative description of
every source. The unified semantic layer needs it as a *table* it can join
against, so this script flattens it into ``data/sources.csv``: one row per
source and measure, carrying the lineage and the independence
classification.

    python3 scripts/export_sources.py

The test suite checks that the CSV still matches the JSON, so the two
cannot drift apart.
"""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "data" / "sources.json"
OUTPUT = ROOT / "data" / "sources.csv"

FIELDS = [
    "source_id",
    "source_name",
    "source_type",
    "measure",
    "origin_id",
    "origin_label",
    "origin_kind",
    "derived_from",
    "is_derived",
    "is_own_publication",
    "is_synthetic",
    "independent_capable",
    "verification_scope",
    "source_url",
    "licence",
    "notes",
]

# The scope of a line as evidence about itself. A derived mirror of a
# series is self-consistency, never independent confirmation; the origin
# document is self-consistency too; a household survey is an independent
# measurement; generated records are never evidence.
SCOPES = {
    ("origin",): "SELF_CONSISTENCY",
    ("mirror",): "SELF_CONSISTENCY",
    ("measurement",): "INDEPENDENT_MEASUREMENT",
    ("synthetic",): "CONTEXT_ONLY",
}


def scope_for(entry, origin_id, origin_info):
    """The declared verification scope of one source/measure line."""
    if entry.get("is_synthetic") or (origin_info or {}).get("is_synthetic"):
        return SCOPES[("synthetic",)]
    if origin_info and origin_info.get("kind") == "household_survey":
        return SCOPES[("measurement",)]
    if entry.get("derived_from"):
        return SCOPES[("mirror",)]
    if origin_id in (entry.get("own_publications") or []):
        return SCOPES[("origin",)]
    return SCOPES[("mirror",)]


def rows():
    """The flattened registry."""
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    origins = registry.get("origins") or {}
    out = []

    for entry in registry.get("sources", []):
        urls = entry.get("source_urls") or []
        for measure, origin_id in (entry.get("origin_of_measure") or {}).items():
            origin_info = origins.get(origin_id) or {}
            out.append({
                "source_id": entry.get("source_id"),
                "source_name": entry.get("name"),
                "source_type": entry.get("source_type"),
                "measure": measure,
                "origin_id": origin_id,
                "origin_label": origin_info.get("label"),
                "origin_kind": origin_info.get("kind"),
                "derived_from": entry.get("derived_from") or "",
                "is_derived": "true" if entry.get("derived_from") else "false",
                "is_own_publication": (
                    "true" if origin_id in (entry.get("own_publications") or [])
                    else "false"
                ),
                "is_synthetic": "true" if entry.get("is_synthetic") else "false",
                "independent_capable": (
                    "true" if entry.get("independent_capable") else "false"
                ),
                "verification_scope": scope_for(entry, origin_id, origin_info),
                "source_url": urls[0] if urls else (entry.get("origin_url") or ""),
                "licence": entry.get("licence") or "",
                "notes": entry.get("notes") or "",
            })

    out.sort(key=lambda row: (row["source_id"], row["measure"]))
    return out


def write():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows():
            writer.writerow(row)
    return len(rows())


def main():
    count = write()
    print(f"Wrote {count} registry rows to {OUTPUT}")


if __name__ == "__main__":
    main()
