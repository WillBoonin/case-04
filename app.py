from datetime import datetime, timezone
import hashlib
from flask import Flask, request, jsonify
from flask_cors import CORS
from pydantic import ValidationError
from models import SurveySubmission, StoredSurveyRecord
from storage import append_json_line

app = Flask(__name__)
# Allow cross-origin requests so the static HTML can POST from localhost or file://
CORS(app, resources={r"/v1/*": {"origins": "*"}})

def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

@app.route("/ping", methods=["GET"])
def ping():
    """Simple health check endpoint."""
    return jsonify({
        "status": "ok",
        "message": "API is alive",
        "utc_time": datetime.now(timezone.utc).isoformat()
    })

@app.post("/v1/survey")
def submit_survey():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "invalid_json", "detail": "Body must be application/json"}), 400

    try:
        submission = SurveySubmission(**payload)
    except ValidationError as ve:
        return jsonify({"error": "validation_error", "detail": ve.errors()}), 422

    now_utc = datetime.now(timezone.utc)

    # Hash PII for storage
    email_hash = _sha256(str(submission.email))
    age_hash = _sha256(str(submission.age))

    # Use provided submission_id or derive from email + YYYYMMDDHH (UTC)
    sub_id = submission.submission_id or _sha256(
        f"{submission.email}{now_utc.strftime('%Y%m%d%H')}"
    )

    # Prefer payload user_agent, else fall back to header
    ua = submission.user_agent or request.headers.get("User-Agent")

    record = StoredSurveyRecord(
        name=submission.name,
        email_sha256=email_hash,
        age_sha256=age_hash,
        consent=submission.consent,
        rating=submission.rating,
        comments=submission.comments or "",
        user_agent=ua,
        submission_id=sub_id,
        received_at=now_utc,
        ip=request.headers.get("X-Forwarded-For", request.remote_addr or "")
    )

    append_json_line(record.dict())
    return jsonify({"status": "ok"}), 201

if __name__ == "__main__":
    app.run(port=5000, debug=True)
