"""Contextual checks for claims against PDF table rows."""

import copy
import io
import re
import unicodedata
from urllib.request import Request, urlopen

from pypdf import PdfReader

YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
VALUE_RE = re.compile(r"(?<![\w.])(?:\d+(?:\.\d+)?|NA)(?![\w.])", re.I)

# The country profiles are large PDFs and the same document is checked
# again on every investigation iteration. The result depends only on the
# URL and the claim, so it is cached for the lifetime of the process.
_VERIFICATION_CACHE = {}


def norm(value):
    value = unicodedata.normalize("NFKD", str(value)).casefold()
    value = value.replace("ﬃ", "ffi").replace("ﬁ", "fi").replace("ﬂ", "fl")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def measure_row(label):
    label = norm(label)
    if "administrative" in label:
        return "administrative"
    if "survey" in label:
        return "survey"
    if "official" in label:
        return "official"
    if "estimate" in label or "wuenic" in label:
        return "estimate"
    return None

def parse_table(text):
    lines = [re.sub(r"\s+", " ", line).strip()
             for line in text.splitlines()]

    years = None
    for line in lines:
        found = YEAR_RE.findall(line)
        if (
            len(found) == 12
            and len(set(found)) == 12
            and all(2010 <= int(y) <= 2035 for y in found)
        ):
            years = found
            break

    if years is None:
        return [], {}

    rows = {}
    for line in lines:
        normalized = norm(line)

        if normalized.startswith("estimate goc"):
            continue

        label = None
        for candidate in ("administrative", "official", "survey", "estimate"):
            if normalized == candidate or normalized.startswith(candidate + " "):
                label = candidate
                break

        if not label:
            continue

        remainder = re.sub(r"^[^\s]+\s*", "", line, count=1)
        values = VALUE_RE.findall(remainder)

        # Accept only rows with exactly one value per year.
        if len(values) == len(years):
            rows[label] = values

    return years, rows


def verify_pdf_source(url, finding, timeout=20,
                      max_bytes=15 * 1024 * 1024):
    country = norm(finding.get("country", ""))
    antigen = norm(finding.get("antigen", ""))
    year = str(finding.get("year", ""))
    cache_key = (url, country, antigen, year)

    if cache_key in _VERIFICATION_CACHE:
        return copy.deepcopy(_VERIFICATION_CACHE[cache_key])

    result = verify_pdf_source_uncached(
        url, finding, timeout=timeout, max_bytes=max_bytes
    )
    _VERIFICATION_CACHE[cache_key] = copy.deepcopy(result)
    return result


def clear_verification_cache():
    """Drop the cached PDF verifications (used by the tests)."""
    _VERIFICATION_CACHE.clear()


def comparisons_for(finding):
    """The (field, measure, expected value) triples to check in a table.

    A finding may carry more than the two numbers it was built on: a
    household-survey line is a third reported number for the same country,
    antigen and year, and it lives in the same table.
    """
    comparisons = []
    for observation in finding.get("observations") or []:
        field = observation.get("field")
        measure = observation.get("measure")
        value = observation.get("value")
        if not field or not measure:
            continue
        comparisons.append((field, measure, value))

    if not comparisons:
        comparisons = [
            (
                "value_a",
                finding.get("measure_a", "WUENIC estimate"),
                finding.get("value_a"),
            ),
            (
                "value_b",
                finding.get("measure_b", "Administrative coverage"),
                finding.get("value_b"),
            ),
        ]
    return comparisons


def verify_pdf_source_uncached(url, finding, timeout=20,
                               max_bytes=15 * 1024 * 1024):
    result = {
        "url": url,
        "status": "NOT_VERIFIED",
        "table_context_found": False,
        "checks": {},
        "matched_values": [],
        "limitations": [
            "Text matching does not validate the underlying data.",
            "PDF extraction can fail or reorder table values.",
            "A match does not establish which measure is more accurate.",
        ],
    }

    try:
        request = Request(url, headers={"User-Agent": "CrossExaminer/0.1"})
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            data = response.read(max_bytes + 1)

        if len(data) > max_bytes:
            result["status"] = "DOCUMENT_TOO_LARGE"
            return result
        if "pdf" not in content_type.casefold() and not data.startswith(b"%PDF"):
            result["status"] = "NOT_A_PDF"
            return result

        pdf = PdfReader(io.BytesIO(data))
        country = norm(finding.get("country", ""))
        antigen = norm(finding.get("antigen", ""))
        year = str(finding.get("year", ""))

        if not country or not antigen or not year:
            result["status"] = "MISSING_CLAIM_FIELDS"
            return result

        tables = []
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            heading = norm(text.splitlines()[0]) if text.splitlines() else ""

            if country not in heading or antigen not in heading:
                continue

            years, rows = parse_table(text)
            
            if (
                year in years
                and "estimate" in rows
                and "administrative" in rows
                and len(years) == 12
            ):
                tables.append((page_number, years, rows))

        if len(tables) != 1:
            result["status"] = (
                "AMBIGUOUS_TABLE" if tables else "TABLE_NOT_FOUND"
            )
            return result

        page_number, years, rows = tables[0]
        year_index = years.index(year)
        result["table_context_found"] = True
        result["table_page"] = page_number
        result["checks"] = {
            "country": True,
            "antigen": True,
            "year": True,
        }

        comparisons = comparisons_for(finding)
        all_match = True

        for field, description, expected in comparisons:
            row = measure_row(description)
            values = rows.get(row) if row else None
            actual = values[year_index] if values and year_index < len(values) else None

            try:
                matches = (
                    actual is not None
                    and actual.upper() != "NA"
                    and float(actual) == float(expected)
                )
            except (TypeError, ValueError):
                matches = False

            result["matched_values"].append({
                "field": field,
                "measure": description,
                "table_row": row,
                "expected": expected,
                "table_value": actual,
                "found_in_expected_year_row": matches,
            })
            all_match = all_match and matches

        result["checks"]["measure_rows_match"] = all_match
        result["status"] = "CONTEXT_MATCHED" if all_match else "PARTIAL_MATCH"

    except Exception as exc:
        result["status"] = "VERIFICATION_ERROR"
        result["error"] = f"{type(exc).__name__}: {exc}"

    return result
