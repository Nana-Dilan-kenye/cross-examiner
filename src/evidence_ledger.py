"""Registry of the evidence gathered during one investigation.

Every piece of evidence the coordinator retrieves is registered here with an
identifier, a verification *scope* and a status. The identifier is what makes
a model citation checkable: a proposal may only cite an identifier that this
registry issued, and only evidence with the ``INDEPENDENT_VERIFICATION``
scope may support a positive disposition.

The scope is what keeps the project's evidence discipline intact:

``INDEPENDENT_VERIFICATION``
    The value was checked against the source's own published table.
``SELF_CONSISTENCY``
    The value was compared with the extract the claim came from. This proves
    the extraction path worked; it does not verify the underlying data.
``INDEPENDENT_MEASUREMENT``
    The number comes from a measurement that does not derive from the
    numbers it is compared against - a household survey rather than
    administrative reporting. It is independent evidence about the level.
    It is not a verification of the other numbers, and on its own it does
    not settle a claim.
``DOCUMENT_PRESENCE``
    The document was retrieved so it could be inspected. Its contents are
    still unverified.
``CONTEXT_ONLY``
    Context. Context is never treated as proof.
"""

SCOPE_INDEPENDENT = "INDEPENDENT_VERIFICATION"
SCOPE_SELF_CONSISTENCY = "SELF_CONSISTENCY"
SCOPE_INDEPENDENT_MEASUREMENT = "INDEPENDENT_MEASUREMENT"
SCOPE_DOCUMENT_PRESENCE = "DOCUMENT_PRESENCE"
SCOPE_CONTEXT_ONLY = "CONTEXT_ONLY"

SCOPE_MEANING = {
    SCOPE_INDEPENDENT: (
        "Checked against the source's own published table; this is "
        "independent verification of the values."
    ),
    SCOPE_SELF_CONSISTENCY: (
        "Compared with the extract the claim came from; this is a "
        "self-consistency check, not independent verification."
    ),
    SCOPE_INDEPENDENT_MEASUREMENT: (
        "Produced by a different measurement process (household sampling "
        "rather than administrative reporting); independent evidence about "
        "the level, not a verification of the other numbers."
    ),
    SCOPE_DOCUMENT_PRESENCE: (
        "The document was retrieved so it could be inspected; its contents "
        "are not verified."
    ),
    SCOPE_CONTEXT_ONLY: (
        "Context only. Context is never treated as proof."
    ),
}

SCOPE_FOR_STATUS = {
    "CONTEXT_MATCHED": SCOPE_INDEPENDENT,
    "PARTIAL_MATCH": SCOPE_INDEPENDENT,
    "EXTRACT_CONSISTENT": SCOPE_SELF_CONSISTENCY,
    "EXTRACT_CONFLICT": SCOPE_SELF_CONSISTENCY,
    "SOURCE_DOCUMENT_RETRIEVED": SCOPE_DOCUMENT_PRESENCE,
}

# The kind of evidence item that closes one of the mandatory review items
# the arbiter names. Nothing in the current toolset produces such an item,
# so a finding cannot leave REVIEW until one does.
REVIEW_ITEM_KIND = "REVIEW_ITEM"

# Statuses that mean "the document behind this source is already in hand".
DOCUMENT_HELD_STATUSES = (
    "CONTEXT_MATCHED",
    "PARTIAL_MATCH",
    "SOURCE_DOCUMENT_RETRIEVED",
)


def scope_for_status(status):
    """Verification scope implied by a source-check status."""
    return SCOPE_FOR_STATUS.get(status, SCOPE_CONTEXT_ONLY)


def check_signals(check):
    """Deterministic signals extracted from one source check.

    ``both_values_confirmed``
        The source's own table confirms both published figures, so the
        difference between them is a real, published difference.
    ``source_values_agree``
        The source's own table shows the same number for both measures in
        the expected year, so the reported discrepancy is not supported.
    """
    matched = check.get("matched_values") or []
    by_field = {
        str(item.get("field")): item
        for item in matched
        if isinstance(item, dict)
    }
    first = by_field.get("value_a")
    second = by_field.get("value_b")

    both = bool(
        first
        and second
        and first.get("found_in_expected_year_row")
        and second.get("found_in_expected_year_row")
    )

    agree = False
    if first and second:
        try:
            agree = float(first.get("table_value")) == float(second.get("table_value"))
        except (TypeError, ValueError):
            agree = False

    return {
        "both_values_confirmed": both,
        "source_values_agree": agree,
    }


