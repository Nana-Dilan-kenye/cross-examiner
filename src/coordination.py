"""Bounded, adaptive investigation coordinator.

The coordinator owns the loop. It is not a fixed pipeline: after each
iteration it looks at the current state of the investigation - the evidence
that is in hand, the challenges that were raised, the deterministic checks
and the model's proposal - and decides what the next step should be. A step
may go back to an earlier stage (retrieve more evidence, re-evaluate a
claim) or it may stop.

Every model proposal is structured, checked against an allowlist, and
executed only by the trusted Python code in this module. The model can pick
*which* permitted action to run and can propose a disposition, but it cannot
name an action that is not on the allowlist, cannot name a URL that is not
already attached to the finding, and cannot cite evidence that was never
registered.

The loop is bounded three ways: a maximum number of iterations, the shared
model-call budget, and a set of state guards that stop the investigation
when it repeats itself or when no permitted action can help.
"""

import hashlib

from src.adjudicator import (
    DISPOSITION_MEANING,
    apply_verdict,
    baseline_disposition,
    propose_verdict,
    validate_verdict,
)
from src.arbiter import arbitrate, compare_with_memory
from src.critic import merge_source_checks
from src.evidence_ledger import (
    DOCUMENT_HELD_STATUSES,
    EvidenceLedger,
    register_conflicts,
    register_source_checks,
)
from src.findings import finding_key, finding_label
from src.investigator import challenge_claim, propose_actions
from src import revision
from src.revision import fetch_source_document, revise_decision

DEFAULT_MAX_ITERATIONS = 4

RESOLVED_DISPOSITIONS = ("ACCEPT", "REJECT")


# ---------------------------------------------------------------------------
# state inspection helpers
# ---------------------------------------------------------------------------


def _is_wuenic_check(check):
    """True when the check belongs to a WUENIC/UNICEF source."""
    blob = " ".join([
        str(check.get("name", "")),
        str(check.get("url", "")),
    ]).casefold()
    return "wuenic" in blob or "unicef" in blob


def _executed(state, key, action):
    """True when this action was already run for this finding."""
    return any(
        entry[0] == key and entry[1] == action
        for entry in state.executed_set
    )


def _document_targets(state, key):
    """Source URLs whose document is not in hand yet."""
    finding = state.findings[key]
    decision = state.decisions.get(key) or {}
    checks = (decision.get("critic") or {}).get("source_checks") or []
    held = {
        str(check.get("url", ""))
        for check in checks
        if check.get("status") in DOCUMENT_HELD_STATUSES
    }
    targets = []
    for source in finding.get("sources", []):
        url = str(source.get("url") or "").strip()
        if not url or url in held:
            continue
        if (key, "FETCH_SOURCE_DOCUMENT", url) in state.executed_set:
            continue
        targets.append(url)
    return targets


def _field_for_measure(finding, check):
    """Which side of the finding a workbook-style check covers."""
    measure = ""
    for item in check.get("matched_values") or []:
        if isinstance(item, dict) and item.get("measure"):
            measure = str(item["measure"]).casefold()
            break
    if "wuenic" in measure or "estimate" in measure:
        return "value_a"
    return "value_b"


def _verified_fields(state, key):
    """The finding fields that some source check actually confirms."""
    finding = state.findings[key]
    decision = state.decisions.get(key) or {}
    checks = (decision.get("critic") or {}).get("source_checks") or []
    fields = set()
    for check in checks:
        status = check.get("status")
        if status in ("CONTEXT_MATCHED", "PARTIAL_MATCH"):
            for item in check.get("matched_values") or []:
                if not isinstance(item, dict):
                    continue
                if item.get("found_in_expected_year_row"):
                    fields.add(str(item.get("field")))
        elif status == "EXTRACT_CONSISTENT":
            fields.add(_field_for_measure(finding, check))
    return fields


def _all_values_verified(state, key):
    """True when both published values are confirmed by some check."""
    fields = _verified_fields(state, key)
    return "value_a" in fields and "value_b" in fields


def _challenge_wants_support(state, key):
    """True when the recorded challenge asks for evidence that is missing."""
    challenge = state.challenges.get(key) or {}
    if challenge.get("source") != "model":
        return False
    if challenge.get("would_change_verdict"):
        return True
    return bool(challenge.get("missing_support"))


def permitted_actions(state, key):
    """Actions the trusted executor can still usefully run for this finding.

    The list is derived from the current evidence state, so it shrinks as
    evidence arrives. That is what keeps the loop from re-fetching the same
    document and from looping over the same work.
    """
    decision = state.decisions.get(key) or {}
    checks = (decision.get("critic") or {}).get("source_checks") or []
    actions = []

    # What an earlier investigation left behind comes first. If this
    # country, antigen and year already had the administrative figure
    # contradicted by a household measurement, the survey evidence is
    # what this run has to look at.
    recalled = (state.decisions.get(key) or {}).get("memory_recall") or {}
    preferred = recalled.get("preferred_action")
    target = recalled.get("preferred_target") or ""

    if (
        preferred == "FETCH_SOURCE_DOCUMENT"
        and _document_targets(state, key)
        and not _executed(state, key, "FETCH_SOURCE_DOCUMENT")
    ):
        actions.append("FETCH_SOURCE_DOCUMENT")

    if (
        any(
            _is_wuenic_check(check) and check.get("status") == "NOT_VERIFIED"
            for check in checks
        )
        and not _executed(state, key, "FETCH_WUENIC_WORKBOOK")
    ):
        actions.append("FETCH_WUENIC_WORKBOOK")

    if _document_targets(state, key) and not _executed(
        state, key, "FETCH_SOURCE_DOCUMENT"
    ):
        actions.append("FETCH_SOURCE_DOCUMENT")

    if not _all_values_verified(state, key) and not _executed(
        state, key, "QUERY_ZETARIS"
    ):
        actions.append("QUERY_ZETARIS")

    if _challenge_wants_support(state, key) and not _executed(
        state, key, "QUERY_HMEM"
    ):
        actions.append("QUERY_HMEM")

    # A recalled conflict can also make the generic document-target rule
    # append FETCH_SOURCE_DOCUMENT; keep the action list deterministic and
    # free of duplicate names.
    return list(dict.fromkeys(actions))


