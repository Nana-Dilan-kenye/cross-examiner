"""Model-driven investigation layer for Cross-Examiner.

The runtime model may do two things:

* propose which evidence should be gathered next, and
* critique a claim that the deterministic pipeline produced.

Both are advisory. A proposal is only executed when it names an action on
the fixed allowlist below *and* resolves to evidence the trusted Python code
already knows about (a source URL that is attached to the finding). The model
never chooses a URL from thin air, never changes a number, and never changes
a decision: the arbiter in :mod:`src.arbiter` is untouched by this module.

The allowlist is the set of tools the trusted executor can actually run:

``FETCH_WUENIC_WORKBOOK``
    Compare the claimed WUENIC estimate with the local workbook extract.
``FETCH_SOURCE_DOCUMENT``
    Retrieve one of the source documents already attached to the finding.
``QUERY_ZETARIS``
    Re-query the evidence store for the same country, antigen and year.
``QUERY_HMEM``
    Retrieve prior observations for the same topic and year.
``STOP``
    No further evidence is worth retrieving.

The coordinator (:mod:`src.coordination`) passes the actions that are still
*permitted* for a finding in the current state. Those are authoritative, so
the model can never ask for work that was already done, and a proposal for
an action that is not permitted is rejected with a recorded reason.

When the runtime is unreachable, slow, or answers with something unusable,
every function here falls back to a deterministic result and says so.
"""

from src.model_client import (
    ModelInvalidResponse,
    ModelRequestFailed,
    ModelUnavailable,
)

ALLOWED_ACTIONS = (
    "FETCH_WUENIC_WORKBOOK",
    "FETCH_SOURCE_DOCUMENT",
    "QUERY_ZETARIS",
    "QUERY_HMEM",
    "STOP",
)

MAX_REASON_CHARS = 400
MAX_LIST_ITEMS = 6
MAX_ITEM_CHARS = 300


class CallBudget:
    """Bounded number of model calls for one investigation run."""

    def __init__(self, max_calls=4):
        self.max_calls = max(0, int(max_calls))
        self.calls = 0

    def spend(self):
        """Reserve one call. False when the budget is exhausted."""
        if self.calls >= self.max_calls:
            return False
        self.calls += 1
        return True

    def remaining(self):
        return max(0, self.max_calls - self.calls)


# ---------------------------------------------------------------------------
# deterministic fallbacks
# ---------------------------------------------------------------------------


def _unverified_sources(finding, decision):
    checks = (decision.get("critic") or {}).get("source_checks") or []
    return [
        check for check in checks
        if check.get("status") == "NOT_VERIFIED" and check.get("url")
    ]


def _wuenic_sources(finding, decision):
    out = []
    for check in _unverified_sources(finding, decision):
        blob = " ".join([
            str(check.get("name", "")),
            str(check.get("url", "")),
        ]).casefold()
        if "wuenic" in blob or "unicef" in blob:
            out.append(check)
    return out


def available_actions(finding, decision, extra=()):
    """Actions the trusted executor can actually perform for this finding."""
    actions = []
    if _wuenic_sources(finding, decision):
        actions.append("FETCH_WUENIC_WORKBOOK")
    if any(source.get("url") for source in finding.get("sources", [])):
        actions.append("FETCH_SOURCE_DOCUMENT")
    for action in extra:
        if action in ALLOWED_ACTIONS and action not in actions:
            actions.append(action)
    actions.append("STOP")
    return actions


def default_proposal(finding, decision):
    """The deterministic next action.

    What an earlier investigation left behind comes first: if this
    country, antigen and year already had the administrative figure
    contradicted by a household measurement, the survey evidence is
    checked before the estimate is re-read.
    """
    recalled = (decision or {}).get("memory_recall") or {}

    if recalled.get("preferred_action") == "FETCH_SOURCE_DOCUMENT":
        target = recalled.get("preferred_target") or ""
        return {
            "country": finding.get("country"),
            "antigen": finding.get("antigen"),
            "year": finding.get("year"),
            "action": "FETCH_SOURCE_DOCUMENT",
            "target": target or None,
            "reason": (
                "An earlier investigation of this country, antigen and year "
                "found the administrative figure far above an independent "
                "household measurement, so the survey evidence is checked "
                "first."
            ),
            "source": "memory",
            "accepted": True,
            "rejected_action": None,
            "fallback_reason": None,
        }

    actions = available_actions(finding, decision)
    if "FETCH_WUENIC_WORKBOOK" in actions:
        action = "FETCH_WUENIC_WORKBOOK"
        reason = (
            "A WUENIC/UNICEF source is still unverified, so the workbook "
            "extract is compared against the claimed value."
        )
    else:
        action = "STOP"
        reason = "No further evidence retrieval is available for this finding."

    return {
        "country": finding.get("country"),
        "antigen": finding.get("antigen"),
        "year": finding.get("year"),
        "action": action,
        "target": None,
        "reason": reason,
        "source": "deterministic",
        "accepted": True,
        "rejected_action": None,
        "fallback_reason": None,
    }


