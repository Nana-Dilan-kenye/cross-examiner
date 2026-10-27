"""Conservative decision policy for Cross-Examiner findings."""
from src.adjudicator import build_recommendation
from src.critic import critique
from src.memory_policy import recall as recall_memories


def compare_with_memory(finding, memory_context=None):
    """Compare a finding with retrieved memories without treating them as proof."""
    memories = (memory_context or {}).get("memories", [])
    matching = []

    country = str(finding.get("country", "")).casefold()
    antigen = str(finding.get("antigen", "")).casefold()
    year = str(finding.get("year", ""))
    gap = float(finding.get("gap_percentage_points", 0))

    for memory in memories:
        content = str(memory.get("content", ""))
        source = str(memory.get("source", ""))

        # Match the investigation topic and year using both stored text
        # and the structured memory source identifier.
        same_topic = (
            country in content.casefold()
            and antigen in content.casefold()
        )
        same_year = (
            year in content
            or source.endswith(f":{year}")
        )

        if not same_topic or not same_year:
            continue

        matching_gap = f"{gap:.1f}" in content

        matching.append({
            "memory_id": memory.get("id", "unknown"),
            "memory_source": source,
            "relation": (
                "NUMERICALLY_CONSISTENT_MEMORY"
                if matching_gap
                else "SAME_TOPIC_SAME_YEAR_DIFFERENT_VALUE"
            ),
            "content": content,
            "warning": (
                "Retrieved memory is contextual information, "
                "not independent verification."
            ),
        })

    return {
        "matching_memories": matching,
        "memory_comparison": (
            "MATCHES_RETRIEVED_MEMORY"
            if matching
            else "NO_MATCHING_MEMORY_FOUND"
        ),
    }

def arbitrate(finding, threshold=5, memory_context=None):
    review = critique(finding)
    memory_comparison = compare_with_memory(finding, memory_context)

    if not review["passed"]:
        decision = "ABSTAIN"
        reason = "Evidence or data-quality checks failed."
    elif float(finding["gap_percentage_points"]) >= threshold:
        decision = "REVIEW"
        reason = (
            "The observed gap meets the review threshold; investigate definitions, "
            "denominators, reporting quality, and estimation methods."
        )
    else:
        decision = "REPORT_OBSERVATION"
        reason = (
            "The observation is below the review threshold; this does not certify "
            "either value as correct."
        )

    result = {
        "decision": decision,
        "reason": reason,
        "critic": review,
        "memory_comparison": memory_comparison,
    }

    # What earlier investigations of this country, antigen and year left
    # behind. It changes what this run does next, and it is on the record
    # so a reader can see the difference between a cold and a warm start.
    recalled = recall_memories(
        (memory_context or {}).get("memories"), finding
    )
    if recalled.get("memory_ids"):
        result["memory_recall"] = recalled
        if recalled.get("effect"):
            result["reason"] = f"{reason} {recalled['effect']}"

    # An independent measurement may say which number to act on even when
    # the discrepancy itself is not settled.
    recommendation = build_recommendation(finding, result)
    if recommendation:
        result["recommendation"] = recommendation

    return result