def choose_next_action(state, key, proposal):
    """Decide the next step for one finding.

    A model proposal wins when it names an action that is permitted and was
    not already run. Otherwise the coordinator picks from the permitted set,
    preferring the step that answers the challenge that was raised.
    """
    permitted = permitted_actions(state, key)
    targets = _document_targets(state, key)

    if proposal and proposal.get("source") == "model" and proposal.get("accepted"):
        action = str(proposal.get("action") or "").strip().upper()
        if action == "STOP":
            return {
                "action": "STOP",
                "target": None,
                "reason": "The model judged that no further evidence is worth "
                          "retrieving.",
                "source": "model",
            }
        if action in permitted:
            target = None
            if action == "FETCH_SOURCE_DOCUMENT":
                target = proposal.get("target")
                if target not in targets:
                    target = targets[0] if targets else None
            return {
                "action": action,
                "target": target,
                "reason": proposal.get("reason") or "Proposed by the model.",
                "source": "model",
            }

    if "FETCH_SOURCE_DOCUMENT" in permitted and _challenge_wants_support(state, key):
        return {
            "action": "FETCH_SOURCE_DOCUMENT",
            "target": targets[0] if targets else None,
            "reason": "A challenge asked for support that is not in the "
                      "evidence yet.",
            "source": "deterministic",
        }

    # What an earlier investigation left behind takes precedence over the
    # generic first step: the survey evidence is what this run has to look
    # at when the conflict was seen before.
    recalled = (state.decisions.get(key) or {}).get("memory_recall") or {}
    if recalled.get("preferred_action") == "FETCH_SOURCE_DOCUMENT":
        target = recalled.get("preferred_target") or ""
        if target not in targets:
            target = targets[0] if targets else None
        if target:
            return {
                "action": "FETCH_SOURCE_DOCUMENT",
                "target": target,
                "reason": (
                    "An earlier investigation of this country, antigen and "
                    "year found the administrative figure far above an "
                    "independent household measurement, so the survey "
                    "evidence is checked first."
                ),
                "source": "memory",
            }

    if "FETCH_WUENIC_WORKBOOK" in permitted:
        return {
            "action": "FETCH_WUENIC_WORKBOOK",
            "target": None,
            "reason": "A WUENIC/UNICEF source is still unverified.",
            "source": "deterministic",
        }

    if "FETCH_SOURCE_DOCUMENT" in permitted:
        return {
            "action": "FETCH_SOURCE_DOCUMENT",
            "target": targets[0] if targets else None,
            "reason": "A source document for this finding has not been "
                      "retrieved yet.",
            "source": "deterministic",
        }

    if "QUERY_HMEM" in permitted:
        return {
            "action": "QUERY_HMEM",
            "target": None,
            "reason": "Prior observations may still corroborate the claim.",
            "source": "deterministic",
        }

    if "QUERY_ZETARIS" in permitted:
        return {
            "action": "QUERY_ZETARIS",
            "target": None,
            "reason": "A published value is not corroborated yet.",
            "source": "deterministic",
        }

    return {
        "action": "STOP",
        "target": None,
        "reason": "No permitted action remains for this finding.",
        "source": "deterministic",
    }


# ---------------------------------------------------------------------------
# execution (trusted Python only)
# ---------------------------------------------------------------------------


def _revision_record(key, finding, action, reason, source):
    return {
        "action": action,
        "outcome": "UNCHANGED",
        "stop_reason": reason,
        "country": finding.get("country"),
        "antigen": finding.get("antigen"),
        "year": finding.get("year"),
        "proposal_source": source,
        "proposal_action": action,
    }


