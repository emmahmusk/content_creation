import json
import re

from django.conf import settings

from apps.processing.services import groq_provider


class CreativeSafetyError(ValueError):
    pass


FORBIDDEN_PATTERNS = [
    r"sound like\s+[\w ]+", r"in the (?:style|voice) of\s+[\w ]+", r"imitate\s+[\w ]+",
    r"clone\s+[\w ]+", r"exactly like\s+[\w ]+",
]


def enforce_originality(direction):
    text = " ".join(str(value) for value in direction.values()).lower()
    if any(re.search(pattern, text) for pattern in FORBIDDEN_PATTERNS):
        raise CreativeSafetyError("Describe musical qualities—not an artist, celebrity, cloned voice, or identifiable performance style.")


def _groq_json(instructions, prompt, schema, name):
    return groq_provider.generate_json(instructions, prompt, schema, name)


REPORT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "genre_analysis": {"type": "string"}, "mood_analysis": {"type": "string"},
        "groove_analysis": {"type": "string"}, "arrangement": {"type": "string"},
        "musical_dna": {"type": "array", "items": {"type": "string"}},
        "creative_opportunities": {"type": "array", "items": {"type": "string"}},
        "inspiration_summary": {"type": "string"},
    },
    "required": ["genre_analysis", "mood_analysis", "groove_analysis", "arrangement", "musical_dna", "creative_opportunities", "inspiration_summary"],
}


SONG_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "title": {"type": "string"}, "concept": {"type": "string"}, "hook": {"type": "string"},
        "lyrics": {"type": "string"}, "arrangement": {"type": "array", "items": {"type": "string"}},
        "chord_map": {"type": "array", "items": {"type": "string"}},
        "melody_plan": {"type": "object", "additionalProperties": False, "properties": {
            "register": {"type": "string"}, "contour": {"type": "string"}, "rhythm": {"type": "string"},
        }, "required": ["register", "contour", "rhythm"]},
        "production_notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "concept", "hook", "lyrics", "arrangement", "chord_map", "melody_plan", "production_notes"],
}


def build_report(features):
    if settings.GROQ_API_KEY:
        return _groq_json(
            "You are a music intelligence analyst. Discuss only high-level musical characteristics. Never identify an artist, transcribe lyrics, reproduce melody, or suggest copied stems.",
            f"Create a concise AfroFusion producer report from these measured characteristics:\n{json.dumps(features)}",
            REPORT_SCHEMA, "music_intelligence_report",
        )
    if not settings.PIPELINE_ALLOW_MOCK_AI:
        raise RuntimeError("Groq is not configured and mock AI is disabled.")
    return {
        "genre_analysis": f"A {features['groove']} rhythmic foundation with room for AfroFusion interpretation.",
        "mood_analysis": f"The measured energy reads as {features['mood']}.",
        "groove_analysis": f"Approximately {features['tempo_bpm']} BPM with a {features['groove']} pulse.",
        "arrangement": "Contrast restrained verses with a wider, percussion-led chorus and a short bridge reset.",
        "musical_dna": [f"{features['tempo_bpm']} BPM pulse", features["groove"], features["mood"], features["complexity"]],
        "creative_opportunities": ["Use call-and-response in an original hook", "Let percussion evolve between sections", "Reserve harmonic lift for the final chorus"],
        "inspiration_summary": "Use the measured pacing and energy arc as a creative constraint while composing entirely new lyrics, harmony, melody, and instrumentation.",
    }


def generate_original_song(features, direction):
    enforce_originality(direction)
    prompt = f"""Create a completely original song package.
Measured reference characteristics (inspiration constraints only): {json.dumps(features)}
Creator direction: {json.dumps(direction)}

Rules:
- Do not mention or imitate any artist.
- Do not reproduce existing lyrics, hooks, melody, chord sequence, samples, or vocal identity.
- Lyrics must be newly written, culturally respectful, and rhythmically natural.
- Use section labels in the lyrics and include a memorable original chorus.
- Chord map and melody plan are compositional guidance, not transcriptions."""
    if settings.GROQ_API_KEY:
        return _groq_json(
            "You are an original AfroFusion songwriter and producer. Copyright safety and non-imitation are mandatory.",
            prompt, SONG_SCHEMA, "original_afrofusion_song",
        )
    if not settings.PIPELINE_ALLOW_MOCK_AI:
        raise RuntimeError("Groq is not configured and mock AI is disabled.")
    story = direction.get("story", "moving forward")
    language = direction.get("language", "english").title()
    return {
        "title": "Open Sky",
        "concept": f"An original {direction.get('genre', 'AfroFusion')} song about {story} for {direction.get('audience', 'a global audience')}.",
        "hook": "We rise with the morning, no shadow holding on",
        "lyrics": "[Verse 1]\nNew light on the road and my feet know the way\nI carry every lesson but I travel light today\n\n[Pre-Chorus]\nIf the night calls my name, I answer with the dawn\n\n[Chorus]\nWe rise with the morning, no shadow holding on\nHeart beat like a talking drum, steady till the fear is gone\nWe rise with the morning, every road becoming home\n\n[Verse 2]\nHands high for the people who believed before the proof\nNow the hope we kept in silence is a rhythm breaking through\n\n[Bridge]\nOne voice, then another, till the whole world sings along\n\n[Final Chorus]\nWe rise with the morning, no shadow holding on\nHeart beat like a talking drum, steady till the fear is gone",
        "arrangement": ["8-bar percussion intro", "Verse", "Pre-Chorus", "Chorus", "Verse", "Chorus", "Bridge", "Final Chorus", "Outro"],
        "chord_map": ["Verse: vi–IV–I–V", "Chorus: I–V–vi–IV", "Bridge: IV–V–iii–vi"],
        "melody_plan": {"register": direction.get("voice_profile", "warm"), "contour": "rising chorus with compact verse phrases", "rhythm": f"syncopated phrases around {features.get('tempo_bpm', 104)} BPM"},
        "production_notes": [f"Language direction: {language}", "Original percussion and bass performance", "No reference stems or samples", "Licensed or user-owned voice only"],
    }
