"""The source registry: which publication a number came from, and what produced it.

The registry is data, not inference. ``src/findings.py`` used to guess an
upstream family from the words in a source name ("wuenic", "unicef",
"who.int"), which meant that renaming a source could change a verdict: the
same evidence would be scored as independent verification one day and as
self-consistency the next. Worse, a source that republishes another series
(the World Bank republishing the WUENIC estimate) was invisible to that
heuristic, so it could have been counted as confirming a number it was
derived from.

Two concepts carry the lineage:

``source``
    A publication the agent read: the workbook, the country profile PDF, a
    REST endpoint, a generated CSV.

``origin``
    The series the numbers actually come from: the WUENIC estimate, the
    national administrative reporting, a household survey. A source that
    republishes an origin is a *derived mirror* of it. Derived sources are
    counted once with their origin, so a mirror can never confirm the
    numbers it was derived from.

A source is the *own publication* of an origin when it is where that origin
is published. Checking a value against the origin's own publication is the
strongest check available - it verifies the value against the source's own
published table. Checking it against a derived mirror is self-consistency:
it shows the number travels faithfully, not that the number is right.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "data" / "sources.json"

# Measurement kinds that do not derive from administrative reporting. A
# number produced by one of these is independent *evidence about the level*,
# even when it is published by the same organisation as the administrative
# line.
INDEPENDENT_MEASUREMENT_KINDS = ("household_survey",)

# The measure label -> the metric type the unified layer carries.
METRIC_TYPES = {
    "WUENIC estimate": "wuenic",
    "Administrative coverage": "administrative",
    "Official (government) coverage": "official",
    "Household survey coverage": "survey",
    "Programme report (synthetic)": "programme_report",
}

# How far a line may be trusted as evidence, decided by its lineage.
SCOPE_SELF_CONSISTENCY = "SELF_CONSISTENCY"
SCOPE_INDEPENDENT_MEASUREMENT = "INDEPENDENT_MEASUREMENT"
SCOPE_CONTEXT_ONLY = "CONTEXT_ONLY"

# How a source's numbers were checked.
VERIFICATION_STATUS = {
    "wuenic_workbook_2025": "verified_against_source_table",
    "who_country_profile_2024": "verified_against_source_table",
    "worldbank_wdi": "verified_against_source_table",
    "unicef_sdmx_immunisation": "verified_against_source_table",
    "dhs_cameroon_2018": "transcribed_from_publication",
    "synthetic_programme_reports": "generated",
}

_REGISTRY = None


def load_registry(path=None):
    """The registry, read once per process."""
    global _REGISTRY
    if path is not None:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    if _REGISTRY is None:
        with open(REGISTRY_PATH, encoding="utf-8") as handle:
            _REGISTRY = json.load(handle)
    return _REGISTRY


def reset_registry():
    """Drop the cached registry (used by the tests)."""
    global _REGISTRY
    _REGISTRY = None


def _normalise_url(url):
    """A URL without its query string, for matching."""
    return str(url or "").split("?", 1)[0].rstrip("/").casefold()


def _source_fields(source):
    """The name and the URL of a source record, however it was written."""
    if source is None:
        return "", ""
    if isinstance(source, str):
        return source, ""
    return (
        str(source.get("name", "") or ""),
        str(source.get("url", "") or ""),
    )


def entry_for(source):
    """The registry entry for a source record, or None."""
    registry = load_registry()
    name, url = _source_fields(source)
    target_url = _normalise_url(url)
    target_name = name.strip().casefold()

    for entry in registry.get("sources", []):
        for known in entry.get("source_urls", []):
            if _normalise_url(known) == target_url and target_url:
                return entry
    for entry in registry.get("sources", []):
        for known in entry.get("source_names", []):
            if known.strip().casefold() == target_name and target_name:
                return entry
    return None


def candidate_urls(url):
    """Registered URLs for the source that owns ``url``.

    The configured canonical URL is preferred, followed by any alternate
    URLs already registered for that source. An unknown URL is returned
    unchanged so callers can still attempt it.
    """
    url = str(url or "").strip()
    if not url:
        return []

    entry = entry_for({"url": url})
    candidates = []
    if entry:
        # Only URLs registered as serving the same document are eligible
        # fallbacks. A publication catalog or search page is not the same
        # document, even when it is the source's origin page.
        for known in entry.get("source_urls") or []:
            known = str(known or "").strip()
            if known and known not in candidates:
                candidates.append(known)

    if url not in candidates:
        candidates.insert(0, url)
    return candidates


def source_id(source):
    """The registry id of a source record, or None."""
    entry = entry_for(source)
    return entry.get("source_id") if entry else None


def origin_for(source, measure=None):
    """The origin of a measure published by a source.

    ``measure`` is the label the evidence uses ("WUENIC estimate",
    "Administrative coverage", ...). When the measure is unknown the source's
    single origin is used, so a source that publishes one series still
    resolves.
    """
    entry = entry_for(source)
    if not entry:
        return None
    origins = entry.get("origin_of_measure") or {}
    if measure and measure in origins:
        return origins[measure]
    if measure:
        # A source may publish the same series under a slightly different
        # label. Fall back to a case-insensitive match before giving up.
        for label, origin in origins.items():
            if label.casefold() == str(measure).casefold():
                return origin
        return None
    if len(origins) == 1:
        return next(iter(origins.values()))
    return None


def origin_entry(origin_id):
    """The registry entry for an origin, or None."""
    registry = load_registry()
    return (registry.get("origins") or {}).get(origin_id)


def series_for(origin_id):
    """The series an origin belongs to.

    Two origins can be the same series: the WHO/UNICEF estimates of 2023
    and of 2025 are one series, published twice. A revision is not a
    second opinion, so a value can never be confirmed by another revision
    of its own series.
    """
    entry = origin_entry(origin_id)
    if not entry:
        return None
    return entry.get("series") or origin_id


def same_series(first, second):
    """True when two origins belong to the same series."""
    if not first or not second:
        return False
    return series_for(first) == series_for(second)


def origin_kind(origin_id):
    """The kind of measurement behind an origin."""
    entry = origin_entry(origin_id)
    return entry.get("kind") if entry else None


def origin_kind(source, measure=None):
    """The kind of measurement behind a measure ("household_survey", ...)."""
    origin = origin_for(source, measure)
    entry = origin_entry(origin) if origin else None
    return entry.get("kind") if entry else None


def is_own_publication(source, origin_id):
    """True when the source is where that origin is published."""
    entry = entry_for(source)
    if not entry or not origin_id:
        return False
    return origin_id in (entry.get("own_publications") or [])


def is_derived(source):
    """True when the source republishes another series."""
    entry = entry_for(source)
    if not entry:
        return False
    return bool(entry.get("derived_from"))


def is_synthetic(source):
    """True when the source is generated."""
    entry = entry_for(source)
    if not entry:
        return False
    if entry.get("is_synthetic"):
        return True
    origin = origin_entry(entry.get("own_publications", [None])[0]) \
        if entry.get("own_publications") else None
    return bool(origin and origin.get("is_synthetic"))


def is_independent_measurement(source, measure=None):
    """True when the measure comes from a measurement that does not derive
    from administrative reporting.

    A household survey is the example: it samples households, so it is
    independent evidence about the coverage level even when it is published
    in the same document as the administrative line.
    """
    return origin_kind(source, measure) in INDEPENDENT_MEASUREMENT_KINDS


def label(source, measure=None):
    """A short human label for a source, for the report."""
    entry = entry_for(source)
    if not entry:
        name, _ = _source_fields(source)
        return name or "Unnamed source"
    origin = origin_for(source, measure)
    origin_info = origin_entry(origin) if origin else None
    if origin_info:
        return f"{entry.get('name')} — {origin_info.get('label')}"
    return entry.get("name")


def lineage(source, measure=None):
    """The full lineage of one measure, for the report."""
    entry = entry_for(source)
    if not entry:
        name, url = _source_fields(source)
        return {
            "source_id": None,
            "source_name": name,
            "source_type": "unregistered",
            "publication_url": url,
            "origin": None,
            "origin_label": None,
            "origin_kind": None,
            "derived_from": None,
            "is_own_publication": False,
            "is_synthetic": False,
            "independent_capable": False,
            "access": [],
        }
    origin = origin_for(source, measure)
    origin_info = origin_entry(origin) if origin else None
    derived = entry.get("derived_from")
    if derived:
        derived_entry = next(
            (
                item
                for item in load_registry().get("sources", [])
                if item.get("source_id") == derived
            ),
            None,
        )
        derived = derived_entry.get("name") if derived_entry else derived
    return {
        "source_id": entry.get("source_id"),
        "source_name": entry.get("name"),
        "source_type": entry.get("source_type"),
        "publication_url": entry.get("origin_url"),
        "origin": origin,
        "origin_label": origin_info.get("label") if origin_info else None,
        "origin_kind": origin_info.get("kind") if origin_info else None,
        "derived_from": derived,
        "is_own_publication": is_own_publication(source, origin),
        "is_synthetic": bool(entry.get("is_synthetic")),
        "independent_capable": bool(entry.get("independent_capable")),
        "access": list(entry.get("access") or []),
    }


def scope_for(entry, origin_id, origin_info):
    """The declared verification scope of one source and measure line.

    A generated record is never evidence. A household survey is an
    independent measurement: it does not derive from the administrative
    reporting, so it is independent evidence about the level, but it is
    not a verification of the numbers it is compared with. Everything
    else is self-consistency: reading a number back out of the
    publication it came from, or out of another publication of the same
    series, proves the extraction worked and nothing more.
    """
    if entry.get("is_synthetic") or (origin_info or {}).get("is_synthetic"):
        return SCOPE_CONTEXT_ONLY
    if (origin_info or {}).get("kind") in INDEPENDENT_MEASUREMENT_KINDS:
        return SCOPE_INDEPENDENT_MEASUREMENT
    return SCOPE_SELF_CONSISTENCY


def verification_status(entry):
    """The declared verification status of a source."""
    return VERIFICATION_STATUS.get(
        (entry or {}).get("source_id", ""), "not_checked"
    )


def metric_type(measure):
    """The metric type of a measure label."""
    return METRIC_TYPES.get(measure, "other")


def registry_rows():
    """Every source in the registry, for the report and the tests."""
    return list(load_registry().get("sources", []))
