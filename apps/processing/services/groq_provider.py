import json
import logging
import mimetypes
from pathlib import Path
from tempfile import TemporaryDirectory

import requests
from django.conf import settings

from . import media


class GroqConfigurationError(RuntimeError):
    pass


# Stay below Groq's 25 MB free-tier file cap; larger recordings are split first.
GROQ_UPLOAD_LIMIT_BYTES = 24 * 1024 * 1024
TRANSCRIPTION_CHUNK_SECONDS = 15 * 60
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
logger = logging.getLogger(__name__)


def _response_telemetry(response, endpoint, model, error=None, usage=None):
    """Log safe Groq response metadata; never log prompts, files, or credentials."""
    headers = response.headers
    details = {
        "endpoint": endpoint,
        "model": model,
        "status": response.status_code,
        "request_id": headers.get("x-request-id") or headers.get("request-id"),
        "retry_after": headers.get("retry-after"),
        "limit_requests": headers.get("x-ratelimit-limit-requests"),
        "remaining_requests": headers.get("x-ratelimit-remaining-requests"),
        "reset_requests": headers.get("x-ratelimit-reset-requests"),
        "limit_tokens": headers.get("x-ratelimit-limit-tokens"),
        "remaining_tokens": headers.get("x-ratelimit-remaining-tokens"),
        "reset_tokens": headers.get("x-ratelimit-reset-tokens"),
    }
    if error:
        details.update(error)
    if usage is not None:
        details["usage"] = usage
    logger.log(
        logging.ERROR if response.status_code >= 400 else logging.INFO,
        "Groq API response %s",
        json.dumps(details, sort_keys=True, separators=(",", ":")),
    )


def _check_response(response, endpoint, model):
    if response.status_code < 400:
        return

    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        payload = {}
    error = payload.get("error", {}) if isinstance(payload, dict) else {}
    if not isinstance(error, dict):
        error = {"message": str(error)}
    message = str(error.get("message") or "Groq rejected the request.")[:600]
    code = error.get("code") or error.get("type")
    _response_telemetry(response, endpoint, model, {"error_code": code, "error_message": message})
    retry_after = response.headers.get("retry-after")
    suffix = f" Retry after {retry_after} seconds." if response.status_code == 429 and retry_after else ""
    raise requests.HTTPError(
        f"Groq returned HTTP {response.status_code}"
        f"{f' ({code})' if code else ''}: {message}{suffix}",
        response=response,
    )


def _headers():
    if not settings.GROQ_API_KEY:
        raise GroqConfigurationError("groq_api_key is not configured in .env.")
    return {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}


def generate_json(instructions, prompt, schema=None, name="response"):
    """Call Groq chat completions and return a JSON response as a Python object."""
    body = {
        "model": settings.GROQ_TEXT_MODEL,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": prompt},
        ],
        "response_format": (
            {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}}
            if schema
            else {"type": "json_object"}
        ),
    }
    response = requests.post(
        f"{GROQ_BASE_URL}/chat/completions",
        headers={**_headers(), "Content-Type": "application/json"},
        json=body,
        timeout=(20, 300),
    )
    _check_response(response, "chat/completions", settings.GROQ_TEXT_MODEL)
    payload = response.json()
    _response_telemetry(response, "chat/completions", settings.GROQ_TEXT_MODEL, usage=payload.get("usage"))
    choices = payload.get("choices", [])
    content = choices[0].get("message", {}).get("content") if choices else None
    if not content:
        raise RuntimeError("Groq returned no JSON content.")
    return json.loads(content)


