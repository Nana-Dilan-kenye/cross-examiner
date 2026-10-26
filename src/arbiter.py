"""Conservative decision policy for Cross-Examiner findings."""
from src.critic import critique


def arbitrate(finding, threshold=5):
    review = critique(finding)
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

    return {
        "decision": decision,
        "reason": reason,
        "critic": review,
    }
