"""Critic-driven extra evidence fetch. Not an LLM agent.

The trusted Python code in this module decides what evidence is retrieved and
what the retrieved evidence means. A model may propose *which* of the
allow-listed actions is taken (see :mod:`src.investigator`), but the action
is ignored unless it is on the allowlist and resolves to a source already
attached to the finding.

Status vocabulary for source checks added here:

``EXTRACT_CONSISTENT`` / ``EXTRACT_CONFLICT``
    The claimed value was compared with the local WUENIC workbook extract.
    The workbook is where the original values came from, so this is a
    self-consistency check on the extraction path, not independent
    verification of the underlying data.

``SOURCE_DOCUMENT_RETRIEVED``
    A source document was fetched so its content could be inspected.
    Retrieving a document says nothing about whether the numbers in it are
    right.
"""
import json
import os
import re
from urllib.error import URLError
from urllib.request import Request, urlopen

DEFAULT_EVIDENCE_API = os.environ.get(
    "EVIDENCE_API_URL", "http://127.0.0.1:8765"
)
# The evidence API parses a large workbook, so the first request is slow.
EVIDENCE_API_TIMEOUT = float(os.environ.get("EVIDENCE_API_TIMEOUT", "60"))

DOCUMENT_TIMEOUT = 20
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"(?is)<(script|style).*?</\1>")


def finding_measures(finding):
    """The measure labels a finding carries, with their values."""
    measures = {}
    for observation in finding.get("observations") or []:
        label = str(observation.get("measure", ""))
        if label:
            measures[label.casefold()] = observation.get("value")
    for field in ("value_a", "value_b"):
        label = str(finding.get(f"measure_{field[-1]}", ""))
        if label:
            measures.setdefault(label.casefold(), finding.get(field))
    return measures


def claimed_wuenic_value(finding):
    """The WUENIC value the finding claims, if it claims one."""
    for measure, value in (
        (finding.get("measure_a"), finding.get("value_a")),
        (finding.get("measure_b"), finding.get("value_b")),
    ):
        if "wuenic" in str(measure).casefold():
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def unverified_wuenic_checks(decision):
    checks = (decision.get("critic") or {}).get("source_checks") or []
    matched = []
    for check in checks:
        if check.get("status") != "NOT_VERIFIED":
            continue
        blob = " ".join([
            str(check.get("name", "")),
            str(check.get("url", "")),
        ]).casefold()
        if "unicef" in blob or "wuenic" in blob:
            matched.append(check)
    return matched


def fetch_wuenic_records(base_url=None, timeout=None):
    root = (base_url or DEFAULT_EVIDENCE_API).rstrip("/")
    url = f"{root}/wuenic"
    request = Request(url, headers={"User-Agent": "CrossExaminer/0.1"})
    with urlopen(request, timeout=timeout or EVIDENCE_API_TIMEOUT) as response:
        payload = json.loads(response.read().decode())
    return payload.get("evidence") or []


def plain_text(payload):
    """Very small HTML-to-text helper for source document presence checks."""
    text = _SCRIPT_RE.sub(" ", payload)
    text = _TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_source_document(url, timeout=DOCUMENT_TIMEOUT,
                          max_bytes=MAX_DOCUMENT_BYTES):
    """Fetch a source document that is already attached to a finding.

    Returns a dict describing what was retrieved. Never raises for ordinary
    network problems: the caller decides how to treat a failure.
    """
    result = {
        "status": "NOT_RETRIEVED",
        "content_type": "",
        "bytes": 0,
        "text_excerpt": "",
        "mentions": {},
        "error": None,
    }
    try:
        request = Request(url, headers={"User-Agent": "CrossExaminer/0.1"})
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            data = response.read(max_bytes + 1)
    except (URLError, TimeoutError, OSError) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    if len(data) > max_bytes:
        result["status"] = "TOO_LARGE"
        result["content_type"] = content_type
        return result

    result["status"] = "RETRIEVED"
    result["content_type"] = content_type
    result["bytes"] = len(data)

    if "pdf" not in content_type.casefold() and not data.startswith(b"%PDF"):
        try:
            text = plain_text(data.decode("utf-8", errors="replace"))
        except Exception:
            text = ""
        result["text_excerpt"] = text[:600]
        result["mentions"] = {
            "antigen": "",
            "country": "",
        }
    return result


def _mentions(finding, excerpt):
    antigen = str(finding.get("antigen", "")).casefold()
    country = str(finding.get("country", "")).casefold()
    lowered = excerpt.casefold()
    return {
        "antigen": bool(antigen) and antigen in lowered,
        "country": bool(country) and country in lowered,
    }


