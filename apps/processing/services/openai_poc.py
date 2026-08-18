import json
import mimetypes
from pathlib import Path
from tempfile import TemporaryDirectory

import requests
from django.conf import settings

from . import media


class OpenAIConfigurationError(RuntimeError):
    pass


OPENAI_UPLOAD_LIMIT_BYTES = 24 * 1024 * 1024
TRANSCRIPTION_CHUNK_SECONDS = 15 * 60


def _headers():
    if not settings.OPENAI_API_KEY:
        raise OpenAIConfigurationError("OPENAI_API_KEY is not configured in .env.")
    return {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}


def _transcribe_file(path):
    """Transcribe one upload-safe file and normalize its timestamps."""
    path = Path(path)
    with path.open("rb") as audio:
        response = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers=_headers(),
            files={"file": (path.name, audio, mimetypes.guess_type(path.name)[0] or "application/octet-stream")},
            data={
                "model": settings.OPENAI_TRANSCRIPTION_MODEL,
                "response_format": "verbose_json",
                "timestamp_granularities[]": ["segment", "word"],
                "temperature": "0",
            },
            timeout=(20, 900),
        )
    response.raise_for_status()
    payload = response.json()
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
    """Return one timestamped transcript, chunking large audio automatically."""
    path = Path(audio_path)
    if path.stat().st_size <= OPENAI_UPLOAD_LIMIT_BYTES:
        return _transcribe_file(path)

    with TemporaryDirectory(prefix="recast-transcription-") as folder:
        chunks = media.split_audio(path, folder, TRANSCRIPTION_CHUNK_SECONDS)
        result = []
        for index, chunk in enumerate(chunks):
            if chunk.stat().st_size > OPENAI_UPLOAD_LIMIT_BYTES:
                raise ValueError("A compressed transcription chunk still exceeds OpenAI's upload limit.")
            offset_ms = index * TRANSCRIPTION_CHUNK_SECONDS * 1000
            result.extend(_offset_segments(_transcribe_file(chunk), offset_ms))
    return result


CLIP_SCHEMA = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array", "minItems": 1, "maxItems": 10,
            "items": {
                "type": "object",
                "properties": {
                    "rank": {"type": "integer"}, "title": {"type": "string"},
                    "hook": {"type": "string"}, "caption": {"type": "string"},
                    "start_ms": {"type": "integer"}, "end_ms": {"type": "integer"},
                    "score": {"type": "number", "minimum": 0, "maximum": 10},
                    "rationale": {"type": "string"},
                    "matched_preference": {"type": "string"},
                },
                "required": ["rank", "title", "hook", "caption", "start_ms", "end_ms", "score", "rationale", "matched_preference"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["clips", "summary"], "additionalProperties": False,
}


def _output_text(payload):
    if payload.get("output_text"):
        return payload["output_text"]
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                return content.get("text", "")
    raise RuntimeError("OpenAI returned no text output.")


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
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={**_headers(), "Content-Type": "application/json"},
        json={
            "model": settings.OPENAI_TEXT_MODEL,
            "instructions": "You are an expert short-form video editor. Use only evidence and timestamps supplied in the transcript.",
            "input": prompt,
            "text": {"format": {"type": "json_schema", "name": "clip_recommendations", "strict": True, "schema": CLIP_SCHEMA}},
        },
        timeout=(20, 300),
    )
    response.raise_for_status()
    result = json.loads(_output_text(response.json()))
    result["clips"] = result["clips"][:count]
    result.update({"social_posts": {}, "youtube": {}, "newsletter": {}})
    return result
