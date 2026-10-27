"""Evidence-based adjudication of the discrepancy under investigation.

The runtime model may propose one of four dispositions for the discrepancy
that is being investigated:

``ACCEPT``
    The discrepancy is confirmed by independently validated evidence. The
    difference between the two published figures is real. This does *not*
    say which of the two figures is correct.
``REJECT``
    The discrepancy is not supported as a material difference.
``REVIEW``
    The discrepancy stands but is not resolved; a human has to look at it.
``ABSTAIN``
    The evidence is missing, weak or contradictory, so nothing is asserted.

The proposal is advisory. :func:`validate_verdict` decides whether the
evidence that the trusted Python code gathered supports the proposal, and
:func:`apply_verdict` only then updates the final disposition. The
deterministic arbiter decision is never rewritten: it stays on the record as
the baseline the proposal was measured against.
"""

from src.evidence_ledger import REVIEW_ITEM_KIND
from src.model_client import (
    ModelInvalidResponse,
    ModelRequestFailed,
    ModelUnavailable,
)

VERDICTS = ("ACCEPT", "REJECT", "REVIEW", "ABSTAIN")

# The review items the arbiter names when it sends a finding to REVIEW:
# "investigate definitions, denominators, reporting quality, and estimation
# methods". Under the project's own semantics these are mandatory conditions
# for leaving REVIEW, not optional follow-up questions.
MANDATORY_REVIEW_ITEMS = (
    "measure_definitions",
    "denominators",
    "reporting_quality",
    "estimation_methodology",
)

DISPOSITION_MEANING = {
    "ACCEPT": (
        "The discrepancy is resolved: the mandatory review items (definitions, "
        "denominators, reporting quality, estimation methodology) are closed "
        "and no further review is needed. This does not establish which of "
        "the two figures is correct."
    ),
    "REJECT": (
        "The discrepancy is not supported as a material difference: the "
        "source's own table shows the same number for both measures. This "
        "does not establish which of the two figures is correct."
    ),
    "REVIEW": (
        "The discrepancy stands but is not resolved; a human has to look at "
        "the definitions, denominators, reporting quality and estimation "
        "methods."
    ),
    "ABSTAIN": (
        "The evidence is missing, weak or contradictory, so no disposition "
        "is asserted."
    ),
}

# How the deterministic arbiter decision maps onto the disposition
# vocabulary. The arbiter's own vocabulary is untouched.
BASELINE_DISPOSITION = {
    "ABSTAIN": "ABSTAIN",
    "REVIEW": "REVIEW",
    "REPORT_OBSERVATION": "REJECT",
}

MAX_REASON_CHARS = 400
MAX_CITATIONS = 6


def build_recommendation(finding, decision):
    """What the evidence says the planner should act on.

    A household survey is measured independently of the administrative
    reporting, so when it disagrees with the administrative figure by more
    than the review threshold it says something the two published figures
    cannot: the administrative number is not the coverage level.

    This does not settle the discrepancy, so the disposition stays REVIEW.
    It tells the planner which number to use for the level and which one
    not to use, and it says where that came from.
    """
    conflicts = (decision.get("critic") or {}).get("conflicts") or []
    if not conflicts:
        return None

    conflict = conflicts[0]
    observations = (decision.get("critic") or {}).get("observations") or []

    survey_source = {}
    for observation in observations:
        if observation.get("measure") == conflict.get("measure_b"):
            survey_source = observation
            break

    lineage = survey_source.get("lineage") or {}

    return {
        "recommended_measure": conflict.get("measure_b"),
        "recommended_value": conflict.get("value_b"),
        "recommended_source": survey_source.get("origin_label"),
        "recommended_source_id": lineage.get("source_id"),
        "not_recommended_measure": conflict.get("measure_a"),
        "not_recommended_value": conflict.get("value_a"),
        "gap_percentage_points": conflict.get("gap_percentage_points"),
        "basis": conflict.get("note"),
        "caveats": [
            "The survey figure is independent of the administrative "
            "reporting, but it was read from a publication that also "
            "carries the administrative line, so it was not re-read from "
            "the survey's own report.",
            "A survey measures a sample of households, not the whole "
            "population, so it carries its own sampling uncertainty.",
            "This is a recommendation for the coverage level, not a claim "
            "that one of the published figures is correct.",
        ],
    }


