"""Image signal 1: metadata forensics (rule-based). Spec: planning.md S2."""

import re

GENERATOR_NAMES = (
    "midjourney", "dall-e", "dalle", "stable diffusion", "stablediffusion", "sdxl", "comfyui",
    "automatic1111", "firefly", "imagen", "leonardo", "ideogram", "flux", "novelai",
)
_GENERATOR_PATTERN = re.compile(r"\b(" + "|".join(re.escape(n) for n in GENERATOR_NAMES) + r")\b")
AI_SOURCE_TYPES = ("trainedalgorithmicmedia", "compositewithtrainedalgorithmicmedia")
CAMERA_FIELDS = ("make", "model", "exposure_time", "f_number", "iso", "focal_length", "gps")
GENERATOR_SIZES = frozenset({512, 640, 768, 832, 896, 1024, 1152, 1216, 1344, 1536, 1792, 2048})

GENERATOR_SCORE = 0.95
BASE_SCORE = 0.50
PER_CAMERA_FIELD = 0.08
GENERATOR_SIZE_BONUS = 0.15
NO_CAMERA_BONUS = 0.10
MIN_SCORE = 0.05
MAX_SCORE = 0.95
RECOGNIZED_FIELDS = frozenset(CAMERA_FIELDS) | {"width", "height", "software", "digital_source_type"}


def _present(value):
    return value not in (None, "", False)


def _string_values(metadata):
    return [str(v).lower() for v in metadata.values() if isinstance(v, (str, int, float))]


def has_recognized_fields(metadata):
    return any(k in RECOGNIZED_FIELDS and _present(v) for k, v in (metadata or {}).items())


def metadata_signal(metadata):
    """Score image metadata. Returns a dict with ai_probability and the evidence found."""
    metadata = metadata or {}
    values = _string_values(metadata)

    generator = next((m.group(1) for v in values if (m := _GENERATOR_PATTERN.search(v))), None)
    source_type = str(metadata.get("digital_source_type", "")).lower()
    ai_source = source_type in AI_SOURCE_TYPES

    camera_fields = [f for f in CAMERA_FIELDS if _present(metadata.get(f))]
    width, height = metadata.get("width"), metadata.get("height")
    generator_size = width in GENERATOR_SIZES and height in GENERATOR_SIZES

    if generator or ai_source:
        score = GENERATOR_SCORE
    else:
        score = BASE_SCORE - PER_CAMERA_FIELD * len(camera_fields)
        if generator_size:
            score += GENERATOR_SIZE_BONUS
        if not camera_fields:
            score += NO_CAMERA_BONUS
        score = max(MIN_SCORE, min(MAX_SCORE, score))

    return {
        "ai_probability": round(score, 2),
        "generator_match": generator,
        "ai_source_type": ai_source,
        "camera_fields": camera_fields,
        "generator_size": generator_size,
        "status": "ok",
    }