class EvidenceLedger:
    """Append-only registry of the evidence used in one investigation."""

    def __init__(self):
        self._items = []
        self._ids = set()
        self._by_key = {}

    def register(self, kind, name, url="", status="", scope=SCOPE_CONTEXT_ONLY,
                 detail=None, finding=None, key=None):
        """Register one evidence item and return its identifier.

        ``key`` makes registration idempotent: registering the same evidence
        again updates the item in place and returns the identifier issued
        the first time. That keeps the ledger describing the *current* state
        of the evidence while the coordinator re-analyses the same finding.
        """
        if key is not None and key in self._by_key:
            item = self.get(self._by_key[key])
            item.update({
                "name": name or item["name"],
                "url": url or item["url"],
                "status": status,
                "scope": scope,
                "independent": scope == SCOPE_INDEPENDENT,
                "detail": detail if detail is not None else item["detail"],
            })
            if finding is not None and finding not in item["findings"]:
                # One source document can back several findings, so the
                # item keeps every finding that refers to it.
                item["findings"].append(finding)
            return item["evidence_id"]

        item = {
            "evidence_id": f"ev-{len(self._items) + 1}",
            "kind": kind,
            "name": name,
            "url": url,
            "status": status,
            "scope": scope,
            "independent": scope == SCOPE_INDEPENDENT,
            "findings": [finding] if finding is not None else [],
            "detail": detail or {},
        }
        self._items.append(item)
        self._ids.add(item["evidence_id"])
        if key is not None:
            self._by_key[key] = item["evidence_id"]
        return item["evidence_id"]

    def has(self, evidence_id):
        """True when this registry issued the identifier."""
        return str(evidence_id) in self._ids

    def get(self, evidence_id):
        """The registered item, or None."""
        for item in self._items:
            if item["evidence_id"] == str(evidence_id):
                return item
        return None

    def items(self):
        """All registered items, in registration order."""
        return list(self._items)

    def independent_items(self):
        """Items whose verification scope is independent verification."""
        return [item for item in self._items if item["independent"]]

    def summary(self):
        """Ledger content without the bulky detail payloads."""
        return [
            {
                "evidence_id": item["evidence_id"],
                "kind": item["kind"],
                "name": item["name"],
                "url": item["url"],
                "status": item["status"],
                "scope": item["scope"],
                "findings": list(item["findings"]),
            }
            for item in self._items
        ]

    def fingerprint(self):
        """Stable digest of the ledger contents."""
        parts = [
            f"{item['evidence_id']}|{item['kind']}|{item['name']}|"
            f"{item['url']}|{item['status']}|{item['scope']}"
            for item in self._items
        ]
        return "|".join(parts)


def register_source_checks(ledger, decision, finding=None):
    """Register the source checks of a decision as evidence items."""
    ids = []
    for check in (decision.get("critic") or {}).get("source_checks") or []:
        status = check.get("status", "")
        # The critic decides the scope by provenance; the status map is only
        # a fallback for checks that carry no scope of their own.
        scope = check.get("verification_scope") or scope_for_status(status)
        detail = {
            "scope_meaning": check.get("scope_note") or SCOPE_MEANING[scope],
            "table_page": check.get("table_page"),
        }
        if status in ("CONTEXT_MATCHED", "PARTIAL_MATCH"):
            # The signals describe what the source's own table shows. The
            # scope decides whether that may support a positive disposition.
            detail["signals"] = check_signals(check)
        lineage = check.get("lineage")
        if lineage:
            detail["lineage"] = lineage
        ids.append(ledger.register(
            kind="SOURCE_CHECK",
            name=check.get("name", ""),
            url=check.get("url", ""),
            status=status,
            scope=scope,
            detail=detail,
            finding=finding,
            key=("SOURCE_CHECK", check.get("url", "")),
        ))
    return ids


def register_conflicts(ledger, decision, finding=None):
    """Register the conflicts between lines that do not share an upstream."""
    ids = []
    for conflict in (decision.get("critic") or {}).get("conflicts") or []:
        ids.append(ledger.register(
            kind="CONFLICT",
            name=(
                f"{conflict.get('code')} "
                f"{conflict.get('country', '')} "
                f"{conflict.get('antigen', '')} "
                f"{conflict.get('year', '')}: "
                f"{conflict.get('measure_a')} {conflict.get('value_a')} "
                f"vs {conflict.get('measure_b')} {conflict.get('value_b')}"
            ),
            status="CONFLICT_DETECTED",
            scope=SCOPE_INDEPENDENT_MEASUREMENT,
            detail={
                "code": conflict.get("code"),
                "gap_percentage_points": conflict.get("gap_percentage_points"),
                "origin_a": conflict.get("origin_a"),
                "origin_b": conflict.get("origin_b"),
                "note": conflict.get("note"),
                "scope_meaning": SCOPE_MEANING[SCOPE_INDEPENDENT_MEASUREMENT],
            },
            finding=finding,
            key=("CONFLICT", conflict.get("code"), str(finding)),
        ))
    return ids


def independent_measurements(ledger):
    """Ledger items that come from a measurement independent of the others."""
    return [item for item in ledger.items() if item.get("scope") == SCOPE_INDEPENDENT_MEASUREMENT]