def _matching_workbook_row(finding, records):
    """The workbook row that carries the same measure as the finding.

    The row has to be about the same measure: comparing a stored estimate
    with a finding that only carries an administrative figure would be a
    conflict that nobody claimed.
    """
    country = str(finding.get("country", "")).casefold()
    antigen = str(finding.get("antigen", "")).casefold()
    year = str(finding.get("year", ""))
    measures = finding_measures(finding)

    for record in records:
        if (
            str(record.get("country", "")).casefold() == country
            and str(record.get("antigen", "")).casefold() == antigen
            and str(record.get("year", "")) == year
            and str(record.get("measure", "")).casefold() in measures
        ):
            return record
    return None


def _find_check_by_url(decision, url):
    checks = (decision.get("critic") or {}).get("source_checks") or []
    for check in checks:
        if str(check.get("url", "")) == str(url):
            return check
    return None


def _copy_decision(decision):
    critic = decision.get("critic") or {}
    return {
        **decision,
        "critic": {
            **critic,
            "source_checks": list(critic.get("source_checks") or []),
            "limitations": list(critic.get("limitations") or []),
        },
    }


def revise_decision(finding, decision, fetch_records=None, proposal=None,
                    fetch_document=fetch_source_document):
    """If the critic left a WUENIC/UNICEF source unverified, fetch /wuenic.

    Matching extra evidence upgrades that check to EXTRACT_CONSISTENT and
    keeps the original decision. A numeric conflict abstains. A failed fetch
    leaves the original decision in place and records that extra evidence was
    unavailable.

    ``proposal`` is an optional action proposal (see :mod:`src.investigator`).
    Only ``FETCH_WUENIC_WORKBOOK`` and ``FETCH_SOURCE_DOCUMENT`` are
    executable, and a document fetch only ever targets a URL that is already
    attached to the finding.
    """
    if fetch_records is None:
        fetch_records = fetch_wuenic_records
    updated = _copy_decision(decision)
    revision = {
        "action": "NO_ADDITIONAL_EVIDENCE",
        "outcome": "UNCHANGED",
        "stop_reason": "NO_UNVERIFIED_WUENIC_SOURCE",
        "country": finding.get("country"),
        "antigen": finding.get("antigen"),
        "year": finding.get("year"),
        "proposal_source": (proposal or {}).get("source", "deterministic"),
        "proposal_action": (proposal or {}).get("action"),
    }

    targets = unverified_wuenic_checks(updated)
    claimed = claimed_wuenic_value(finding)

    proposed_action = (proposal or {}).get("action")
    proposed_target = (proposal or {}).get("target")

    if proposed_action == "FETCH_SOURCE_DOCUMENT":
        outcome = _retrieve_source_document(
            updated, revision, finding, proposed_target, fetch_document
        )
        updated["revision"] = revision
        return updated, revision

    if proposed_action == "STOP":
        # The investigator decided that no further evidence is worth
        # retrieving. The finding keeps its unverified sources and the
        # decision is untouched.
        revision["action"] = "STOP"
        revision["outcome"] = "STOPPED_BY_PROPOSAL"
        revision["stop_reason"] = "PROPOSAL_STOP"
        updated["revision"] = revision
        return updated, revision

    if proposed_action not in (None, "FETCH_WUENIC_WORKBOOK"):
        # Not executable here: fall back to the deterministic behaviour below.
        revision["proposal_action"] = proposed_action
        revision["proposal_source"] = "rejected"

    if not targets:
        updated["revision"] = revision
        return updated, revision
    if claimed is None:
        revision["stop_reason"] = "NO_WUENIC_CLAIM_IN_FINDING"
        updated["revision"] = revision
        return updated, revision

    revision["action"] = "FETCH_WUENIC"
    try:
        records = fetch_records()
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
        revision["outcome"] = "ADDITIONAL_EVIDENCE_UNAVAILABLE"
        revision["stop_reason"] = f"{type(exc).__name__}: {exc}"
        updated["critic"]["limitations"].append(
            "Additional WUENIC workbook evidence was requested and could not be retrieved."
        )
        updated["revision"] = revision
        return updated, revision

    row = _matching_workbook_row(finding, records)
    if row is None:
        revision["outcome"] = "ABSTAIN"
        revision["stop_reason"] = "WUENIC_WORKBOOK_ROW_NOT_FOUND"
        updated["decision"] = "ABSTAIN"
        updated["reason"] = (
            "The critic flagged an unverified WUENIC/UNICEF source, and the "
            "workbook endpoint had no matching country/antigen/year row."
        )
        updated.pop("recommendation", None)
        updated["revision"] = revision
        return updated, revision

    # The value to compare is the one the finding claims for the measure the
    # workbook row carries.
    measures = finding_measures(finding)
    row_measure = str(row.get("measure", "")).casefold()
    claimed = measures.get(row_measure)
    if claimed is None:
        claimed = claimed_wuenic_value(finding)
    try:
        claimed = float(claimed)
    except (TypeError, ValueError):
        claimed = None

    try:
        workbook_value = float(row["value_percent"])
        matches = (
            claimed is not None
            and abs(workbook_value - claimed) < 0.01
        )
    except (TypeError, ValueError, KeyError):
        matches = False
        workbook_value = row.get("value_percent")

    limitation = (
        "Workbook matching compares the claim with a local WUENIC extract; "
        "it does not prove the estimate is correct or more accurate than "
        "administrative coverage."
    )
    for index, check in enumerate(updated["critic"]["source_checks"]):
        if check is not targets[0] and check.get("name") != targets[0].get("name"):
            continue
        updated["critic"]["source_checks"][index] = {
            **check,
            "status": "EXTRACT_CONSISTENT" if matches else "EXTRACT_CONFLICT",
            "verification_scope": "SELF_CONSISTENCY",
            "table_context_matched": False,
            "matched_values": [{
                "measure": "WUENIC estimate",
                "expected": claimed,
                "table_value": workbook_value,
                "found_in_expected_year_row": matches,
            }],
            "limitations": list(check.get("limitations") or []) + [limitation],
        }
        break

    if matches:
        revision["outcome"] = "REVISED_SOURCE_CHECK"
        revision["stop_reason"] = "EXTRACT_VALUE_MATCHED"
        updated["critic"]["limitations"].append(limitation)
    else:
        revision["outcome"] = "ABSTAIN"
        revision["stop_reason"] = "EXTRACT_VALUE_CONFLICT"
        updated["decision"] = "ABSTAIN"
        updated["reason"] = (
            "Additional WUENIC workbook evidence conflicted with the claimed "
            "estimate, so the finding is withheld."
        )
        updated.pop("recommendation", None)

    updated["revision"] = revision
    return updated, revision