def _query_zetaris(state, key):
    """Re-query the evidence store for this finding's country/antigen/year."""
    finding = state.findings[key]
    decision = state.decisions[key]
    revision = _revision_record(
        key, finding, "QUERY_ZETARIS",
        "Re-queried the evidence store for the same country, antigen and year.",
        "deterministic",
    )

    try:
        records = state.zetaris_fetcher()
    except Exception as exc:  # the store is optional; the loop continues
        revision["outcome"] = "ADDITIONAL_EVIDENCE_UNAVAILABLE"
        revision["stop_reason"] = f"{type(exc).__name__}: {exc}"
        state.ledger.register(
            kind="ZETARIS_QUERY",
            name="Evidence store re-query",
            status="UNAVAILABLE",
            scope="CONTEXT_ONLY",
            detail={"error": revision["stop_reason"]},
            finding=key,
            key=("ZETARIS", key, "UNAVAILABLE"),
        )
        return decision, revision

    row = _matching_record(finding, records)
    if row is None:
        revision["outcome"] = "NO_MATCHING_RECORD"
        revision["stop_reason"] = "ZETARIS_ROW_NOT_FOUND"
        state.ledger.register(
            kind="ZETARIS_QUERY",
            name="Evidence store re-query",
            status="NO_MATCHING_RECORD",
            scope="CONTEXT_ONLY",
            finding=key,
            key=("ZETARIS", key, "NO_MATCHING_RECORD"),
        )
        return decision, revision

    try:
        stored = float(row.get("value_percent"))
    except (TypeError, ValueError):
        stored = None

    claimed = _claimed_value(finding, row.get("measure"))

    if claimed is None:
        revision["outcome"] = "NO_MATCHING_RECORD"
        revision["stop_reason"] = "ZETARIS_ROW_MEASURE_NOT_IN_FINDING"
        state.ledger.register(
            kind="ZETARIS_QUERY",
            name="Evidence store re-query",
            status="NO_MATCHING_RECORD",
            scope="CONTEXT_ONLY",
            finding=key,
            key=("ZETARIS", key, "NO_MATCHING_RECORD"),
        )
        return decision, revision

    matches = (
        stored is not None
        and abs(stored - claimed) < 0.01
    )

    status = "EXTRACT_CONSISTENT" if matches else "EXTRACT_CONFLICT"
    scope = "SELF_CONSISTENCY"
    state.ledger.register(
        kind="ZETARIS_QUERY",
        name=f"Evidence store row for {finding.get('country')} "
             f"{finding.get('antigen')} {finding.get('year')}",
        url=row.get("source_url", ""),
        status=status,
        scope=scope,
        detail={
            "stored_value": stored,
            "claimed_value": claimed,
            "found_in_expected_year_row": matches,
            "scope_meaning": "Compared with the store the claim came from; "
                             "this is a self-consistency check, not "
                             "independent verification.",
        },
        finding=key,
        key=("ZETARIS", key, status),
    )

    if matches:
        revision["outcome"] = "EVIDENCE_RETRIEVED"
        revision["stop_reason"] = "ZETARIS_VALUE_MATCHED"
        return decision, revision

    revision["outcome"] = "ABSTAIN"
    revision["stop_reason"] = "ZETARIS_VALUE_CONFLICT"
    updated = dict(decision)
    updated["decision"] = "ABSTAIN"
    updated["withheld_by_deterministic_check"] = True
    updated["reason"] = (
        "The evidence store returned a different value for the same measure, "
        "so the finding is withheld."
    )
    updated.setdefault("critic", {}).setdefault("limitations", []).append(
        "A re-query of the evidence store disagreed with the claimed value."
    )
    return updated, revision


def _finding_measures(finding):
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


def _matching_record(finding, records):
    """Find the stored row that matches one finding's claim.

    The row has to carry the same measure as one of the finding's
    observations: a stored estimate cannot be compared with a finding that
    only carries an administrative figure.
    """
    country = str(finding.get("country", "")).casefold()
    antigen = str(finding.get("antigen", "")).casefold()
    year = str(finding.get("year", ""))
    measures = _finding_measures(finding)

    for record in records or []:
        if (
            str(record.get("country", "")).casefold() == country
            and str(record.get("antigen", "")).casefold() == antigen
            and str(record.get("year", "")) == year
            and str(record.get("measure", "")).casefold() in measures
        ):
            return record
    return None


def _claimed_value(finding, measure):
    """The value the finding claims for one measure."""
    measures = _finding_measures(finding)
    value = measures.get(str(measure or "").casefold())
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _query_hmem(state, key):
    """Retrieve prior observations for this finding from the memory store."""
    finding = state.findings[key]
    decision = state.decisions[key]
    question = (
        f"{finding.get('country')} {finding.get('antigen')} "
        f"{finding.get('year')} coverage discrepancy"
    )
    revision = _revision_record(
        key, finding, "QUERY_HMEM",
        "Retrieved prior observations for the same topic and year.",
        "deterministic",
    )

    try:
        context = state.memory_fetcher(question)
    except Exception as exc:  # the memory store is optional
        revision["outcome"] = "ADDITIONAL_EVIDENCE_UNAVAILABLE"
        revision["stop_reason"] = f"{type(exc).__name__}: {exc}"
        state.ledger.register(
            kind="MEMORY",
            name="Prior observations",
            status="UNAVAILABLE",
            scope="CONTEXT_ONLY",
            detail={"error": revision["stop_reason"]},
            finding=key,
            key=("MEMORY", key, "UNAVAILABLE"),
        )
        return decision, revision

    memories = (context or {}).get("memories") or []
    state.memory_contexts[key] = context
    state.ledger.register(
        kind="MEMORY",
        name=f"Prior observations for {finding.get('country')} "
             f"{finding.get('antigen')} {finding.get('year')}",
        status="RETRIEVED" if memories else "NO_MATCHES",
        scope="CONTEXT_ONLY",
        detail={
            "memory_ids": [memory.get("id") for memory in memories],
            "scope_meaning": "Context only. Context is never treated as proof.",
        },
        finding=key,
        key=("MEMORY", key, "RETRIEVED" if memories else "NO_MATCHES"),
    )

    updated = dict(decision)
    updated["memory_comparison"] = compare_with_memory(finding, context)
    revision["outcome"] = "CONTEXT_RETRIEVED"
    revision["stop_reason"] = (
        "MEMORIES_RETRIEVED" if memories else "NO_MATCHING_MEMORY"
    )
    return updated, revision