def default_challenge(finding, decision):
    """Deterministic critique built from the existing critic output."""
    critic = decision.get("critic") or {}
    challenges = []
    for issue in critic.get("issues", []) or []:
        code = issue.get("code", "ISSUE")
        details = issue.get("details", "")
        challenges.append(f"{code}: {details}".strip())

    if not challenges:
        challenges.append(
            "The evidence record is internally consistent; the gap between the "
            "two measures is unexplained by the checks that were run."
        )

    return {
        "challenges": challenges[:MAX_LIST_ITEMS],
        "missing_support": [
            "No independent document confirms either value.",
        ],
        "would_change_verdict": False,
        "summary": (
            f"Deterministic challenge for {finding.get('country')} "
            f"{finding.get('antigen')} ({finding.get('year')})."
        ),
        "source": "deterministic",
        "status": "fallback",
        "fallback_reason": "MODEL_NOT_USED",
    }


# ---------------------------------------------------------------------------
# model calls
# ---------------------------------------------------------------------------


def _plan_prompt(question, findings, decisions, permitted=None, challenges=None):
    allowed = ["FETCH_WUENIC_WORKBOOK", "FETCH_SOURCE_DOCUMENT"]
    if permitted:
        for actions in permitted.values():
            for action in actions:
                if action not in allowed and action != "STOP":
                    allowed.append(action)
    else:
        allowed.append("QUERY_ZETARIS")
        allowed.append("QUERY_HMEM")

    lines = [
        "You are the investigator in an evidence investigation. For each "
        "finding, choose the single most useful next evidence-gathering "
        "action.",
        "",
        "Allowed actions (choose exactly one per finding):",
        "  FETCH_WUENIC_WORKBOOK - compare the claimed WUENIC estimate with the "
        "local WUENIC workbook extract.",
        "  FETCH_SOURCE_DOCUMENT - retrieve one of the listed source documents "
        "so its content can be inspected.",
    ]
    for action in allowed:
        if action in ("FETCH_WUENIC_WORKBOOK", "FETCH_SOURCE_DOCUMENT"):
            continue
        if action == "QUERY_ZETARIS":
            lines.append(
                "  QUERY_ZETARIS - re-query the evidence store for the same "
                "country, antigen and year."
            )
        elif action == "QUERY_HMEM":
            lines.append(
                "  QUERY_HMEM - retrieve prior observations for this topic and "
                "year from the memory store."
            )
        else:
            lines.append(f"  {action} - {action.lower().replace('_', ' ')}.")
    lines.append(
        "  STOP - no further evidence is worth retrieving."
    )

    lines += [
        "",
        f"Investigation question: {question}",
        "",
        "Findings:",
    ]
    for finding in findings:
        lines.append(
            f"- {finding.get('country')} {finding.get('antigen')} "
            f"({finding.get('year')}): {finding.get('measure_a')} "
            f"{finding.get('value_a')}% vs {finding.get('measure_b')} "
            f"{finding.get('value_b')}%, gap "
            f"{finding.get('gap_percentage_points')} percentage points"
        )
        lines.append("  sources:")
        for source in finding.get("sources", []):
            lines.append(
                f"    - {source.get('name', 'Unnamed source')} | "
                f"{source.get('url') or 'no URL'}"
            )
        key = (
            str(finding.get("country", "")),
            str(finding.get("antigen", "")),
            str(finding.get("year", "")),
        )
        decision = (decisions or {}).get(key) or (decisions or {}).get(
            str(finding.get("year", ""))
        ) or {}
        lines.append(
            f"  current deterministic decision: {decision.get('decision', 'UNKNOWN')}"
        )
        allowed_here = None
        if permitted is not None:
            allowed_here = permitted.get(key)
        if allowed_here is not None:
            lines.append(
                "  actions still permitted here: "
                + (", ".join(allowed_here) if allowed_here else "none")
            )
        recalled = (decision.get("memory_recall") or {})
        if recalled.get("effect"):
            lines.append(
                "  what earlier investigations of this country, antigen "
                "and year found: " + recalled["effect"]
            )
        challenge = (challenges or {}).get(key)
        if challenge:
            for item in challenge.get("challenges") or []:
                lines.append(f"  challenge raised: {item}")
            for item in challenge.get("missing_support") or []:
                lines.append(f"  missing support: {item}")

    lines += [
        "",
        "Do not decide which coverage figure is correct. Do not invent URLs.",
        "Respond with JSON only, in this shape:",
        '{"actions": [{"country": "Cameroon", "antigen": "MCV1",',
        ' "year": "2020", "action": "FETCH_WUENIC_WORKBOOK",',
        ' "target": "the source name or URL to fetch, or null",',
        ' "reason": "one sentence"}]}',
    ]
    return "\n".join(lines)