def baseline_disposition(decision):
    """The disposition implied by the deterministic arbiter decision."""
    decision_value = str(decision.get("decision", "")).strip().upper()
    return BASELINE_DISPOSITION.get(decision_value, "REVIEW")


def _supports(item, verdict):
    """True when the registered evidence supports the proposed verdict."""
    signals = (item.get("detail") or {}).get("signals") or {}
    if verdict == "ACCEPT":
        return bool(signals.get("both_values_confirmed")) and not signals.get(
            "source_values_agree"
        )
    if verdict == "REJECT":
        # A refutation does not need an independent line: the document the
        # claim was taken from showing the same number for both measures is
        # enough to show the recorded discrepancy is not real.
        return bool(signals.get("source_values_agree"))
    return False


def _closed_review_items(ledger):
    """The mandatory review items the evidence actually closes."""
    closed = set()
    for item in ledger.items():
        if item.get("kind") != REVIEW_ITEM_KIND:
            continue
        covers = (item.get("detail") or {}).get("covers") or []
        for entry in covers:
            closed.add(str(entry))
    return closed


def open_review_items(ledger):
    """The mandatory review items that are still open."""
    closed = _closed_review_items(ledger)
    return [item for item in MANDATORY_REVIEW_ITEMS if item not in closed]


def _evidence_note(item):
    """A short factual note about what an evidence item shows."""
    signals = (item.get("detail") or {}).get("signals") or {}
    if not signals:
        return ""
    if signals.get("source_values_agree"):
        return (
            "the source's own table shows the same number for both measures "
            "in this year"
        )
    if signals.get("both_values_confirmed"):
        return (
            "the source's own table confirms both published figures for "
            "this year"
        )
    return "the source's own table confirms only part of the claim"


def verdict_prompt(finding, decision, ledger, challenges=None,
                   memory_context=None):
    """The prompt the runtime model answers with a disposition proposal."""
    critic = decision.get("critic") or {}
    issues = "; ".join(
        f"{issue.get('code')}: {issue.get('details')}"
        for issue in (critic.get("issues") or [])
    ) or "none"

    challenge_lines = []
    for challenge in challenges or []:
        for item in challenge.get("challenges") or []:
            challenge_lines.append(f"- {item}")
        for item in challenge.get("missing_support") or []:
            challenge_lines.append(f"- missing support: {item}")

    memory_lines = []
    for memory in (memory_context or {}).get("memories", []) or []:
        memory_lines.append(
            f"- {memory.get('id')}: {memory.get('content')} "
            "(context only, not independent verification)"
        )

    lines = [
        "You are adjudicating one discrepancy from an evidence investigation.",
        "You may propose a disposition for the discrepancy. You may not "
        "invent evidence, and you may not assert which coverage figure is "
        "correct.",
        "",
        f"Claim: {finding.get('country')} {finding.get('antigen')} "
        f"({finding.get('year')}): {finding.get('measure_a')} "
        f"{finding.get('value_a')}% vs {finding.get('measure_b')} "
        f"{finding.get('value_b')}% "
        f"(gap {finding.get('gap_percentage_points')} percentage points)",
        f"Deterministic decision from the trusted code: {decision.get('decision')} "
        f"- {decision.get('reason')}",
        f"Data-quality issues found by the deterministic critic: {issues}",
        "",
        "Dispositions you may propose (choose exactly one):",
        "  ACCEPT - the discrepancy is confirmed by independently validated "
        "evidence: both published figures were checked against the source's "
        "own table, so the difference between them is real. It says nothing "
        "about which of the two figures is more accurate.",
        "  REJECT - the discrepancy is not supported as a material difference.",
        "  REVIEW - the discrepancy stands, but the evidence does not settle "
        "it; a human has to look at definitions, denominators and estimation "
        "methods.",
        "  ABSTAIN - the evidence is missing, weak or contradictory, so "
        "nothing is asserted.",
        "",
        "Which disposition fits the evidence in front of you:",
        "- The ledger holds an INDEPENDENT_VERIFICATION item that confirms "
        "both published figures for this year, and no source check is in "
        "conflict: the discrepancy is confirmed, so ACCEPT.",
        "- That independent confirmation is missing or only partial, while "
        "the deterministic decision still calls for review: the discrepancy "
        "stands but is not settled, so REVIEW.",
        "- A source check conflicts with the claim or a deterministic check "
        "failed: the evidence is contradictory, so ABSTAIN.",
        "- The source's own table shows the same number for both measures: "
        "the reported difference is not supported, so REJECT.",
        "",
        "Evidence gathered so far. Cite only the ids listed here:",
    ]
    for item in ledger.items():
        note = _evidence_note(item)
        lines.append(
            f"  {item['evidence_id']}: {item['name']} | status={item['status']} "
            f"| scope={item['scope']}"
            + (f" | {note}" if note else "")
            + f" | {item['url']}"
        )
    if not ledger.items():
        lines.append("  (none)")

    lines.extend(["", "Challenges on record:"])
    lines.extend(challenge_lines or ["  none"])

    lines.extend(["", "Retrieved memories (context only):"])
    lines.extend(memory_lines or ["  none retrieved"])

    lines.extend([
        "",
        "Respond with JSON only, in this shape:",
        '{"verdict": "ACCEPT", "reason": "one sentence",',
        ' "evidence": ["ev-1"]}',
    ])
    return "\n".join(lines)