def _mark_withheld(updated, revision):
    """Remember that the deterministic code withheld this finding.

    A later revision step must not quietly undo a numerical conflict, so
    the coordinator carries the flag forward itself.
    """
    if (
        updated.get("decision") == "ABSTAIN"
        and revision.get("outcome") == "ABSTAIN"
    ):
        updated["withheld_by_deterministic_check"] = True
    return updated


def execute_action(state, key, choice, proposal):
    """Run one allow-listed action with trusted Python code."""
    finding = state.findings[key]
    decision = state.decisions[key]
    action = choice["action"]
    source = choice.get("source", "deterministic")
    reason = choice.get("reason") or ""

    if action == "FETCH_WUENIC_WORKBOOK":
        updated, revision = revise_decision(
            finding,
            decision,
            fetch_records=state.workbook_fetcher,
            proposal={
                "action": action,
                "target": None,
                "reason": reason,
                "source": source,
                "accepted": True,
            },
        )
        revision["coordinator_action"] = action
        if revision.get("outcome") == "ADDITIONAL_EVIDENCE_UNAVAILABLE":
            state.source_failures[key] = {
                "action": action,
                "target": None,
                "error": revision.get("stop_reason"),
            }
            state.ledger.register(
                kind="WORKBOOK_FETCH",
                name="WUENIC workbook extract",
                status="NOT_RETRIEVED",
                scope="CONTEXT_ONLY",
                detail={"error": revision.get("stop_reason")},
                finding=key,
                key=("WORKBOOK_FETCH", key, "NOT_RETRIEVED"),
            )
        return _mark_withheld(updated, revision), revision

    if action == "FETCH_SOURCE_DOCUMENT":
        updated, revision = revise_decision(
            finding,
            decision,
            fetch_document=state.document_fetcher,
            proposal={
                "action": action,
                "target": choice.get("target"),
                "reason": reason,
                "source": source,
                "accepted": True,
            },
        )
        revision["coordinator_action"] = action
        if revision.get("outcome") == "ADDITIONAL_EVIDENCE_UNAVAILABLE":
            state.source_failures[key] = {
                "action": action,
                "target": choice.get("target"),
                "error": revision.get("stop_reason"),
            }
            state.ledger.register(
                kind="DOCUMENT_FETCH",
                name=f"Source document {choice.get('target') or ''}".strip(),
                url=choice.get("target") or "",
                status="NOT_RETRIEVED",
                scope="DOCUMENT_PRESENCE",
                detail={"error": revision.get("stop_reason")},
                finding=key,
                key=("DOCUMENT_FETCH", choice.get("target"), "NOT_RETRIEVED"),
            )
        return _mark_withheld(updated, revision), revision

    if action == "QUERY_ZETARIS":
        updated, revision = _query_zetaris(state, key)
        revision["coordinator_action"] = action
        return updated, revision

    if action == "QUERY_HMEM":
        updated, revision = _query_hmem(state, key)
        revision["coordinator_action"] = action
        return updated, revision

    revision = _revision_record(key, finding, "STOP", reason, source)
    revision["outcome"] = "STOPPED"
    revision["coordinator_action"] = "STOP"
    return decision, revision


# ---------------------------------------------------------------------------
# re-analysis
# ---------------------------------------------------------------------------


def _reanalyze(state, key):
    """Re-run the deterministic checks and keep the upgraded statuses."""
    finding = state.findings[key]
    previous = state.decisions.get(key) or {}
    fresh = arbitrate(finding, state.threshold, state.memory_context)

    fresh_critic = fresh.get("critic") or {}
    previous_critic = previous.get("critic") or {}
    fresh_critic = merge_source_checks(fresh_critic, previous_critic)

    limitations = list(fresh_critic.get("limitations") or [])
    for item in previous_critic.get("limitations") or []:
        if item not in limitations:
            limitations.append(item)
    fresh_critic["limitations"] = limitations
    fresh["critic"] = fresh_critic

    previous_revision = previous.get("revision") or {}
    if previous.get("withheld_by_deterministic_check"):
        # A numerical conflict or a missing workbook row already forced the
        # abstention. Re-analysis must not quietly undo it.
        fresh["decision"] = "ABSTAIN"
        fresh["reason"] = previous.get("reason")
        fresh["withheld_by_deterministic_check"] = True

    if previous_revision:
        fresh["revision"] = previous_revision
    if previous.get("adjudications"):
        fresh["adjudications"] = previous["adjudications"]
    if previous.get("withheld_by_deterministic_check"):
        fresh["withheld_by_deterministic_check"] = True

    return fresh


def _challenge_basis(state, key):
    """Digest of the decision a challenge was made against."""
    decision = state.decisions.get(key) or {}
    checks = (decision.get("critic") or {}).get("source_checks") or []
    return "|".join([
        str(decision.get("decision")),
        str(decision.get("disposition")),
        ",".join(str(check.get("status")) for check in checks),
    ])


def _uncertainties(state, key):
    """What is still uncertain about this finding."""
    decision = state.decisions.get(key) or {}
    checks = (decision.get("critic") or {}).get("source_checks") or []
    items = []

    for check in checks:
        status = check.get("status")
        name = check.get("name") or "a source"
        if status == "NOT_VERIFIED":
            items.append(
                f"'{name}' was never verified against its own published source."
            )
        elif status == "SOURCE_DOCUMENT_RETRIEVED":
            items.append(
                f"The document behind '{name}' was retrieved but its values "
                f"were not checked."
            )
        elif status in ("EXTRACT_CONSISTENT", "EXTRACT_CONFLICT"):
            items.append(
                f"'{name}' was only compared with the extract the claim came "
                f"from (self-consistency, not independent verification)."
            )
        elif status == "PARTIAL_MATCH":
            items.append(
                f"Only part of '{name}' matched the expected table row."
            )

    challenge = state.challenges.get(key) or {}
    for item in challenge.get("missing_support") or []:
        items.append(f"Missing support: {item}")

    if not items:
        items.append(
            "The gap between the two measures is not explained by the checks "
            "that were run; definitions, denominators and estimation methods "
            "still need a human look."
        )
    return items


