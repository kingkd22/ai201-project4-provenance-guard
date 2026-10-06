"""Provenance certificate ("Verified Human Creator"). Spec: planning.md S3."""

import hashlib
import hmac
import os
import random
import secrets
from datetime import timedelta

import storage

CHALLENGE_TTL = timedelta(minutes=10)
CERTIFICATE_TTL = timedelta(days=180)
MIN_RESPONSE_WORDS = 60
PASS_MAX_SCORE = 0.40
SECRET_FILE = ".cert_secret"

CHALLENGE_PROMPTS = (
    "Describe the last piece you wrote: where you were, what was hard about it, and what you changed.",
    "Tell the story of how one of your pieces started. What gave you the idea, and what did the first draft look like?",
    "Describe a piece of your writing you are not happy with and explain what you would do differently now.",
    "Walk through your usual writing routine on a real day: time, place, tools, and what usually interrupts you.",
    "Pick a recent piece and explain one specific choice you made in it, like a word, a line break, or a cut.",
)

BADGE_TITLE = "Verified Human Creator"
BADGE_TEXT = (
    "Verified Human Creator. This creator passed a live writing check on {date}. "
    "This confirms they write in their own voice; it does not certify that this specific piece "
    "was written without AI."
)


def _secret():
    """CERT_SECRET from the environment, else a secret generated once and kept in .cert_secret."""
    env = os.environ.get("CERT_SECRET")
    if env:
        return env.encode()
    if not os.path.exists(SECRET_FILE):
        with open(SECRET_FILE, "w") as f:
            f.write(secrets.token_hex(32))
    with open(SECRET_FILE) as f:
        return f.read().strip().encode()


def sign(certificate_id, creator_id, issued_at, expires_at):
    message = f"{certificate_id}|{creator_id}|{issued_at}|{expires_at}".encode()
    return hmac.new(_secret(), message, hashlib.sha256).hexdigest()


def new_challenge(challenge_id, creator_id):
    now = storage.from_iso(storage.utc_now())
    return {
        "challenge_id": challenge_id,
        "creator_id": creator_id,
        "prompt": random.choice(CHALLENGE_PROMPTS),
        "created_at": storage.to_iso(now),
        "expires_at": storage.to_iso(now + CHALLENGE_TTL),
    }


def passes(result):
    """Pass if the response scores clearly human and no signal votes AI."""
    return result["ai_score"] < PASS_MAX_SCORE and "ai" not in result["votes"].values()


def issue(certificate_id, creator_id, verification_score):
    issued = storage.from_iso(storage.utc_now())
    issued_at = storage.to_iso(issued)
    expires_at = storage.to_iso(issued + CERTIFICATE_TTL)
    return {
        "certificate_id": certificate_id,
        "creator_id": creator_id,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "verification_score": verification_score,
        "signature": sign(certificate_id, creator_id, issued_at, expires_at),
    }


def is_valid(cert):
    """Signature matches and the certificate has not expired."""
    expected = sign(cert["certificate_id"], cert["creator_id"], cert["issued_at"], cert["expires_at"])
    if not hmac.compare_digest(expected, cert["signature"]):
        return False
    return storage.from_iso(cert["expires_at"]) > storage.from_iso(storage.utc_now())


def creator_verification(creator_id):
    """What is displayed next to a creator's content."""
    cert = storage.latest_certificate_for(creator_id)
    if cert is None or not is_valid(cert):
        return {"verified": False}
    return {
        "verified": True,
        "certificate_id": cert["certificate_id"],
        "badge": BADGE_TITLE,
        "badge_text": BADGE_TEXT.format(date=cert["issued_at"][:10]),
        "expires_at": cert["expires_at"],
    }
