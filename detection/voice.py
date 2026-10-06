"""Signal 3: personal voice analyzer (local, pure Python).

Measures evidence that a specific person is talking. One-sided by design:
present personal voice is strong human evidence, absent voice is only weak AI
evidence, so ai_probability tops out at VOICE_CEILING. Spec: planning.md S1.
"""

import re

FIRST_PERSON = frozenset({"i", "me", "my", "mine", "myself", "i'm", "i've", "i'd", "i'll"})
FIRST_PERSON_SATURATION = 0.06
INFORMAL_SATURATION = 0.04
VOICE_CEILING = 0.75

_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
_CASUAL_PUNCT = re.compile(r"[?!]|\.\.\.|\s-\s|—|\(")
_DIGITS = re.compile(r"\d+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_IGNORED_CAPS = frozenset({"AI", "US", "UK", "TV", "OK"})


def voice_signal(text):
    """Score text on first-person use, informal markers, and lowercase sentence starts."""
    text = text.replace("’", "'")
    words = _WORD.findall(text)
    if not words:
        return {"ai_probability": 0.5, "status": "no_words"}
    n = len(words)
    lower = [w.lower() for w in words]

    first_person_rate = sum(1 for w in lower if w in FIRST_PERSON) / n
    informal_count = (
        sum(1 for w in lower if "'" in w)
        + len(_CASUAL_PUNCT.findall(text))
        + sum(1 for w in words if len(w) > 1 and w.isupper() and w not in _IGNORED_CAPS)
        + len(_DIGITS.findall(text))
    )
    informal_rate = informal_count / n
    sentences = [s.strip() for s in _SENTENCE.split(text) if s.strip()]
    lowercase_starts = sum(1 for s in sentences if s[0].islower()) / len(sentences)

    first_person = min(1.0, first_person_rate / FIRST_PERSON_SATURATION)
    informal = min(1.0, informal_rate / INFORMAL_SATURATION)
    human_evidence = (first_person + informal + lowercase_starts) / 3

    return {
        "ai_probability": round(VOICE_CEILING * (1 - human_evidence), 2),
        "first_person": round(first_person, 2),
        "informal_markers": round(informal, 2),
        "lowercase_starts": round(lowercase_starts, 2),
        "raw": {
            "first_person_rate": round(first_person_rate, 3),
            "informal_rate": round(informal_rate, 3),
        },
        "status": "ok",
    }
