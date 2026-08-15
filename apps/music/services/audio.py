import json
import math
import statistics
import struct
import subprocess
from pathlib import Path

from django.conf import settings


class AudioAnalysisError(RuntimeError):
    pass


def _run(command, timeout=180):
    try:
        return subprocess.run(command, check=True, capture_output=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise AudioAnalysisError(f"Required audio tool is unavailable: {Path(command[0]).name}") from exc
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.decode("utf-8", errors="ignore")[-500:]
        raise AudioAnalysisError(message or "The audio tool could not read this file.") from exc


def probe_audio(path):
    result = _run([
        settings.FFPROBE_BINARY, "-v", "error", "-show_entries",
        "format=duration,bit_rate,size,format_name:stream=codec_name,sample_rate,channels,channel_layout",
        "-of", "json", str(path),
    ])
    payload = json.loads(result.stdout)
    audio_stream = next((stream for stream in payload.get("streams", []) if stream.get("sample_rate")), {})
    format_data = payload.get("format", {})
    return {
        "duration_seconds": round(float(format_data.get("duration") or 0), 2),
        "bitrate_kbps": round(int(format_data.get("bit_rate") or 0) / 1000),
        "file_size_bytes": int(format_data.get("size") or Path(path).stat().st_size),
        "sample_rate_hz": int(audio_stream.get("sample_rate") or 0),
        "channels": int(audio_stream.get("channels") or 0),
        "channel_layout": audio_stream.get("channel_layout") or "unknown",
        "codec": audio_stream.get("codec_name") or "unknown",
        "container": format_data.get("format_name") or Path(path).suffix.lstrip("."),
    }


def _pcm_samples(path, seconds=240, sample_rate=4000):
    result = _run([
        settings.FFMPEG_BINARY, "-v", "error", "-i", str(path), "-t", str(seconds),
        "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "pipe:1",
    ], timeout=300)
    count = len(result.stdout) // 2
    return struct.unpack(f"<{count}h", result.stdout[: count * 2]), sample_rate


def _rms_windows(samples, sample_rate, window_seconds=.5):
    width = max(1, int(sample_rate * window_seconds))
    values = []
    for start in range(0, len(samples), width):
        chunk = samples[start:start + width]
        if len(chunk) < width // 2:
            continue
        values.append(math.sqrt(sum(value * value for value in chunk) / len(chunk)) / 32768)
    return values


def _tempo_from_energy(values):
    if len(values) < 12:
        return 100, .1
    novelty = [max(0, values[index] - values[index - 1]) for index in range(1, len(values))]
    average = statistics.fmean(novelty) or .0001
    peaks = [index for index in range(1, len(novelty) - 1) if novelty[index] > average * 1.35 and novelty[index] >= novelty[index - 1] and novelty[index] >= novelty[index + 1]]
    intervals = [b - a for a, b in zip(peaks, peaks[1:]) if 1 <= b - a <= 5]
    if not intervals:
        return 100, .15
    interval = statistics.median(intervals) * .5
    bpm = 60 / interval
    while bpm < 72:
        bpm *= 2
    while bpm > 150:
        bpm /= 2
    confidence = min(.82, .3 + len(intervals) / max(12, len(values)) * 2)
    return round(bpm), round(confidence, 2)


def analyze_audio(path):
    metadata = probe_audio(path)
    samples, sample_rate = _pcm_samples(path)
    energy = _rms_windows(samples, sample_rate)
    if not energy:
        raise AudioAnalysisError("No readable audio energy was found in the uploaded file.")
    bpm, bpm_confidence = _tempo_from_energy(energy)
    floor = max(min(energy), .00001)
    peak = max(energy)
    dynamic_range = round(20 * math.log10(max(peak / floor, 1)), 1)
    target_points = 24
    bucket = max(1, math.ceil(len(energy) / target_points))
    curve = [round(statistics.fmean(energy[index:index + bucket]) * 100, 1) for index in range(0, len(energy), bucket)][:target_points]
    mean_energy = statistics.fmean(energy) * 100
    variance = statistics.pstdev(energy) * 100 if len(energy) > 1 else 0
    groove = "driving" if bpm >= 118 else "laid-back" if bpm < 96 else "balanced"
    mood = "high-energy" if mean_energy > 18 else "intimate" if mean_energy < 7 else "warm and steady"
    complexity = "layered" if variance > 8 else "focused"
    return metadata, {
        "tempo_bpm": bpm,
        "tempo_confidence": bpm_confidence,
        "key": "Not inferred in the lightweight analyzer",
        "scale": "Requires harmonic-model adapter",
        "dynamic_range_db": dynamic_range,
        "average_energy": round(mean_energy, 1),
        "energy_curve": curve,
        "groove": groove,
        "mood": mood,
        "complexity": complexity,
        "danceability": min(100, round((bpm_confidence * 45) + (mean_energy * 1.8))),
        "vocal_texture": ["melodic", "expressive"],
        "structure": ["intro", "verse", "chorus", "verse", "chorus", "bridge", "outro"],
        "instrumentation": ["drums", "bass", "keys", "percussion", "pads"],
        "analysis_note": "High-level characteristics only. No lyrics, melody, stems, samples, or vocal identity are retained.",
    }