def _parse_action_entries(payload):
    entries = payload.get("actions")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _entry_matches(entry, finding):
    """True when a model entry is about this finding.

    The model may name only the year; when it names a country or an antigen
    those have to match.
    """
    country = str(entry.get("country") or "").strip().casefold()
    antigen = str(entry.get("antigen") or "").strip().casefold()
    if country and country != str(finding.get("country", "")).casefold():
        return False
    if antigen and antigen != str(finding.get("antigen", "")).casefold():
        return False
    return True


def _match_source(finding, target):
    """Resolve a model-supplied target to a source already on the finding."""
    if not target:
        return None
    wanted = str(target).strip().casefold()
    for source in finding.get("sources", []):
        url = str(source.get("url") or "").strip()
        name = str(source.get("name") or "").strip()
        if wanted and (wanted == url.casefold() or wanted == name.casefold()):
            return source
    return None


def propose_actions(client, question, findings, decisions, max_calls=4,
                    budget=None, permitted=None, challenges=None):
    """Ask the model for the next evidence-gathering action per finding.

    Returns a dict with the raw proposals and the fallbacks that were used.
    Any proposal that is not on the allowlist, or that names a target the
    finding does not already contain, is rejected in favour of the
    deterministic action for that finding.

    ``permitted`` is the state-derived allowlist for each finding: the
    actions the trusted executor can still run. When it is given it is
    authoritative, so the model can never ask for work that was already
    done.
    """
    if budget is None:
        budget = CallBudget(max_calls)
    result = {
        "status": "used",
        "model": getattr(client, "model", None),
        "calls": 0,
        "max_calls": budget.max_calls,
        "proposals": [],
        "note": None,
    }

    if client is None:
        result["status"] = "disabled"
        result["note"] = "MODEL_NOT_REQUESTED"
    elif not budget.spend():
        result["status"] = "disabled"
        result["note"] = "CALL_BUDGET_EXHAUSTED"
    else:
        result["calls"] = 1
        try:
            payload = client.chat_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are a careful evidence investigator. "
                            "Reply with JSON only."
                        ),
                    },
                    {
                        "role": "user",
                        "content": _plan_prompt(
                            question, findings, decisions, permitted, challenges
                        ),
                    },
                ],
                max_tokens=700,
                temperature=0.1,
            )
        except ModelRequestFailed as exc:
            # The runtime answered with an error (for example the requested
            # model is not served). Another transport would fail the same way.
            result["status"] = "rejected"
            result["note"] = str(exc)[:MAX_REASON_CHARS]
        except (ModelUnavailable, ModelInvalidResponse) as exc:
            result["status"] = "unavailable"
            result["note"] = str(exc)[:MAX_REASON_CHARS]

    entries = []
    if result["status"] == "used":
        entries = _parse_action_entries(payload)
        if not entries:
            result["status"] = "fallback"
            result["note"] = "MODEL_RETURNED_NO_ACTIONS"

    by_year = {}
    for entry in entries:
        by_year.setdefault(str(entry.get("year", "")), []).append(entry)

    for finding in findings:
        year = str(finding.get("year", ""))
        key = (
            str(finding.get("country", "")),
            str(finding.get("antigen", "")),
            year,
        )
        # Decisions may be keyed by the full finding key or by year alone.
        decision = decisions.get(key) or decisions.get(year) or {}
        candidates = [
            entry for entry in by_year.get(year, [])
            if _entry_matches(entry, finding)
        ]
        proposal = default_proposal(finding, decision)

        if permitted is not None:
            allowed_here = list(permitted.get(key, []))
            if "STOP" not in allowed_here:
                allowed_here.append("STOP")
        else:
            allowed_here = available_actions(finding, decision)

        if proposal["action"] not in allowed_here:
            proposal = {
                **proposal,
                "accepted": False,
                "fallback_reason": "ACTION_NOT_AVAILABLE_FOR_THIS_FINDING",
            }

        for entry in candidates:
            action = str(entry.get("action", "")).strip().upper()
            target = entry.get("target")
            reason = str(entry.get("reason", "") or "").strip()[:MAX_REASON_CHARS]

            if action not in ALLOWED_ACTIONS:
                proposal = {
                    **proposal,
                    "accepted": False,
                    "rejected_action": action or "UNKNOWN",
                    "source": "model",
                    "fallback_reason": "ACTION_NOT_ALLOWED",
                }
                continue

            if action not in allowed_here:
                proposal = {
                    **proposal,
                    "accepted": False,
                    "rejected_action": action,
                    "source": "model",
                    "fallback_reason": "ACTION_NOT_AVAILABLE_FOR_THIS_FINDING",
                }
                continue

            resolved_target = None
            if action == "FETCH_SOURCE_DOCUMENT":
                source = _match_source(finding, target)
                if source is None:
                    proposal = {
                        **proposal,
                        "accepted": False,
                        "rejected_action": action,
                        "source": "model",
                        "fallback_reason": "TARGET_NOT_A_KNOWN_SOURCE",
                    }
                    continue
                resolved_target = source.get("url")

            proposal = {
                "country": finding.get("country"),
                "antigen": finding.get("antigen"),
                "year": year,
                "action": action,
                "target": resolved_target,
                "reason": reason or "No reason supplied by the model.",
                "source": "model",
                "accepted": True,
                "rejected_action": None,
                "fallback_reason": None,
            }
            break

        result["proposals"].append(proposal)

    return result


