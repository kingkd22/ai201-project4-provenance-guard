"""Provenance Guard API."""

import os
import uuid

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

load_dotenv()

import analytics  # noqa: E402
import certificates  # noqa: E402
import storage  # noqa: E402
from detection.image_metadata import has_recognized_fields, metadata_signal  # noqa: E402
from detection.llm_signal import llm_image_signal, llm_signal  # noqa: E402
from detection.scoring import combine  # noqa: E402
from detection.stylometry import stylometry_signal  # noqa: E402
from detection.voice import voice_signal  # noqa: E402
from labels import REVIEW_NOTICE, make_label  # noqa: E402

MIN_WORDS = 10
MAX_WORDS = 5000
MAX_DESCRIPTION_CHARS = 2000
MAX_CREATOR_ID_LEN = 64
MIN_REASONING_CHARS = 20
MAX_REASONING_CHARS = 2000
EXCERPT_CHARS = 300
LOG_DEFAULT_LIMIT = 50
LOG_MAX_LIMIT = 500
LOG_EVENTS = {"classification", "appeal", "certificate_issued", "certificate_failed"}
APPEAL_STATUSES = {"pending"}
CONTENT_TYPES = {"text", "image"}

# Rate limits per client IP (reasoning in planning.md Section 8 and README).
SUBMIT_LIMIT = "10 per minute;100 per day"
APPEAL_LIMIT = "5 per hour"
CHALLENGE_LIMIT = "3 per hour"
VERIFY_LIMIT = "10 per hour"
READ_LIMIT = "60 per minute"

app = Flask(__name__)
app.json.sort_keys = False
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)
storage.init_db()


def error(code, message, status, **extra):
    return jsonify({"error": code, "message": message, **extra}), status


def validate_creator_id(creator_id):
    """Return (clean_creator_id, None) or (None, error_response)."""
    if not isinstance(creator_id, str) or not creator_id.strip():
        return None, error("invalid_creator_id", "'creator_id' is required and must be a non-empty string.", 400)
    creator_id = creator_id.strip()
    if len(creator_id) > MAX_CREATOR_ID_LEN:
        return None, error("invalid_creator_id", f"'creator_id' must be at most {MAX_CREATOR_ID_LEN} characters.", 400)
    return creator_id, None


def analyze_text(text, word_count):
    """Run the three text signals and the ensemble scorer."""
    signals = {"llm": llm_signal(text), "stylometry": stylometry_signal(text), "voice": voice_signal(text)}
    return signals, combine(signals, "text", word_count)


def analyze_image(description, metadata):
    """Run the two image signals and the ensemble scorer."""
    signals = {"metadata": metadata_signal(metadata), "llm": llm_image_signal(description, metadata)}
    insufficient = not has_recognized_fields(metadata) and not description
    return signals, combine(signals, "image", insufficient_evidence=insufficient)


def signal_scores(signals):
    """Compact per-signal scores for the audit log and reviewer views."""
    scores = {name: s.get("ai_probability") for name, s in signals.items()}
    scores["llm_status"] = signals["llm"]["status"]
    return scores


def original_decision(content):
    return {
        "content_type": content["content_type"],
        "attribution": content["attribution"],
        "ai_score": content["ai_score"],
        "confidence": content["confidence"],
        "signals": signal_scores(content["signals"]),
        "votes": content["votes"],
        "llm_reasoning": content["signals"]["llm"].get("reasoning"),
        "adjustments": content["adjustments"],
        "label": content["label"],
    }