def _retrieve_source_document(updated, revision, finding, target_url,
                              fetch_document):
    """Fetch a source document named by an accepted proposal."""
    if not target_url:
        revision["outcome"] = "ADDITIONAL_EVIDENCE_UNAVAILABLE"
        revision["stop_reason"] = "NO_TARGET_DOCUMENT"
        return updated

    check = _find_check_by_url(updated, target_url)
    if check is None:
        revision["outcome"] = "ADDITIONAL_EVIDENCE_UNAVAILABLE"
        revision["stop_reason"] = "TARGET_NOT_A_KNOWN_SOURCE"
        return updated

    revision["action"] = "FETCH_SOURCE_DOCUMENT"
    document = fetch_document(target_url)

    if document.get("status") != "RETRIEVED":
        revision["outcome"] = "ADDITIONAL_EVIDENCE_UNAVAILABLE"
        revision["stop_reason"] = document.get("error") or document.get("status")
        updated["critic"]["limitations"].append(
            "The source document could not be retrieved, so it remains unverified."
        )
        return updated

    excerpt = document.get("text_excerpt") or ""
    mentions = _mentions(finding, excerpt) if excerpt else {}

    limitation = (
        "Retrieving a source document shows that it exists; it does not "
        "verify the values inside it."
    )

    for index, item in enumerate(updated["critic"]["source_checks"]):
        if str(item.get("url", "")) != str(target_url):
            continue
        previous_status = item.get("status")
        # A workbook conflict is a stronger signal than "the document was
        # retrieved", so it is not overwritten by the retrieval.
        status = (
            "EXTRACT_CONFLICT"
            if previous_status == "EXTRACT_CONFLICT"
            else "SOURCE_DOCUMENT_RETRIEVED"
        )
        updated["critic"]["source_checks"][index] = {
            **item,
            "status": status,
            "verification_scope": "DOCUMENT_PRESENCE",
            "table_context_matched": False,
            "document": {
                "content_type": document.get("content_type"),
                "bytes": document.get("bytes"),
                "mentions": mentions,
                "text_excerpt": excerpt[:300],
            },
            "limitations": list(item.get("limitations") or []) + [limitation],
        }
        break

    updated["critic"]["limitations"].append(limitation)
    revision["outcome"] = "EVIDENCE_RETRIEVED"
    revision["stop_reason"] = "SOURCE_DOCUMENT_RETRIEVED"
    return updated
