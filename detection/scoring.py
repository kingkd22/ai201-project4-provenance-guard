"""Confidence scorer: weighted ensemble with a vote-conflict check.

Spec: planning.md Section 3 and Stretch S1/S2.
"""

WEIGHTS = {
    "text": {"llm": 0.45, "stylometry": 0.35, "voice": 0.20},
    "image": {"metadata": 0.60, "llm": 0.40},
}

AI_VOTE = 0.60
HUMAN_VOTE = 0.40
CONFLICT_SHRINK = 0.5

SHORT_TEXT_WORDS = 40
UNCERTAIN_FLOOR = 0.30
UNCERTAIN_CEILING = 0.70

AI_THRESHOLD = 0.80
HUMAN_THRESHOLD = 0.30


def attribution_for(ai_score):
    if ai_score >= AI_THRESHOLD:
        return "likely_ai"
    if ai_score < HUMAN_THRESHOLD:
        return "likely_human"
    return "uncertain"


def vote_for(probability):
    if probability >= AI_VOTE:
        return "ai"
    if probability <= HUMAN_VOTE:
        return "human"
    return "abstain"


def _clamp_uncertain(score):
    return max(UNCERTAIN_FLOOR, min(UNCERTAIN_CEILING, score))


def combine(signals, content_type="text", word_count=None, insufficient_evidence=False):
    """Combine signal outputs into ai_score, confidence, attribution, votes, and adjustments.

    `signals` maps signal name to its output dict. A signal counts only if its
    status is "ok".
    """
    weights = WEIGHTS[content_type]
    usable = {name: signals[name]["ai_probability"] for name in weights if signals.get(name, {}).get("status") == "ok"}
    adjustments = [f"{name}_unavailable" for name in weights if name not in usable]

    if not usable:
        score = 0.5
    else:
        total_weight = sum(weights[name] for name in usable)
        score = sum(weights[name] * p for name, p in usable.items()) / total_weight

    votes = {name: vote_for(p) for name, p in usable.items()}
    if "ai" in votes.values() and "human" in votes.values():
        score = 0.5 + (score - 0.5) * CONFLICT_SHRINK
        adjustments.append("signal_conflict")

    clamp = len(usable) < len(weights)
    if content_type == "text" and word_count is not None and word_count < SHORT_TEXT_WORDS:
        adjustments.append("short_text_cap")
        clamp = True
    if insufficient_evidence:
        adjustments.append("insufficient_evidence")
        clamp = True
    if clamp:
        score = _clamp_uncertain(score)

    score = round(score, 2)
    return {
        "ai_score": score,
        "confidence": round(max(score, 1 - score), 2),
        "attribution": attribution_for(score),
        "votes": votes,
        "adjustments": adjustments,
    }
