"""Deterministic checks on the quality and limits of a finding."""


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
                "details": "A percentage value falls outside 0–100.",
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

        source_checks.append({
            "name": source.get("name", source.get("source", "Unnamed source")),
            "url_present": bool(url),
            "table_context_matched": status == "CONTEXT_MATCHED",
            "status": status,
            **(
                {
                    "table_page": verification.get("table_page"),
                    "matched_values": verification.get("matched_values", []),
                    "limitations": verification.get("limitations", []),
                }
                if verification else {}
            ),
        })

    return {
        "passed": not issues,
        "issues": issues,
        "source_checks": source_checks,
        "limitations": [
            "A URL being present does not verify the source's contents.",
            "A difference between measures does not establish which value is correct.",
        ],
    }