def parse_submission(body):
    """Validate a /submit body. Returns (fields, None) or (None, error_response)."""
    content_type = body.get("content_type", "text")
    if content_type not in CONTENT_TYPES:
        return None, error("invalid_content_type", f"'content_type' must be one of {sorted(CONTENT_TYPES)}.", 400)

    if content_type == "text":
        text = body.get("text")
        if not isinstance(text, str) or not text.strip():
            return None, error("invalid_text", "'text' is required and must be a non-empty string.", 400)
        word_count = len(text.split())
        if word_count < MIN_WORDS or word_count > MAX_WORDS:
            return None, error(
                "invalid_length",
                f"'text' must be between {MIN_WORDS} and {MAX_WORDS} words (got {word_count}).",
                400,
            )
        return {"content_type": "text", "text": text, "metadata": None, "word_count": word_count}, None

    description = body.get("description", "")
    metadata = body.get("metadata")
    if not isinstance(description, str) or len(description) > MAX_DESCRIPTION_CHARS:
        return None, error("invalid_description", f"'description' must be a string of at most {MAX_DESCRIPTION_CHARS} characters.", 400)
    if metadata is not None and not isinstance(metadata, dict):
        return None, error("invalid_metadata", "'metadata' must be a JSON object.", 400)
    if not metadata and not description.strip():
        return None, error("missing_image_data", "Image submissions need 'metadata', 'description', or both.", 400)
    description = description.strip()
    return {
        "content_type": "image",
        "text": description,
        "metadata": metadata or {},
        "word_count": len(description.split()),
    }, None


@app.post("/submit")
@limiter.limit(SUBMIT_LIMIT)
def submit():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error("invalid_json", "Request body must be a JSON object.", 400)

    creator_id, err = validate_creator_id(body.get("creator_id"))
    if err:
        return err
    fields, err = parse_submission(body)
    if err:
        return err

    if fields["content_type"] == "text":
        signals, score = analyze_text(fields["text"], fields["word_count"])
    else:
        signals, score = analyze_image(fields["text"], fields["metadata"])

    record = {
        "content_id": str(uuid.uuid4()),
        "creator_id": creator_id,
        "content_type": fields["content_type"],
        "text": fields["text"],
        "metadata": fields["metadata"],
        "word_count": fields["word_count"],
        "attribution": score["attribution"],
        "ai_score": score["ai_score"],
        "confidence": score["confidence"],
        "signals": signals,
        "votes": score["votes"],
        "adjustments": score["adjustments"],
        "label": make_label(score["ai_score"], fields["content_type"]),
        "status": "classified",
        "created_at": storage.utc_now(),
    }
    storage.save_content(record)
    storage.append_audit(
        "classification",
        record["content_id"],
        creator_id,
        {
            "content_type": record["content_type"],
            "status": record["status"],
            "attribution": record["attribution"],
            "ai_score": record["ai_score"],
            "confidence": record["confidence"],
            "signals": signal_scores(signals),
            "votes": record["votes"],
            "adjustments": record["adjustments"],
            "label": record["label"],
        },
        timestamp=record["created_at"],
    )

    response = {k: v for k, v in record.items() if k not in ("text", "metadata")}
    response["creator_verification"] = certificates.creator_verification(creator_id)
    return jsonify(response), 200


