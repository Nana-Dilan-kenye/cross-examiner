"""Deterministic checks on the quality and limits of a finding."""

from src import source_registry
from src.evidence_ledger import (
    SCOPE_CONTEXT_ONLY,
    SCOPE_DOCUMENT_PRESENCE,
    SCOPE_INDEPENDENT,
    SCOPE_INDEPENDENT_MEASUREMENT,
    SCOPE_SELF_CONSISTENCY,
)
from src.findings import (
    measure_of,
    measure_source,
    observation_kind,
    observation_origin,
    source_family,
)

# Source-check statuses that the revision step upgrades after it has
# retrieved evidence. A fresh critic run must not throw that work away.
UPGRADED_STATUSES = (
    "EXTRACT_CONSISTENT",
    "EXTRACT_CONFLICT",
    "SOURCE_DOCUMENT_RETRIEVED",
)

UPGRADED_FIELDS = (
    "status",
    "verification_scope",
    "scope_note",
    "matched_values",
    "document",
    "limitations",
)

TABLE_MATCHED_STATUSES = ("CONTEXT_MATCHED", "PARTIAL_MATCH")

# The measurement kinds that make two numbers comparable in a different way
# from the pair the finding was built on.
CONFLICT_SURVEY_ADMIN = "CONFLICT_ADMIN_SURVEY"


def _same_document(left, right):
    """True when both source records point at the same registered source."""
    left_id = source_registry.source_id(left)
    right_id = source_registry.source_id(right)
    if left_id and right_id:
        return left_id == right_id
    left_url = str(left.get("url", "")).split("?", 1)[0].rstrip("/")
    right_url = str(right.get("url", "")).split("?", 1)[0].rstrip("/")
    return bool(left_url) and left_url == right_url


def value_scope(finding, source, field, matched):
    """How far one value's verification by one source reaches.

    The lineage decides, not the words in a source name:

    ``INDEPENDENT_VERIFICATION``
        The checked source is where the value's own origin is published, so
        the value was checked against the source's own published table.
    ``SELF_CONSISTENCY``
        The checked source is the document the value came from, or another
        publication of the same origin (a derived mirror). The number travels
        faithfully; that is not evidence that it is right.
    ``INDEPENDENT_MEASUREMENT``
        The checked source's number comes from a different measurement
        process - a household survey rather than administrative reporting.
        It is independent evidence about the level, not a verification of
        the value.
    """
    origin_record = measure_source(finding, field)
    checked_measure = matched.get("measure") if matched else ""

    origin_id = source_registry.origin_for(
        origin_record, measure_of(finding, field)
    )
    checked_origin = source_registry.origin_for(source, checked_measure)

    if _same_document(origin_record, source):
        return (
            SCOPE_SELF_CONSISTENCY,
            "The checked value was taken from this document, so comparing "
            "them shows that the record is faithful to its source; it is "
            "not independent verification.",
        )

    if origin_id and checked_origin:
        if origin_id == checked_origin:
            if source_registry.is_own_publication(source, checked_origin):
                return (
                    SCOPE_INDEPENDENT,
                    "Checked against the source's own published table for "
                    "this series.",
                )
            return (
                SCOPE_SELF_CONSISTENCY,
                "This source shares its upstream with the value it would "
                "confirm. Derived sources are counted once with their "
                "upstream, so this is not independent confirmation.",
            )

        if source_registry.same_series(origin_id, checked_origin):
            # An earlier revision of the same series. It cannot confirm the
            # value, and it cannot contradict it either: the estimate was
            # revised between the two publications.
            return (
                SCOPE_SELF_CONSISTENCY,
                "This source publishes an earlier revision of the same "
                "series, so it cannot confirm this value and the difference "
                "is a revision rather than a conflict.",
            )

        kind = source_registry.origin_kind(checked_origin)
        if kind in source_registry.INDEPENDENT_MEASUREMENT_KINDS:
            return (
                SCOPE_INDEPENDENT_MEASUREMENT,
                "This number comes from a different measurement process "
                "(household sampling rather than administrative reporting), "
                "so it is independent evidence about the level. It does not "
                "verify the other numbers and it was not re-read from its "
                "own published table.",
            )
        return (
            SCOPE_INDEPENDENT,
            "Checked against a source from a different upstream than the "
            "value it confirms.",
        )

    # Unregistered sources have no declared lineage. Fall back to the
    # upstream-family guess, which is the only thing left to go on.
    family = source_family(source)
    if family != "UNKNOWN" and source_family(origin_record) == family:
        return (
            SCOPE_SELF_CONSISTENCY,
            "This source shares its upstream with the value it would "
            "confirm. Derived sources are counted once with their "
            "upstream, so this is not independent confirmation.",
        )

    return (
        SCOPE_INDEPENDENT,
        "Checked against a source from a different upstream than the value "
        "it confirms.",
    )