def _challenge_prompt(finding, decision, memory_context):
    critic = decision.get("critic") or {}
    issues = "; ".join(
        f"{issue.get('code')}: {issue.get('details')}"
        for issue in (critic.get("issues") or [])
    ) or "none"

    memory_lines = []
    for memory in (memory_context or {}).get("memories", []) or []:
        memory_lines.append(
            f"- {memory.get('id')}: {memory.get('content')} "
            "(context only, not independent verification)"
        )
    memory_block = "\n".join(memory_lines) or "none retrieved"

    return "\n".join([
        "You are a skeptical reviewer checking one claim from an evidence "
        "investigation. Point out weak or missing support and state what "
        "would change your view. Never state which figure is correct.",
        "",
        f"Claim: {finding.get('country')} {finding.get('antigen')} "
        f"({finding.get('year')}): {finding.get('measure_a')} "
        f"{finding.get('value_a')}% vs {finding.get('measure_b')} "
        f"{finding.get('value_b')}% "
        f"(gap {finding.get('gap_percentage_points')} percentage points)",
        f"Deterministic decision: {decision.get('decision')} - "
        f"{decision.get('reason')}",
        f"Data-quality issues found by the deterministic critic: {issues}",
        f"Source checks: "
        f"{'; '.join(str(check.get('status')) for check in (critic.get('source_checks') or []))}",
        "",
        "Retrieved memories (context only):",
        memory_block,
        "",
        "Respond with JSON only, in this shape:",
        '{"challenges": ["..."], "missing_support": ["..."],',
        ' "would_change_verdict": false, "summary": "one sentence"}',
    ])


def challenge_claim(client, finding, decision, memory_context=None, budget=None):
    """Ask the model to challenge one finding. Advisory only.

    The returned dict never influences the arbiter; the reporter shows it so
    a reader can see the challenge that was made.
    """
    fallback = default_challenge(finding, decision)

    if client is None:
        fallback["fallback_reason"] = "MODEL_NOT_REQUESTED"
        return fallback

    if budget is not None and not budget.spend():
        fallback["fallback_reason"] = "CALL_BUDGET_EXHAUSTED"
        return fallback

    try:
        payload = client.chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a skeptical reviewer. Reply with JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": _challenge_prompt(finding, decision, memory_context),
                },
            ],
            max_tokens=700,
            temperature=0.1,
        )
    except (ModelUnavailable, ModelInvalidResponse) as exc:
        fallback["fallback_reason"] = str(exc)[:MAX_REASON_CHARS]
        return fallback

    challenges = payload.get("challenges")
    missing = payload.get("missing_support")
    summary = payload.get("summary")
    would_change = payload.get("would_change_verdict")

    if not isinstance(challenges, list) or not all(
        isinstance(item, str) for item in challenges
    ):
        fallback["fallback_reason"] = "MODEL_RETURNED_INVALID_CHALLENGES"
        return fallback
    if not isinstance(missing, list) or not all(
        isinstance(item, str) for item in missing
    ):
        missing = []
    if not isinstance(summary, str):
        summary = ""
    if not isinstance(would_change, bool):
        would_change = False

    return {
        "challenges": [item.strip()[:MAX_ITEM_CHARS] for item in challenges[:MAX_LIST_ITEMS]],
        "missing_support": [item.strip()[:MAX_ITEM_CHARS] for item in missing[:MAX_LIST_ITEMS]],
        "would_change_verdict": would_change,
        "summary": summary.strip()[:MAX_REASON_CHARS],
        "source": "model",
        "status": "used",
        "fallback_reason": None,
    }