def propose_verdict(client, finding, decision, ledger, challenges=None,
                    memory_context=None, budget=None):
    """Ask the model for a disposition proposal. Advisory only.

    The returned proposal is never applied directly: it still has to pass
    :func:`validate_verdict`.
    """
    proposal = {
        "verdict": None,
        "reason": "",
        "citations": [],
        "source": "deterministic",
        "status": "not_proposed",
        "accepted": False,
        "rejected_reason": "MODEL_NOT_REQUESTED",
        "model": getattr(client, "model", None),
    }

    if client is None:
        return proposal

    if budget is not None and not budget.spend():
        proposal["rejected_reason"] = "CALL_BUDGET_EXHAUSTED"
        return proposal

    try:
        payload = client.chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a careful adjudicator. Reply with JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": verdict_prompt(
                        finding, decision, ledger, challenges, memory_context
                    ),
                },
            ],
            max_tokens=600,
            temperature=0.1,
        )
    except ModelRequestFailed as exc:
        proposal["status"] = "rejected"
        proposal["rejected_reason"] = str(exc)[:MAX_REASON_CHARS]
        return proposal
    except (ModelUnavailable, ModelInvalidResponse) as exc:
        proposal["status"] = "unavailable"
        proposal["rejected_reason"] = str(exc)[:MAX_REASON_CHARS]
        return proposal

    verdict = str(payload.get("verdict", "") or "").strip().upper()
    reason = str(payload.get("reason", "") or "").strip()[:MAX_REASON_CHARS]
    citations = payload.get("evidence")
    if not isinstance(citations, list):
        citations = []
    citations = [
        str(item) for item in citations
        if isinstance(item, (str, int))
    ][:MAX_CITATIONS]

    proposal.update({
        "verdict": verdict or None,
        "reason": reason,
        "citations": citations,
        "source": "model",
        "status": "used",
        "rejected_reason": None,
    })
    return proposal


