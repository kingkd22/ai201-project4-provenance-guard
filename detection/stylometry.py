"""Signal 2: stylometric analyzer (local, pure Python).

Three sub-metrics, each mapped to [0, 1] where higher means more AI-like,
averaged equally into one ai_probability. Mappings are from planning.md Section 2.
"""

import re
import statistics

# Burstiness: coefficient of variation of sentence lengths.
CV_AI = 0.25     # at or below -> 1.0
CV_HUMAN = 0.75  # at or above -> 0.0

# Word length: mean letters per word.
WORD_LEN_HUMAN = 4.2  # at or below -> 0.0
WORD_LEN_AI = 5.8     # at or above -> 1.0

# AI marker vocabulary: fraction of words from the list below.
MARKER_SATURATION = 0.05  # at or above -> 1.0

AI_MARKERS = frozenset({
    "additionally", "comprehensive", "consequently", "crucial", "delve", "ensure",
    "essential", "fostering", "furthermore", "holistic", "landscape", "leverage",
    "moreover", "navigate", "notably", "numerous", "paradigm", "pivotal", "realm",
    "robust", "seamless", "stakeholders", "tapestry", "transformative", "ultimately",
    "underscores", "various",
})

_SENTENCE_SPLIT = re.compile(r"[.!?]+|\n+")
_WORD = re.compile(r"[a-z]+(?:'[a-z]+)?")


def _clamp(value):
    return max(0.0, min(1.0, value))


def split_sentences(text):
    """Split on terminal punctuation and line breaks; poetry lines count as sentences."""
    sentences = []
    for chunk in _SENTENCE_SPLIT.split(text):
        words = _WORD.findall(chunk.lower())
        if words:
            sentences.append(words)
    return sentences


def burstiness_score(sentences):
    lengths = [len(s) for s in sentences]
    if len(lengths) < 2:
        return 0.5, None  # Not enough sentences to measure variation; neutral.
    cv = statistics.pstdev(lengths) / statistics.mean(lengths)
    return _clamp((CV_HUMAN - cv) / (CV_HUMAN - CV_AI)), cv


def word_length_score(words):
    mean_len = sum(len(w) for w in words) / len(words)
    return _clamp((mean_len - WORD_LEN_HUMAN) / (WORD_LEN_AI - WORD_LEN_HUMAN)), mean_len


def marker_score(words):
    rate = sum(1 for w in words if w in AI_MARKERS) / len(words)
    return _clamp(rate / MARKER_SATURATION), rate


def stylometry_signal(text):
    """Score text on burstiness, word length, and AI marker vocabulary. Returns a dict matching planning.md Section 2."""
    sentences = split_sentences(text)
    words = [w for s in sentences for w in s]
    if not words:
        return {"ai_probability": 0.5, "status": "no_words", "sentence_count": 0, "word_count": 0}

    burst, cv = burstiness_score(sentences)
    length, mean_len = word_length_score(words)
    markers, marker_rate = marker_score(words)

    return {
        "ai_probability": round((burst + length + markers) / 3, 2),
        "burstiness": round(burst, 2),
        "word_length": round(length, 2),
        "ai_markers": round(markers, 2),
        "raw": {
            "sentence_length_cv": round(cv, 3) if cv is not None else None,
            "mean_word_length": round(mean_len, 2),
            "marker_rate": round(marker_rate, 3),
        },
        "sentence_count": len(sentences),
        "word_count": len(words),
        "status": "ok",
    }