@app.post("/appeal")
@limiter.limit(APPEAL_LIMIT)
def appeal():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error("invalid_json", "Request body must be a JSON object.", 400)

    content_id = body.get("content_id")
    reasoning = body.get("creator_reasoning")
    creator_id = body.get("creator_id")

    if not isinstance(content_id, str) or not content_id.strip():
        return error("invalid_content_id", "'content_id' is required and must be a string.", 400)
    if not isinstance(reasoning, str) or not (MIN_REASONING_CHARS <= len(reasoning.strip()) <= MAX_REASONING_CHARS):
        return error(
            "invalid_reasoning",
            f"'creator_reasoning' must be a string of {MIN_REASONING_CHARS}-{MAX_REASONING_CHARS} characters "
            "explaining why the result is wrong.",
            400,
        )
    if creator_id is not None and not isinstance(creator_id, str):
        return error("invalid_creator_id", "'creator_id' must be a string if provided.", 400)

    content = storage.get_content(content_id.strip())
    if content is None:
        return error("not_found", "No submission exists with that content_id.", 404)
    if creator_id is not None and creator_id.strip() != content["creator_id"]:
        return error("forbidden", "Only the original creator can appeal this result.", 403)
    if content["status"] == "under_review":
        existing = storage.get_appeal_for_content(content["content_id"])
        return error(
            "already_under_review",
            "This content already has an appeal under review.",
            409,
            appeal_id=existing["appeal_id"] if existing else None,
        )

    decision = original_decision(content)
    appeal_record = {
        "appeal_id": str(uuid.uuid4()),
        "content_id": content["content_id"],
        "creator_id": content["creator_id"],
        "reasoning": reasoning.strip(),
        "status": "pending",
        "created_at": storage.utc_now(),
    }
    audit_details = {
        "status": "under_review",
        "appeal_id": appeal_record["appeal_id"],
        "appeal_reasoning": appeal_record["reasoning"],
        "original_decision": decision,
    }
    if not storage.create_appeal(appeal_record, audit_details):
        return error("already_under_review", "This content already has an appeal under review.", 409)

    return jsonify({
        "message": "Appeal received. The content is now under human review.",
        "appeal_id": appeal_record["appeal_id"],
        "content_id": content["content_id"],
        "status": "under_review",
        "appeal_reasoning": appeal_record["reasoning"],
        "original_decision": decision,
        "created_at": appeal_record["created_at"],
    }), 200


@app.get("/content/<content_id>")
@limiter.limit(READ_LIMIT)
def get_content(content_id):
    content = storage.get_content(content_id)
    if content is None:
        return error("not_found", "No submission exists with that content_id.", 404)
    if content["status"] == "under_review":
        content["review_notice"] = REVIEW_NOTICE
        content["appeal"] = storage.get_appeal_for_content(content_id)
    content["creator_verification"] = certificates.creator_verification(content["creator_id"])
    return jsonify(content)


@app.get("/appeals")
@limiter.limit(READ_LIMIT)
def appeals_queue():
    status = request.args.get("status", "pending")
    if status not in APPEAL_STATUSES:
        return error("invalid_status", f"'status' must be one of {sorted(APPEAL_STATUSES)}.", 400)

    queue = []
    for appeal_row, content in storage.list_appeals(status):
        queue.append({
            "appeal_id": appeal_row["appeal_id"],
            "submitted_at": appeal_row["created_at"],
            "creator_id": appeal_row["creator_id"],
            "reasoning": appeal_row["reasoning"],
            "content": {
                "content_id": content["content_id"],
                "content_type": content["content_type"],
                "text_excerpt": content["text"][:EXCERPT_CHARS],
                "word_count": content["word_count"],
            },
            "original_decision": original_decision(content),
            "creator_verification": certificates.creator_verification(content["creator_id"]),
        })
    return jsonify({"appeals": queue})


@app.post("/certificate/challenge")
@limiter.limit(CHALLENGE_LIMIT)
def certificate_challenge():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error("invalid_json", "Request body must be a JSON object.", 400)
    creator_id, err = validate_creator_id(body.get("creator_id"))
    if err:
        return err

    challenge = certificates.new_challenge(str(uuid.uuid4()), creator_id)
    storage.save_challenge(challenge)
    return jsonify({
        "challenge_id": challenge["challenge_id"],
        "prompt": challenge["prompt"],
        "min_words": certificates.MIN_RESPONSE_WORDS,
        "expires_at": challenge["expires_at"],
        "instructions": "Answer the prompt in your own words, without AI tools, before the challenge expires.",
    }), 200


