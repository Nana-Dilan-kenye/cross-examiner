"""Small helpers shared by the analysis, investigation and reporting layers."""

from src import source_registry


def finding_key(finding):
    """Stable key for one finding, used to line up proposals and decisions."""
    return (
        str(finding.get("country", "")),
        str(finding.get("antigen", "")),
        str(finding.get("year", "")),
    )


def finding_label(finding):
    """Short human label for one finding."""
    return (
        f"{finding.get('country', '')} {finding.get('antigen', '')} "
        f"({finding.get('year', '')})"
    ).strip()


def source_family(source):
    """The upstream family a source belongs to.

    The registry decides this now, because a guess based on the words in a
    source name can be wrong: renaming a source used to be enough to turn a
    self-consistency check into an independent verification, and a source
    that merely republishes another series was invisible to it. The
    substring heuristic is kept for sources the registry does not know.
    """
    origin = source_registry.origin_for(source)
    if origin:
        return origin

    blob = " ".join([
        str(source.get("name", "")),
        str(source.get("url", "")),
        str(source.get("source", "")),
    ]).casefold()
    if "wuenic" in blob or "unicef" in blob:
        return "WUENIC"
    if "who.int" in blob or "world health organization" in blob:
        return "WHO"
    return "UNKNOWN"


def measure_source(finding, field):
    """The source record a measured value was taken from."""
    sources = finding.get("measure_sources") or {}
    record = sources.get(field)
    if record:
        return record
    # Findings built before the measure/source mapping existed keep the
    # original order: the first source backs value_a, the second value_b.
    fallback = {"value_a": 0, "value_b": 1}.get(field)
    listed = finding.get("sources") or []
    if fallback is not None and len(listed) > fallback:
        return listed[fallback]
    return {}


def measure_of(finding, field):
    """The measure label of one side of a finding."""
    if field == "value_a":
        return finding.get("measure_a", "")
    if field == "value_b":
        return finding.get("measure_b", "")
    return ""


def value_origin(finding, field):
    """The origin of the series a value on one side of the finding comes from.

    None when the source is not in the registry: an unregistered source has
    no declared lineage and may not be treated as independent.
    """
    source = measure_source(finding, field)
    return source_registry.origin_for(source, measure_of(finding, field))


def observation_origin(observation):
    """The origin of one observation record."""
    if not observation:
        return None
    return source_registry.origin_for(
        observation.get("source", {}),
        observation.get("measure", ""),
    )


def observation_kind(observation):
    """The kind of measurement behind one observation."""
    if not observation:
        return None
    return source_registry.origin_kind(
        observation.get("source", {}),
        observation.get("measure", ""),
    )