# ---------------------------------------------------------------------------
# the coordinator
# ---------------------------------------------------------------------------


class InvestigationState:
    """Everything the coordinator knows at one point in the investigation."""

    def __init__(self, question, findings, decisions, threshold, budget,
                 max_iterations=DEFAULT_MAX_ITERATIONS, fetch_records=None,
                 fetch_document=None, zetaris_fetcher=None, memory_fetcher=None,
                 ledger=None):
        self.question = question
        self.threshold = threshold
        self.budget = budget
        self.max_iterations = max(0, int(max_iterations))
        self.findings = {finding_key(f): f for f in findings}
        self.decisions = {
            finding_key(f): d for f, d in zip(findings, decisions)
        }
        self.challenges = {}
        self.challenge_basis = {}
        # The evidence registry. It can be handed in already holding evidence
        # that closes the mandatory review items, which is how a finding can
        # leave REVIEW.
        self.ledger = ledger if ledger is not None else EvidenceLedger()
        self.iterations = []
        self.revisions = []
        self.proposals = []
        self.executed_set = set()
        self.executed_actions = []
        self.state_fingerprints = set()
        self.concluded = {}
        self.source_failures = {}
        self.memory_context = None
        self.memory_contexts = {}
        self.workbook_records = None
        self.workbook_failed = False
        self.stop_reason = None
        self.stop_detail = None
        self._fetch_records = fetch_records
        self._fetch_document = fetch_document
        self._zetaris_fetcher = zetaris_fetcher
        self._memory_fetcher = memory_fetcher
        self.trace = None

    # -- executors ---------------------------------------------------------

    def workbook_fetcher(self):
        """Fetch the WUENIC workbook extract once and reuse it."""
        if self.workbook_records is None and not self.workbook_failed:
            fetcher = self._fetch_records or revision.fetch_wuenic_records
            try:
                self.workbook_records = fetcher()
            except Exception:
                self.workbook_failed = True
                raise
        if self.workbook_records is None:
            raise OSError(
                "The WUENIC workbook extract was already requested and could "
                "not be retrieved."
            )
        return self.workbook_records

    def document_fetcher(self, url):
        fetcher = self._fetch_document or fetch_source_document
        return fetcher(url)

    def zetaris_fetcher(self):
        from src.zetaris_source import load_records
        fetcher = self._zetaris_fetcher or load_records
        return fetcher()

    def memory_fetcher(self, question):
        from src.memory_bridge import query
        fetcher = self._memory_fetcher or query
        return fetcher(question)

    # -- state -------------------------------------------------------------

    def active_keys(self):
        return [key for key in self.findings if key not in self.concluded]

    def fingerprint(self):
        """Digest of the meaningful investigation state.

        Two iterations that reach the same fingerprint did not learn
        anything new, so the loop stops instead of going round again.
        """
        parts = []
        for key in sorted(self.findings):
            decision = self.decisions.get(key) or {}
            checks = (decision.get("critic") or {}).get("source_checks") or []
            challenge = self.challenges.get(key) or {}
            parts.append("~".join([
                "|".join(str(part) for part in key),
                str(decision.get("decision")),
                str(decision.get("disposition")),
                ",".join(str(check.get("status")) for check in checks),
                str(challenge.get("source")),
                str(challenge.get("would_change_verdict")),
            ]))
        parts.append(self.ledger.fingerprint())
        return hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()[:16]

    def all_resolved(self):
        if not self.decisions:
            return True
        return all(
            (self.decisions.get(key) or {}).get("disposition")
            in RESOLVED_DISPOSITIONS
            for key in self.decisions
        )

    def unresolved_keys(self):
        """Findings that no disposition has settled."""
        return [
            key for key in self.findings
            if (self.decisions.get(key) or {}).get("disposition")
            not in RESOLVED_DISPOSITIONS
        ]

    def close_reason(self, key):
        """Why a finding stopped being investigated."""
        return (self.concluded.get(key) or {}).get("reason")

    def close_cause(self, key):
        """The cause that closed a finding."""
        return (self.concluded.get(key) or {}).get("cause")

    def final_stop(self):
        """The reason the investigation stopped, and what it means.

        The three end states are kept apart:

        ``EVIDENCE_SUFFICIENT``
            Every finding was resolved: the evidence settled it.
        ``SOURCES_UNAVAILABLE`` / ``*_BUDGET_EXHAUSTED``
            A finding is still uncertain but was safely closed because its
            evidence could not be retrieved or the budget ran out.
        ``REPEATED_STATE`` / ``NO_USEFUL_NEXT_ACTION``
            The investigation stopped while some findings were still open.
        """
        unresolved = self.unresolved_keys()

        if not unresolved:
            return (
                "EVIDENCE_SUFFICIENT",
                "Every finding was resolved by the evidence that was gathered.",
            )

        labels = ", ".join(
            finding_label(self.findings[key]) for key in unresolved
        )
        open_note = (
            f"{len(unresolved)} finding(s) are still open: {labels}."
        )

        # A budget is a hard bound on the investigation, so it is reported
        # first.
        if self.stop_reason in (
            "ITERATION_BUDGET_EXHAUSTED",
            "MODEL_CALL_BUDGET_EXHAUSTED",
        ):
            return (
                self.stop_reason,
                f"{open_note} {self.stop_detail or ''}".strip(),
            )

        if self.budget.remaining() <= 0:
            return (
                "MODEL_CALL_BUDGET_EXHAUSTED",
                f"{open_note} The shared model-call budget was exhausted, so "
                f"the investigation stopped instead of continuing without the "
                f"model. {self.stop_detail or ''}".strip(),
            )

        # Evidence that could not be retrieved explains why the findings are
        # still uncertain, so it is reported before the proximate cause.
        blocked = [
            key for key in unresolved
            if key in self.source_failures
        ]
        if blocked:
            details = "; ".join(
                f"{finding_label(self.findings[key])}: "
                f"{self.source_failures[key].get('error')}"
                for key in blocked
            )
            return (
                "SOURCES_UNAVAILABLE",
                f"{open_note} They were closed because their evidence could "
                f"not be retrieved ({details}). "
                f"{self.stop_detail or ''}".strip(),
            )

        if self.stop_reason == "REPEATED_STATE":
            return (
                self.stop_reason,
                f"{open_note} {self.stop_detail or ''}".strip(),
            )

        return (
            "NO_USEFUL_NEXT_ACTION",
            f"No permitted action was left for {open_note}",
        )