def verification_scope(finding, source, status, matched_values=None):
    """How far a source check reaches, decided by provenance not by status.

    A check that confirms a value which is only self-consistent cannot
    support a positive disposition, so the most conservative scope among the
    values the check confirmed wins.
    """
    if status == "SOURCE_DOCUMENT_RETRIEVED":
        return (
            SCOPE_DOCUMENT_PRESENCE,
            "The document was retrieved so it could be inspected; its contents "
            "are still unverified.",
        )

    if status not in TABLE_MATCHED_STATUSES:
        return (
            SCOPE_CONTEXT_ONLY,
            "The source was never checked against its own published table.",
        )

    confirmed = [
        item for item in (matched_values or [])
        if isinstance(item, dict) and item.get("found_in_expected_year_row")
    ]
    fields = [str(item.get("field")) for item in confirmed]

    scopes = []
    for item in confirmed:
        field = str(item.get("field"))
        scopes.append(value_scope(finding, source, field, item))

    if not scopes:
        return (
            SCOPE_CONTEXT_ONLY,
            "The source's own table did not confirm the value in the "
            "expected year.",
        )

    # The conservative scope wins: a check that is self-consistent for one
    # value cannot be independent verification of the claim.
    order = (
        SCOPE_CONTEXT_ONLY,
        SCOPE_INDEPENDENT_MEASUREMENT,
        SCOPE_SELF_CONSISTENCY,
        SCOPE_INDEPENDENT,
    )
    for scope in order:
        for candidate, note in scopes:
            if candidate == scope:
                return candidate, note

    return scopes[0]


def merge_source_checks(fresh_critic, previous_critic):
    """Carry upgraded source-check statuses into a fresh critic run.

    The deterministic checks are always re-run. Only the statuses that the
    revision step earned by actually retrieving evidence are kept, so a
    second pass does not report a retrieved document as "not verified".
    """
    previous_by_url = {}
    for check in (previous_critic or {}).get("source_checks") or []:
        previous_by_url[str(check.get("url", ""))] = check

    merged = []
    for check in fresh_critic.get("source_checks") or []:
        previous = previous_by_url.get(str(check.get("url", "")))
        if previous and previous.get("status") in UPGRADED_STATUSES:
            check = {
                **check,
                **{
                    field: previous[field]
                    for field in UPGRADED_FIELDS
                    if field in previous
                },
            }
        merged.append(check)

    fresh_critic["source_checks"] = merged
    return fresh_critic


def _mark_revision_differences(finding, source, matched_values):
    """Say so when a mismatch is a revision rather than a disagreement.

    The country profiles publish an earlier revision of the WHO/UNICEF
    estimates than the workbook does. Where the two differ, the estimate
    was revised; the profile is not contradicting itself and it is not an
    independent measurement either.
    """
    out = []
    for item in matched_values or []:
        if not isinstance(item, dict) or item.get("found_in_expected_year_row"):
            out.append(item)
            continue

        field = str(item.get("field", ""))
        claim_origin = source_registry.origin_for(
            measure_source(finding, field), measure_of(finding, field)
        )
        checked_origin = source_registry.origin_for(
            source, item.get("measure")
        )
        if (
            claim_origin
            and checked_origin
            and claim_origin != checked_origin
            and source_registry.same_series(claim_origin, checked_origin)
        ):
            item = dict(item)
            item["revision_difference"] = True
            item["revision_note"] = (
                "The source publishes an earlier revision of this series, so "
                "the difference is a revision, not a conflict."
            )
        out.append(item)
    return out


def _observations(finding):
    """The observations of a finding, with their declared lineage."""
    observations = finding.get("observations")
    if observations:
        return list(observations)

    built = []
    for field in ("value_a", "value_b"):
        if field not in finding:
            continue
        source = measure_source(finding, field)
        built.append({
            "field": field,
            "measure": measure_of(finding, field),
            "value": finding.get(field),
            "source": source,
            "origin": observation_origin({"source": source, "measure": measure_of(finding, field)}),
            "measurement_kind": observation_kind({"source": source, "measure": measure_of(finding, field)}),
        })
    return built


def detect_conflicts(finding, threshold=5):
    """Comparisons between lines that do not share an upstream.

    The pair the finding was built on is a discrepancy between two
    publications. A third line that comes from a different measurement
    process - a household survey rather than administrative reporting - is
    not a third publication: it is a second kind of number, and it says
    something the other two cannot.
    """
    conflicts = []
    observations = _observations(finding)

    for observation in observations:
        if observation.get("measurement_kind") not in (
            source_registry.INDEPENDENT_MEASUREMENT_KINDS
        ):
            continue
        for other in observations:
            if other is observation:
                continue
            if other.get("measurement_kind") != "administrative_reporting":
                continue
            try:
                survey_value = float(observation.get("value"))
                admin_value = float(other.get("value"))
            except (TypeError, ValueError):
                continue
            gap = abs(survey_value - admin_value)
            if gap < threshold:
                continue
            conflicts.append({
                "code": CONFLICT_SURVEY_ADMIN,
                "country": finding.get("country"),
                "antigen": finding.get("antigen"),
                "year": finding.get("year"),
                "measure_a": other.get("measure"),
                "value_a": admin_value,
                "measure_b": observation.get("measure"),
                "value_b": survey_value,
                "gap_percentage_points": gap,
                "origin_a": other.get("origin"),
                "origin_b": observation.get("origin"),
                "note": (
                    "The administrative figure is "
                    f"{gap:.1f} percentage points above an independent "
                    "household-survey measurement for the same year. The "
                    "administrative number is not supported as the coverage "
                    "level on this evidence; the survey is the more appropriate "
                    "level estimate "
                    "among the reported figures, but it remains an unverified "
                    "measurement, with the usual caveats about survey design."
                ),
            })
    return conflicts


