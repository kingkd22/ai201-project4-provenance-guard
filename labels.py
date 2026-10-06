"""Transparency label generator. Label text: planning.md Section 4 (text) and S2 (image)."""

from detection.scoring import attribution_for

AI_LABEL = (
    "Likely AI-generated. Our analysis found strong signs that this text was written by an AI tool "
    "(estimated {pct}% likelihood). This is an automated estimate, not a final judgment. "
    "The creator can appeal this result."
)
HUMAN_LABEL = (
    "Likely human-written. Our analysis found strong signs that this text was written by a person "
    "(estimated {pct}% likelihood). This is an automated estimate, not a guarantee."
)
UNCERTAIN_LABEL = (
    "Origin unclear. Our analysis could not confidently tell whether this text was written by a person "
    "or an AI tool. Treat this result as inconclusive. The creator can appeal this result."
)

IMAGE_AI_LABEL = (
    "Likely AI-generated. Our analysis found strong signs that this image was created with an AI tool "
    "(estimated {pct}% likelihood). This is an automated estimate, not a final judgment. "
    "The creator can appeal this result."
)
IMAGE_HUMAN_LABEL = (
    "Likely human-made. Our analysis found strong signs that this image was captured or created by a person "
    "(estimated {pct}% likelihood). This is an automated estimate, not a guarantee."
)
IMAGE_UNCERTAIN_LABEL = (
    "Origin unclear. Our analysis could not confidently tell whether this image was made by a person "
    "or an AI tool. Treat this result as inconclusive. The creator can appeal this result."
)

LABELS = {
    "text": {"likely_ai": AI_LABEL, "likely_human": HUMAN_LABEL, "uncertain": UNCERTAIN_LABEL},
    "image": {"likely_ai": IMAGE_AI_LABEL, "likely_human": IMAGE_HUMAN_LABEL, "uncertain": IMAGE_UNCERTAIN_LABEL},
}

REVIEW_NOTICE = "The creator has appealed this result. It is under human review."


def make_label(ai_score, content_type="text"):
    """Return the reader-facing label for an ai_score, using the scoring thresholds."""
    attribution = attribution_for(ai_score)
    template = LABELS[content_type][attribution]
    if attribution == "likely_ai":
        return template.format(pct=round(ai_score * 100))
    if attribution == "likely_human":
        return template.format(pct=round((1 - ai_score) * 100))
    return template