def investigate(question, findings, decisions, client, budget, threshold=5,
                memory_context=None, max_iterations=DEFAULT_MAX_ITERATIONS,
                fetch_records=None, fetch_document=None, zetaris_fetcher=None,
                memory_fetcher=None, ledger=None, trace=None):
    """Run the bounded iterative investigation.

    Returns the decisions (aligned with ``findings``), the iteration trace,
    the evidence ledger, the revisions, the challenges and the reason the
    investigation stopped.
    """
    state = InvestigationState(
        question,
        findings,
        decisions,
        threshold,
        budget,
        max_iterations,
        fetch_records=fetch_records,
        fetch_document=fetch_document,
        zetaris_fetcher=zetaris_fetcher,
        memory_fetcher=memory_fetcher,
        ledger=ledger,
    )
    state.memory_context = memory_context
    state.trace = trace

    if state.trace is not None:
        state.trace.event(
            "investigation.started",
            question=question,
            findings=[
                {
                    "country": finding.get("country"),
                    "antigen": finding.get("antigen"),
                    "year": finding.get("year"),
                    "gap_percentage_points": finding.get("gap_percentage_points"),
                }
                for finding in findings
            ],
        )
        for key, decision in state.decisions.items():
            recalled = decision.get("memory_recall") or {}
            if recalled.get("memory_ids"):
                state.trace.agent(
                    "memory",
                    "recall.prior_findings",
                    target_agent="investigator",
                    input_summary=finding_label(state.findings[key]),
                    output_summary=recalled.get("effect"),
                    status="recalled",
                    memory_ids=recalled.get("memory_ids"),
                    prior_conflict=bool(recalled.get("has_prior_conflict")),
                    changed_action=recalled.get("preferred_action"),
                )

    for key, decision in state.decisions.items():
        register_source_checks(state.ledger, decision, key)
        register_conflicts(state.ledger, decision, key)
        # Every decision carries a disposition from the start, so a run that
        # never reaches the adjudication step still reports one.
        decision["disposition"] = baseline_disposition(decision)
        decision["disposition_meaning"] = DISPOSITION_MEANING.get(
            decision["disposition"], DISPOSITION_MEANING["REVIEW"]
        )

    iteration = 0
    while iteration < state.max_iterations:
        iteration += 1
        active = state.active_keys()
        record = {
            "iteration": iteration,
            "active_findings": [finding_label(state.findings[k]) for k in active],
            "proposed": [],
            "next_steps": [],
            "rejected_proposals": [],
            "executed": [],
            "challenges": [],
            "adjudications": [],
            "state_fingerprint": None,
            "stop_reason": None,
        }

        if not active:
            record["stop_reason"] = "EVIDENCE_SUFFICIENT"
            state.iterations.append(record)
            break

        # 1. PLAN ------------------------------------------------------------
        permitted = {key: permitted_actions(state, key) for key in active}
        plan = propose_actions(
            client,
            question,
            [state.findings[key] for key in active],
            {key: state.decisions[key] for key in active},
            budget=budget,
            permitted=permitted,
            challenges=state.challenges,
        )
        state.proposals.extend(plan.get("proposals", []))
        proposals_by_key = {}
        for proposal in plan.get("proposals", []):
            proposals_by_key[(
                str(proposal.get("country", "")),
                str(proposal.get("antigen", "")),
                str(proposal.get("year", "")),
            )] = proposal
        record["plan_status"] = plan.get("status")
        record["plan_note"] = plan.get("note")
        if state.trace is not None:
            for key in active:
                proposal = proposals_by_key.get(key) or {}
                state.trace.agent(
                    "investigator",
                    f"plan.{str(proposal.get('action') or 'none').lower()}",
                    target_agent="critic",
                    input_summary=finding_label(state.findings[key]),
                    output_summary=proposal.get("reason"),
                    confidence=0.6 if proposal.get("source") == "model" else None,
                    status="proposed",
                    iteration=iteration,
                    proposed_by=proposal.get("source"),
                    target=proposal.get("target"),
                    permitted=permitted.get(key),
                )
        record["proposed"] = [
            {
                "finding": finding_label(state.findings[key]),
                "action": (proposals_by_key.get(key) or {}).get("action"),
                "source": (proposals_by_key.get(key) or {}).get("source"),
                "accepted": (proposals_by_key.get(key) or {}).get("accepted"),
                "fallback_reason": (proposals_by_key.get(key) or {}).get(
                    "fallback_reason"
                ),
                "reason": (proposals_by_key.get(key) or {}).get("reason"),
            }
            for key in active
        ]
        for proposal in plan.get("proposals", []):
            if not proposal.get("accepted"):
                record["rejected_proposals"].append({
                    "finding": finding_label(state.findings[key]) if key in state.findings else "",
                    "action": proposal.get("action"),
                    "rejected_action": proposal.get("rejected_action"),
                    "fallback_reason": proposal.get("fallback_reason"),
                })

        # 2. NEXT STEP + EXECUTE -------------------------------------------
        for key in active:
            proposal = proposals_by_key.get(key)
            choice = choose_next_action(state, key, proposal)
            record["next_steps"].append({
                "finding": finding_label(state.findings[key]),
                "action": choice["action"],
                "source": choice["source"],
                "reason": choice["reason"],
            })

            if choice["action"] == "STOP":
                state.concluded[key] = {
                    "reason": choice["reason"],
                    "cause": (
                        "SOURCE_UNAVAILABLE"
                        if key in state.source_failures else "NO_ACTION"
                    ),
                }
                continue

            updated, revision = execute_action(state, key, choice, proposal)
            state.decisions[key] = updated
            state.revisions.append(revision)
            state.executed_set.add((key, choice["action"], choice.get("target")))
            state.executed_actions.append({
                "iteration": iteration,
                "finding": finding_label(state.findings[key]),
                "action": choice["action"],
                "target": choice.get("target"),
                "source": choice["source"],
                "reason": choice["reason"],
                "outcome": revision.get("outcome"),
                "stop_reason": revision.get("stop_reason"),
            })
            record["executed"].append(dict(state.executed_actions[-1]))
            if state.trace is not None:
                executed = state.executed_actions[-1]
                state.trace.agent(
                    "investigator",
                    f"execute.{str(executed.get('action') or 'none').lower()}",
                    target_agent="critic",
                    input_summary=executed.get("finding"),
                    output_summary=executed.get("outcome"),
                    status=(
                        "ok"
                        if executed.get("outcome") not in (
                            "ADDITIONAL_EVIDENCE_UNAVAILABLE", "ABSTAIN",
                        )
                        else "failed"
                    ),
                    iteration=iteration,
                    stop_reason=executed.get("stop_reason"),
                )

        # 3. RE-ANALYSE ------------------------------------------------------
        for key in active:
            if key in state.concluded:
                continue
            state.decisions[key] = _reanalyze(state, key)
            register_source_checks(state.ledger, state.decisions[key], key)
            register_conflicts(state.ledger, state.decisions[key], key)
            if state.trace is not None:
                checks = (
                    state.decisions[key].get("critic") or {}
                ).get("source_checks") or []
                scopes = {
                    check.get("verification_scope") for check in checks
                }
                state.trace.agent(
                    "critic",
                    "verify.sources",
                    target_agent="arbiter",
                    input_summary=finding_label(state.findings[key]),
                    output_summary=(
                        f"{len(checks)} source check(s): "
                        + ", ".join(sorted(str(s) for s in scopes if s))
                    ),
                    confidence=(
                        0.9 if "INDEPENDENT_VERIFICATION" in scopes
                        else 0.6 if "INDEPENDENT_MEASUREMENT" in scopes
                        else 0.4
                    ),
                    iteration=iteration,
                    decision=state.decisions[key].get("decision"),
                    conflicts=len(
                        (state.decisions[key].get("critic") or {})
                        .get("conflicts") or []
                    ),
                )

        # 4. CHALLENGE -------------------------------------------------------
        for key in active:
            if key in state.concluded:
                continue
            basis = _challenge_basis(state, key)
            previous = state.challenges.get(key)
            if previous and state.challenge_basis.get(key) == basis:
                # The decision did not change, so the challenge still stands
                # and does not need to be raised again.
                record["challenges"].append({
                    "finding": finding_label(state.findings[key]),
                    "source": previous.get("source"),
                    "challenges": previous.get("challenges") or [],
                    "missing_support": previous.get("missing_support") or [],
                    "would_change_verdict": previous.get("would_change_verdict"),
                    "fallback_reason": previous.get("fallback_reason"),
                    "reused": True,
                })
                continue
            challenge = challenge_claim(
                client,
                state.findings[key],
                state.decisions[key],
                state.memory_context,
                budget=budget,
            )
            challenge.update({
                "country": state.findings[key].get("country"),
                "antigen": state.findings[key].get("antigen"),
                "year": state.findings[key].get("year"),
            })
            state.challenges[key] = challenge
            state.challenge_basis[key] = basis
            if state.trace is not None:
                state.trace.agent(
                    "critic",
                    "challenge.claim",
                    target_agent=(
                        "investigator"
                        if challenge.get("would_change_verdict")
                        else "arbiter"
                    ),
                    input_summary=finding_label(state.findings[key]),
                    output_summary="; ".join(
                        challenge.get("challenges") or []
                    )[:400],
                    status="raised",
                    iteration=iteration,
                    would_change_verdict=challenge.get("would_change_verdict"),
                    missing_support=challenge.get("missing_support") or [],
                )
            record["challenges"].append({
                "finding": finding_label(state.findings[key]),
                "source": challenge.get("source"),
                "challenges": challenge.get("challenges") or [],
                "missing_support": challenge.get("missing_support") or [],
                "would_change_verdict": challenge.get("would_change_verdict"),
                "fallback_reason": challenge.get("fallback_reason"),
                "reused": False,
            })

        # 5. ADJUDICATE ------------------------------------------------------
        for key in active:
            if key in state.concluded:
                continue
            decision = state.decisions[key]
            proposal = propose_verdict(
                client,
                state.findings[key],
                decision,
                state.ledger,
                challenges=[state.challenges[key]] if key in state.challenges else [],
                memory_context=state.memory_context,
                budget=budget,
            )
            accepted, reason = validate_verdict(
                proposal,
                state.findings[key],
                decision,
                state.ledger,
                state.threshold,
            )
            if state.trace is not None:
                state.trace.agent(
                    "adjudicator",
                    "adjudicate.verdict",
                    target_agent="reporter",
                    input_summary=(
                        f"{proposal.get('verdict')}: "
                        f"{proposal.get('reason', '')[:200]}"
                    ),
                    output_summary=(
                        f"{decision.get('disposition')} ({reason})"
                    ),
                    confidence=1.0 if accepted else 0.5,
                    status="accepted" if accepted else "rejected",
                    iteration=iteration,
                    verdict=proposal.get("verdict"),
                    citations=proposal.get("citations") or [],
                    proposed_by=proposal.get("source"),
                )
            updated, adjudication = apply_verdict(decision, proposal, accepted, reason)
            state.decisions[key] = updated
            record["adjudications"].append({
                "finding": finding_label(state.findings[key]),
                "baseline_decision": adjudication["baseline_decision"],
                "baseline_disposition": adjudication["baseline_disposition"],
                "proposed_verdict": adjudication["proposed_verdict"],
                "accepted": adjudication["accepted"],
                "validation_reason": adjudication["validation_reason"],
                "final_disposition": adjudication["final_disposition"],
                "reason": adjudication["reason"],
                "citations": adjudication["citations"],
            })
            if adjudication["final_disposition"] in RESOLVED_DISPOSITIONS:
                state.concluded[key] = {
                    "reason": (
                        "The discrepancy was resolved by the evidence that "
                        "was gathered."
                    ),
                    "cause": "RESOLVED",
                }

        # 6. STOP CHECKS -----------------------------------------------------
        fingerprint = state.fingerprint()
        record["state_fingerprint"] = fingerprint
        record["model_calls"] = budget.calls

        if fingerprint in state.state_fingerprints:
            record["stop_reason"] = "REPEATED_STATE"
            state.stop_reason = "REPEATED_STATE"
            state.stop_detail = (
                "The investigation reached the same state twice, so it was "
                "stopped instead of looping."
            )
            state.iterations.append(record)
            break
        state.state_fingerprints.add(fingerprint)

        state.iterations.append(record)

        if budget.remaining() <= 0:
            # The model can no longer contribute, so the investigation stops
            # here rather than going round again without it.
            state.stop_reason = "MODEL_CALL_BUDGET_EXHAUSTED"
            state.stop_detail = (
                "The shared model-call budget was exhausted, so the "
                "investigation stopped instead of continuing without the "
                "model."
            )
            break

        if not state.active_keys():
            # The end state is derived after the loop, so the reason matches
            # what the findings actually are.
            state.stop_detail = "Every finding was closed."
            break

    if state.stop_reason is None:
        if state.max_iterations <= 0:
            state.stop_reason = "ITERATION_BUDGET_EXHAUSTED"
            state.stop_detail = (
                "The iteration budget was zero, so the investigation did not "
                "start."
            )
        elif iteration >= state.max_iterations and state.active_keys():
            state.stop_reason = "ITERATION_BUDGET_EXHAUSTED"
            state.stop_detail = (
                f"The investigation reached its limit of {state.max_iterations} "
                f"iterations while findings were still open."
            )

    # The end state is derived last, so the reason always matches what the
    # findings actually are: resolved, closed-with-uncertainty, or still open.
    reason, detail = state.final_stop()
    state.stop_reason = reason
    state.stop_detail = detail

    if budget.remaining() <= 0 and "budget" not in (state.stop_detail or ""):
        state.stop_detail = (
            (state.stop_detail + " ") if state.stop_detail else ""
        ) + "The shared model-call budget was exhausted."

    uncertainties = {}
    for key in state.findings:
        uncertainties[finding_label(state.findings[key])] = _uncertainties(state, key)

    closing = {
        finding_label(state.findings[key]): {
            "cause": state.close_cause(key),
            "reason": state.close_reason(key),
            "disposition": (state.decisions.get(key) or {}).get("disposition"),
        }
        for key in state.findings
    }

    return {
        "decisions": [state.decisions.get(finding_key(f), {}) for f in findings],
        "revisions": state.revisions,
        "iterations": state.iterations,
        "ledger": state.ledger.summary(),
        "challenges": [
            state.challenges[key]
            for key in state.challenges
        ],
        "proposals": state.proposals,
        "executed_actions": state.executed_actions,
        "closing": closing,
        "stop_reason": state.stop_reason,
        "stop_detail": state.stop_detail,
        "uncertainties": uncertainties,
        "model_calls": budget.calls,
    }
