"""Print per-signal and combined scores for every labeled sample.

Usage: python -m tests.run_calibration
"""

from dotenv import load_dotenv

load_dotenv()

from detection.image_metadata import has_recognized_fields, metadata_signal  # noqa: E402
from detection.llm_signal import llm_image_signal, llm_signal  # noqa: E402
from detection.scoring import combine  # noqa: E402
from detection.stylometry import stylometry_signal  # noqa: E402
from detection.voice import voice_signal  # noqa: E402
from tests.samples import IMAGE_SAMPLES, SAMPLES  # noqa: E402


def fmt(signal):
    p = signal.get("ai_probability")
    return f"{p:>5.2f}" if p is not None else "  n/a"


def run_text():
    header = f"{'sample':26} {'truth':6} {'words':>5} {'llm':>5} {'stylo':>5} {'voice':>5} {'score':>5}  attribution / votes / adjustments"
    print(header)
    print("-" * len(header))
    for name, truth, text in SAMPLES:
        signals = {"llm": llm_signal(text), "stylometry": stylometry_signal(text), "voice": voice_signal(text)}
        result = combine(signals, "text", len(text.split()))
        print(
            f"{name:26} {truth:6} {len(text.split()):>5} {fmt(signals['llm'])} {fmt(signals['stylometry'])} "
            f"{fmt(signals['voice'])} {result['ai_score']:>5.2f}  {result['attribution']} "
            f"{'/'.join(result['votes'].values())} {result['adjustments']}"
        )


def run_images():
    header = f"{'sample':26} {'truth':6} {'meta':>5} {'llm':>5} {'score':>5}  attribution / votes / adjustments"
    print(header)
    print("-" * len(header))
    for name, truth, description, metadata in IMAGE_SAMPLES:
        signals = {"metadata": metadata_signal(metadata), "llm": llm_image_signal(description, metadata)}
        insufficient = not has_recognized_fields(metadata) and not description
        result = combine(signals, "image", insufficient_evidence=insufficient)
        print(
            f"{name:26} {truth:6} {fmt(signals['metadata'])} {fmt(signals['llm'])} {result['ai_score']:>5.2f}  "
            f"{result['attribution']} {'/'.join(result['votes'].values())} {result['adjustments']}"
        )


if __name__ == "__main__":
    run_text()
    print()
    run_images()