def critique(finding):
    issues = []
    required = (
        "country", "antigen", "year", "measure_a", "measure_b",
        "value_a", "value_b", "gap_percentage_points", "sources",
    )

    missing = [key for key in required if key not in finding or finding[key] in (None, "")]
    if missing:
        issues.append({"code": "MISSING_FIELDS", "details": missing})

    sources = finding.get("sources", [])
    if len(sources) < 2:
        issues.append({
            "code": "INSUFFICIENT_SOURCE_RECORDS",
            "details": "Fewer than two source records are attached.",
        })
    elif any(not source.get("url") for source in sources):
        issues.append({
            "code": "MISSING_SOURCE_URL",
            "details": "At least one source record has no URL.",
        })

    if finding.get("measure_a") == finding.get("measure_b"):
        issues.append({
            "code": "SAME_MEASURE",
            "details": "The two observations have the same measure label.",
        })

    try:
        a = float(finding["value_a"])
        b = float(finding["value_b"])
        reported_gap = float(finding["gap_percentage_points"])
        if not all(0 <= value <= 100 for value in (a, b)):
            issues.append({
                "code": "VALUE_OUT_OF_RANGE",
                "details": "A percentage value falls outside 0-100.",
            })
        if abs(abs(a - b) - reported_gap) > 0.01:
            issues.append({
                "code": "GAP_MISMATCH",
                "details": "The reported gap does not match the supplied values.",
            })
    except (KeyError, TypeError, ValueError):
        issues.append({
            "code": "INVALID_NUMERIC_DATA",
            "details": "Values or gap are missing or not numeric.",
        })


    source_checks = []
    from src.source_verifier import verify_pdf_source

    for source in sources:
        url = source.get("url", "")
        verification = None

        if url and "cdn.who.int/media/docs/default-source/country-profiles/immunization/" in url:
            try:
                verification = verify_pdf_source(url, finding)
            except Exception:
                verification = {"status": "VERIFICATION_ERROR"}

        status = verification["status"] if verification else (
            "NOT_VERIFIED" if url else "MISSING_URL"
        )

        matched_values = (
            verification.get("matched_values", []) if verification else []
        )
        matched_values = _mark_revision_differences(
            finding, source, matched_values
        )
        scope, scope_note = verification_scope(
            finding, source, status, matched_values
        )

        source_checks.append({
            "name": source.get("name", source.get("source", "Unnamed source")),
            "url": url,
            "url_present": bool(url),
            "table_context_matched": status == "CONTEXT_MATCHED",
            "status": status,
            "verification_scope": scope,
            "scope_note": scope_note,
            "lineage": source_registry.lineage(source),
            **(
                {
                    "table_page": verification.get("table_page"),
                    "matched_values": matched_values,
                    "limitations": verification.get("limitations", []),
                }
                if verification else {}
            ),
        })

    observations = []
    for observation in _observations(finding):
        observations.append({
            "field": observation.get("field"),
            "measure": observation.get("measure"),
            "value": observation.get("value"),
            "origin": observation.get("origin"),
            "origin_label": (
                (source_registry.origin_entry(observation.get("origin")) or {})
                .get("label")
            ),
            "measurement_kind": observation.get("measurement_kind"),
            "verification_scope": observation.get("verification_scope", ""),
            "is_synthetic": bool(
                observation.get("is_synthetic")
                or source_registry.is_synthetic(observation.get("source", {}))
            ),
            "lineage": source_registry.lineage(
                observation.get("source", {}), observation.get("measure")
            ),
        })

    conflicts = detect_conflicts(finding)

    limitations = [
        "A URL being present does not verify the source's contents.",
        "A difference between measures does not establish which value is correct.",
    ]
    if any(
        item.get("measurement_kind") in source_registry.INDEPENDENT_MEASUREMENT_KINDS
        for item in observations
    ):
        limitations.append(
            "A household-survey measurement is independent of the "
            "administrative reporting, but it was read from a publication "
            "that also carries the administrative line, so it was not "
            "re-read from the survey's own report."
        )

    return {
        "passed": not issues,
        "issues": issues,
        "source_checks": source_checks,
        "observations": observations,
        "conflicts": conflicts,
        "limitations": limitations,
    }