@app.post("/certificate/verify")
@limiter.limit(VERIFY_LIMIT)
def certificate_verify():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error("invalid_json", "Request body must be a JSON object.", 400)
    creator_id, err = validate_creator_id(body.get("creator_id"))
    if err:
        return err
    challenge_id = body.get("challenge_id")
    response_text = body.get("response")
    if not isinstance(challenge_id, str) or not isinstance(response_text, str):
        return error("invalid_request", "'challenge_id' and 'response' are required strings.", 400)

    challenge = storage.get_challenge(challenge_id)
    if challenge is None:
        return error("not_found", "No challenge exists with that challenge_id.", 404)
    if challenge["creator_id"] != creator_id:
        return error("forbidden", "This challenge was issued to a different creator.", 403)
    if challenge["used"]:
        return error("challenge_used", "This challenge has already been used. Request a new one.", 409)
    if storage.from_iso(challenge["expires_at"]) <= storage.from_iso(storage.utc_now()):
        return error("challenge_expired", "This challenge has expired. Request a new one.", 410)
    word_count = len(response_text.split())
    if word_count < certificates.MIN_RESPONSE_WORDS:
        return error(
            "response_too_short",
            f"The response must be at least {certificates.MIN_RESPONSE_WORDS} words (got {word_count}).",
            400,
        )
    if not storage.consume_challenge(challenge_id):
        return error("challenge_used", "This challenge has already been used. Request a new one.", 409)

    signals, result = analyze_text(response_text, word_count)
    details = {
        "challenge_id": challenge_id,
        "verification_score": result["ai_score"],
        "signals": signal_scores(signals),
        "votes": result["votes"],
        "adjustments": result["adjustments"],
    }

    if not certificates.passes(result):
        storage.append_audit("certificate_failed", None, creator_id, details)
        return jsonify({
            "verified": False,
            "message": "The writing check did not pass. You can request a new challenge and try again.",
            "verification_score": result["ai_score"],
            "votes": result["votes"],
        }), 200

    cert = certificates.issue(str(uuid.uuid4()), creator_id, result["ai_score"])
    storage.save_certificate(cert)
    storage.append_audit("certificate_issued", None, creator_id, {**details, "certificate_id": cert["certificate_id"]})
    return jsonify({
        "verified": True,
        "message": "Writing check passed. Your content now shows the Verified Human Creator badge.",
        "certificate": cert,
        "display": certificates.creator_verification(creator_id),
    }), 200


@app.get("/certificate/<certificate_id>")
@limiter.limit(READ_LIMIT)
def certificate_lookup(certificate_id):
    cert = storage.get_certificate(certificate_id)
    if cert is None:
        return error("not_found", "No certificate exists with that certificate_id.", 404)
    return jsonify({**cert, "valid": certificates.is_valid(cert)})


@app.get("/analytics")
@limiter.limit(READ_LIMIT)
def analytics_json():
    return jsonify(analytics.compute())


@app.get("/dashboard")
@limiter.limit(READ_LIMIT)
def dashboard():
    return Response(analytics.render_html(analytics.compute()), mimetype="text/html")


@app.get("/log")
@limiter.limit(READ_LIMIT)
def log():
    try:
        limit = int(request.args.get("limit", LOG_DEFAULT_LIMIT))
    except ValueError:
        return error("invalid_limit", "'limit' must be an integer.", 400)
    if limit < 1 or limit > LOG_MAX_LIMIT:
        return error("invalid_limit", f"'limit' must be between 1 and {LOG_MAX_LIMIT}.", 400)

    event = request.args.get("event")
    if event is not None and event not in LOG_EVENTS:
        return error("invalid_event", f"'event' must be one of {sorted(LOG_EVENTS)}.", 400)

    return jsonify({"entries": storage.get_log(limit=limit, event=event)})


@app.errorhandler(404)
def not_found(_):
    return error("not_found", "Endpoint not found.", 404)


@app.errorhandler(405)
def method_not_allowed(_):
    return error("method_not_allowed", "Method not allowed on this endpoint.", 405)


@app.errorhandler(429)
def rate_limited(exc):
    return error("rate_limited", f"Rate limit exceeded ({exc.description}). Try again later.", 429)


if __name__ == "__main__":
    # Default 5001: macOS AirPlay Receiver occupies port 5000.
    app.run(debug=True, port=int(os.environ.get("PORT", 5001)))
