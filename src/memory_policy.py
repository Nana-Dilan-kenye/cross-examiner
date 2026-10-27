"""What a remembered investigation changes about the next one.

The memory store is not a log. A memory of the form
``cross-examiner:conflict:<country>:<antigen>:<year>`` says that an
earlier investigation of that country, antigen and year already found
the administrative figure to be far above an independent household
measurement. The next investigation of the same country and year must
act on that: it has to go and get the survey evidence first, and it has
to say that the question it is answering now is a different one from the
one the first run answered.

This module turns a list of memories into that decision. It is
deterministic, and it is the part of the memory feature that can be
tested without a memory server.
"""

# The memory source prefixes the project writes.
CONFLICT_PREFIX = "cross-examiner:conflict:"
DISPOSITION_PREFIX = "cross-examiner:disposition:"
FINDING_PREFIX = "cross-examiner:finding:"
REVISION_PREFIX = "cross-examiner:revision:"
QUESTION_PREFIX = "cross-examiner:question:"


def _topic(source):
    """The country, antigen and year a memory is about."""
    parts = str(source or "").split(":")
    if len(parts) < 5:
        return None
    return {
        "country": parts[2],
        "antigen": parts[3],
        "year": parts[4],
    }


def _kind(source):
    """The kind of fact a memory holds."""
    source = str(source or "")
    for prefix, kind in (
        (CONFLICT_PREFIX, "conflict"),
        (DISPOSITION_PREFIX, "disposition"),
        (FINDING_PREFIX, "finding"),
        (REVISION_PREFIX, "revision"),
        (QUESTION_PREFIX, "question"),
    ):
        if source.startswith(prefix):
            return kind
    return "observation"


def recall(memories, finding):
    """What the store already knows about this finding.

    Returns a dict with the facts that were remembered for the same
    country, antigen and year, and what they imply for this run.
    """
    country = str(finding.get("country", "")).casefold()
    antigen = str(finding.get("antigen", "")).casefold()
    year = str(finding.get("year", ""))

    known = {
        "conflict": [],
        "disposition": [],
        "finding": [],
        "revision": [],
        "question": [],
    }
    memory_ids = []

    for memory in memories or []:
        topic = _topic(memory.get("source", ""))
        if not topic:
            continue
        if (
            topic["country"].casefold() != country
            or topic["antigen"].casefold() != antigen
            or topic["year"] != year
        ):
            continue
        kind = _kind(memory.get("source", ""))
        known.setdefault(kind, []).append({
            "id": memory.get("id"),
            "content": memory.get("content", ""),
            "confidence": memory.get("confidence"),
            "refs": memory.get("refs") or [],
        })
        memory_ids.append(memory.get("id"))

    conflicts = known.get("conflict") or []
    dispositions = known.get("disposition") or []
    questions = known.get("question") or []

    effect = ""
    preferred_action = None
    preferred_target = None

    if conflicts:
        effect = (
            "An earlier investigation of this country, antigen and year "
            "already found that the administrative figure sits far above an "
            "independent household measurement. This run therefore goes for "
            "the survey evidence first, and the question it is answering is "
            "whether that conflict still holds, not which figure is right."
        )
        preferred_action = "FETCH_SOURCE_DOCUMENT"
        preferred_target = _survey_target(finding, conflicts)
    elif dispositions:
        effect = (
            "An earlier investigation of this country, antigen and year "
            "reached a disposition. This run checks it against the evidence "
            "rather than starting from scratch."
        )

    return {
        "known": known,
        "memory_ids": memory_ids,
        "has_prior_conflict": bool(conflicts),
        "prior_conflict": conflicts[0] if conflicts else None,
        "prior_disposition": dispositions[0] if dispositions else None,
        "open_questions": questions,
        "effect": effect,
        "preferred_action": preferred_action,
        "preferred_target": preferred_target,
    }


def _survey_target(finding, conflicts):
    """The source the recall points at: the survey line of this finding."""
    for observation in finding.get("observations") or []:
        if observation.get("measurement_kind") == "household_survey":
            return observation.get("source", {}).get("url", "")
    for conflict in conflicts:
        for ref in conflict.get("refs") or []:
            if "country-profiles" in str(ref) or "dhsprogram" in str(ref):
                return ref
    return ""


def conflict_memory(finding, conflict):
    """The memory text for a conflict that was found."""
    return (
        f"For {finding.get('country')} {finding.get('antigen')} in "
        f"{finding.get('year')}, the administrative figure "
        f"({conflict.get('value_a')}%) sits "
        f"{float(conflict.get('gap_percentage_points', 0)):.1f} percentage points "
        f"above an "
        f"independent household-survey measurement "
        f"({conflict.get('value_b')}%). The administrative number is not "
        f"usable as the coverage level; the survey line is the better "
        f"estimate of the level, with the usual caveats about survey design."
    )


def question_memory(finding, uncertainties):
    """The memory text for what a run could not settle."""
    items = []
    for item in uncertainties or []:
        items.append(str(item))
    body = " ".join(items)[:600]
    return (
        f"Still open for {finding.get('country')} "
        f"{finding.get('antigen')} {finding.get('year')}: {body}"
    )