def _transcribe_file(path, prompt=""):
    """Transcribe one upload-safe audio file and normalize timestamped words."""
    path = Path(path)
    with path.open("rb") as audio:
        response = requests.post(
            f"{GROQ_BASE_URL}/audio/transcriptions",
            headers=_headers(),
            files={"file": (path.name, audio, mimetypes.guess_type(path.name)[0] or "application/octet-stream")},
            data=[
                ("model", settings.GROQ_TRANSCRIPTION_MODEL),
                ("response_format", "verbose_json"),
                ("timestamp_granularities[]", "segment"),
                ("timestamp_granularities[]", "word"),
                ("temperature", "0"),
                *(([("prompt", prompt[:900])] if prompt else [])),
            ],
            timeout=(20, 900),
        )
    _check_response(response, "audio/transcriptions", settings.GROQ_TRANSCRIPTION_MODEL)
    payload = response.json()
    if payload.get("duration") is not None:
        _response_telemetry(response, "audio/transcriptions", settings.GROQ_TRANSCRIPTION_MODEL, usage={"audio_seconds": payload["duration"]})
    words = payload.get("words", [])
    result = []
    for segment in payload.get("segments", []):
        start, end = float(segment["start"]), float(segment["end"])
        segment_words = [
            {"word": word["word"], "start_ms": round(float(word["start"]) * 1000), "end_ms": round(float(word["end"]) * 1000)}
            for word in words
            if float(word.get("start", 0)) >= start and float(word.get("end", 0)) <= end
        ]
        result.append({
            "start_ms": round(start * 1000),
            "end_ms": round(end * 1000),
            "text": segment["text"].strip(),
            "words": segment_words,
        })
    if not result and payload.get("text"):
        result.append({"start_ms": 0, "end_ms": 1000, "text": payload["text"], "words": []})
    return result


def _offset_segments(segments, offset_ms):
    for segment in segments:
        segment["start_ms"] += offset_ms
        segment["end_ms"] += offset_ms
        for word in segment.get("words", []):
            word["start_ms"] += offset_ms
            word["end_ms"] += offset_ms
    return segments


def transcribe(audio_path, fallback_text=""):
    """Transcribe audio with Groq, splitting long audio into timestamp-safe chunks."""
    path = Path(audio_path)
    if path.stat().st_size <= GROQ_UPLOAD_LIMIT_BYTES:
        return _transcribe_file(path, fallback_text)

    with TemporaryDirectory(prefix="kraftaa-groq-transcription-") as folder:
        chunks = media.split_audio(path, folder, TRANSCRIPTION_CHUNK_SECONDS)
        result = []
        for index, chunk in enumerate(chunks):
            if chunk.stat().st_size > GROQ_UPLOAD_LIMIT_BYTES:
                raise ValueError("A compressed transcription chunk still exceeds Groq's upload limit.")
            offset_ms = index * TRANSCRIPTION_CHUNK_SECONDS * 1000
            result.extend(_offset_segments(_transcribe_file(chunk, fallback_text), offset_ms))
    return result


CLIP_SCHEMA = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rank": {"type": "integer"}, "title": {"type": "string"},
                    "hook": {"type": "string"}, "caption": {"type": "string"},
                    "start_ms": {"type": "integer"}, "end_ms": {"type": "integer"},
                    "score": {"type": "number", "minimum": 0, "maximum": 10},
                    "rationale": {"type": "string"}, "matched_preference": {"type": "string"},
                },
                "required": ["rank", "title", "hook", "caption", "start_ms", "end_ms", "score", "rationale", "matched_preference"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["clips", "summary"], "additionalProperties": False,
}


def plan_package(transcript, brief, duration_ms, preferences=None):
    preferences = preferences or {}
    count = max(1, min(int(preferences.get("desired_clip_count", 5)), 10))
    prompt = f"""Analyze this timestamped transcript and select exactly {count} distinct, self-contained moments.

The clipper defines an important moment as:
{preferences.get('importance_definition') or 'The most useful, engaging and self-contained moments.'}

Avoid:
{preferences.get('moments_to_avoid') or 'Introductions, repetition and incomplete thoughts.'}

Audience and content context:
{brief}

Allowed duration: {preferences.get('min_clip_seconds', 20)}-{preferences.get('max_clip_seconds', 60)} seconds.
Recording duration: {duration_ms} milliseconds.

Rules:
- Timestamps must come from the transcript and remain inside the recording.
- Start on a complete thought with immediate value; end after the thought resolves.
- Score relevance against the clipper's definition, standalone clarity, hook strength, information density and emotional impact.
- Avoid overlapping or semantically duplicate clips.
- Explain which preference each selection matched.

TRANSCRIPT:
{transcript[:90000]}"""
    result = generate_json(
        "You are an expert short-form video editor. Use only evidence and timestamps supplied in the transcript.",
        prompt,
        CLIP_SCHEMA,
        "clip_recommendations",
    )
    result["clips"] = result["clips"][:count]
    result.update({"social_posts": {}, "youtube": {}, "newsletter": {}})
    return result