def validate_verdict(proposal, finding, decision, ledger, threshold=5):
    """Decide whether the gathered evidence supports the proposal.

    Returns ``(accepted, reason)``. This is the deterministic gate: it is
    the only thing that can move the final disposition away from the
    deterministic baseline.
    """
    verdict = str(proposal.get("verdict") or "").strip().upper()
    if not verdict:
        return False, proposal.get("rejected_reason") or "NO_VERDICT_PROPOSED"
    if verdict not in VERDICTS:
        return False, "VERDICT_NOT_ALLOWED"
    if not str(proposal.get("reason") or "").strip():
        return False, "NO_REASON_SUPPLIED"

    citations = proposal.get("citations") or []
    unknown = [item for item in citations if not ledger.has(item)]
    if unknown:
        return False, "CITED_EVIDENCE_NOT_FOUND"

    if verdict == "ABSTAIN":
        # Abstaining never asserts anything, so it is always permitted.
        return True, "ABSTENTION_IS_ALWAYS_PERMITTED"

    if finding.get("synthetic"):
        # Generated records are not evidence. Nothing may be disposed of on
        # them.
        return False, "SYNTHETIC_DATA_IS_NOT_EVIDENCE"

    if baseline_disposition(decision) == "ABSTAIN":
        # The deterministic code already withheld the finding: either a
        # check failed or a numerical conflict is unresolved. A model
        # proposal does not get to overturn that.
        return False, "DETERMINISTIC_ABSTENTION_STANDS"

    if verdict == "REVIEW":
        # REVIEW asserts no resolution either, so it is always permitted.
        return True, "REVIEW_IS_A_PERMITTED_RESOLUTION"

    # ACCEPT and REJECT are claims about the state of the world, so they
    # need evidence behind them.
    if not citations:
        return False, "NO_EVIDENCE_CITED"

    cited = [ledger.get(item) for item in citations]

    try:
        gap = float(finding.get("gap_percentage_points", 0))
    except (TypeError, ValueError):
        gap = 0.0

    if verdict == "ACCEPT":
        if gap < threshold:
            return False, "GAP_BELOW_THRESHOLD"

        # The arbiter sends a threshold-meeting gap to REVIEW to have the
        # definitions, denominators, reporting quality and estimation
        # methods looked at. Leaving REVIEW means those items are closed,
        # and only evidence can close them - not the model's opinion.
        still_open = open_review_items(ledger)
        if still_open:
            return False, "MANDATORY_REVIEW_ITEMS_OPEN"

        independent = [
            item for item in cited
            if item
            and item.get("independent")
            # A review item closes a mandatory review item; it is not a
            # verification of the values themselves.
            and item.get("kind") != REVIEW_ITEM_KIND
        ]
        if not independent:
            return False, "NO_INDEPENDENTLY_VALIDATED_EVIDENCE"
        if not any(_supports(item, verdict) for item in independent):
            return False, f"EVIDENCE_DOES_NOT_SUPPORT_{verdict}"
        return True, "SUPPORTED_BY_INDEPENDENTLY_VALIDATED_EVIDENCE"

    # REJECT: the recorded discrepancy is not real. A refutation from the
    # document the claim was taken from is enough.
    if not any(_supports(item, verdict) for item in cited):
        return False, f"EVIDENCE_DOES_NOT_SUPPORT_{verdict}"
    return True, "SUPPORTED_BY_A_REFUTING_SOURCE"


def apply_verdict(decision, proposal, accepted, reason):
    """Record the adjudication on the decision and return the record.

    The deterministic decision (``decision["decision"]``) is left alone. The
    adjudicated outcome lives in ``decision["disposition"]``. A proposal that
    is rejected, or that was never made, leaves the current disposition
    alone: only a validated proposal may change it.
    """
    baseline = baseline_disposition(decision)
    current = decision.get("disposition") or baseline
    final = current
    if accepted and proposal.get("verdict"):
        final = str(proposal["verdict"]).strip().upper()

    record = {
        "baseline_decision": decision.get("decision"),
        "baseline_disposition": baseline,
        "previous_disposition": current,
        "proposed_verdict": proposal.get("verdict"),
        "proposal_source": proposal.get("source"),
        "proposal_status": proposal.get("status"),
        "reason": proposal.get("reason"),
        "citations": proposal.get("citations") or [],
        "accepted": bool(accepted),
        "validation_reason": reason,
        "final_disposition": final,
        "changed": final != current,
        "differs_from_baseline": final != baseline,
    }

    decision["disposition"] = final
    decision["disposition_meaning"] = DISPOSITION_MEANING.get(
        final, DISPOSITION_MEANING["REVIEW"]
    )
    history = decision.get("adjudications")
    if history is None:
        history = []
        decision["adjudications"] = history
    history.append(record)
    decision["adjudication"] = record
    return decision, record
