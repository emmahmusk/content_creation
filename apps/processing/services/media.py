import json, subprocess
from pathlib import Path
from django.conf import settings

class MediaError(RuntimeError): pass

def run(command):
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise MediaError(f"Required media tool is missing: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise MediaError(exc.stderr[-2000:] or "Media processing failed") from exc

def probe(path):
    result=run([settings.FFPROBE_BINARY,"-v","error","-show_streams","-show_format","-of","json",str(path)])
    return json.loads(result.stdout)

def extract_audio(source, destination):
    """Create a compact, speech-optimized track for transcription."""
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    run([
        settings.FFMPEG_BINARY,"-y","-i",str(source),"-vn","-map","0:a:0",
        "-ac","1","-ar","16000","-c:a","libmp3lame","-b:a","64k",str(destination),
    ])
    return destination

def split_audio(source, destination_directory, segment_seconds=900):
    """Re-encode audio into deterministic, upload-safe transcription chunks."""
    directory=Path(destination_directory);directory.mkdir(parents=True,exist_ok=True)
    pattern=directory/"chunk-%03d.mp3"
    run([
        settings.FFMPEG_BINARY,"-y","-i",str(source),"-vn","-map","0:a:0",
        "-ac","1","-ar","16000","-c:a","libmp3lame","-b:a","64k",
        "-f","segment","-segment_time",str(segment_seconds),"-reset_timestamps","1",str(pattern),
    ])
    chunks=sorted(directory.glob("chunk-*.mp3"))
    if not chunks: raise MediaError("FFmpeg did not produce any transcription chunks.")
    return chunks

def clean_audio(source, destination):
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    run([settings.FFMPEG_BINARY,"-y","-i",str(source),"-af","highpass=f=70,lowpass=f=15000,afftdn=nf=-25,loudnorm=I=-16:TP=-1.5:LRA=11","-c:a","libmp3lame","-b:a","192k",str(destination)])
    return destination

def render_audio_clip(source, start_ms, end_ms, destination):
    """Export a social-ready MP3 from the exact same range as the video clip."""
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    run([settings.FFMPEG_BINARY,"-y","-ss",f"{start_ms/1000:.3f}","-to",f"{end_ms/1000:.3f}","-i",str(source),"-vn","-af","loudnorm=I=-16:TP=-1.5:LRA=11","-c:a","libmp3lame","-b:a","192k",str(destination)])
    return destination

def srt_timestamp(ms):
    h, rem=divmod(ms,3600000); m, rem=divmod(rem,60000); s, milli=divmod(rem,1000)
    return f"{h:02}:{m:02}:{s:02},{milli:03}"

def write_srt(segments, start_ms, end_ms, destination):
    rows=[]; index=1
    for seg in segments:
        if seg.end_ms <= start_ms or seg.start_ms >= end_ms: continue
        local_start=max(seg.start_ms,start_ms)-start_ms; local_end=min(seg.end_ms,end_ms)-start_ms
        rows.extend([str(index),f"{srt_timestamp(local_start)} --> {srt_timestamp(local_end)}",seg.text.strip(),""]); index+=1
    Path(destination).write_text("\n".join(rows), encoding="utf-8")
    return destination

def normalize_broll_asset(source, destination, duration_ms):
    """Turn a generated image or stock/generated video into a silent 9:16 insert."""
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    duration = max(1.8, min(duration_ms / 1000, 5.0))
    image_suffixes = {".jpg", ".jpeg", ".png", ".webp"}
    if Path(source).suffix.lower() in image_suffixes:
        command = [settings.FFMPEG_BINARY, "-y", "-loop", "1", "-i", str(source), "-t", f"{duration:.3f}"]
        vf = (
            "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            "zoompan=z='min(zoom+0.0007,1.08)':x='iw/2-(iw/zoom/2)':"
            "y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30,format=yuv420p"
        )
    else:
        command = [settings.FFMPEG_BINARY, "-y", "-stream_loop", "-1", "-i", str(source), "-t", f"{duration:.3f}"]
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p"
    run(command + ["-an", "-vf", vf, "-r", "30", "-c:v", "libx264", "-preset", "fast", "-crf", "22", str(destination)])
    return destination


def render_vertical(source, start_ms, end_ms, subtitle, destination, broll_segments=None):
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    escaped=str(subtitle).replace("\\","/").replace(":","\\:").replace("'","\\'")
    duration=max(1.0,(end_ms-start_ms)/1000)
    info=probe(source)
    has_video=any(stream.get("codec_type")=="video" for stream in info.get("streams",[]))
    command=[settings.FFMPEG_BINARY,"-y"]
    if has_video:
        command += ["-ss",f"{start_ms/1000:.3f}","-t",f"{duration:.3f}","-i",str(source)]
        audio_index=0
        base_filter="[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x101714,setsar=1[base]"
        next_input=1
    else:
        command += ["-f","lavfi","-t",f"{duration:.3f}","-i","color=c=0x101714:s=1080x1920:r=30","-ss",f"{start_ms/1000:.3f}","-t",f"{duration:.3f}","-i",str(source)]
        audio_index=1
        base_filter="[0:v]setsar=1[base]"
        next_input=2
    segments=[item for item in (broll_segments or []) if Path(item["path"]).exists()]
    for item in segments:
        command += ["-i",str(item["path"])]
    filters=[base_filter]
    current="base"
    for index,item in enumerate(segments):
        start=max(0,float(item.get("start_ms",0))/1000)
        end=min(duration,start+(float(item.get("duration_ms",3000))/1000))
        input_index=next_input+index
        filters.append(f"[{input_index}:v]setpts=PTS-STARTPTS+{start:.3f}/TB[b{index}]")
        filters.append(f"[{current}][b{index}]overlay=0:0:eof_action=pass:enable='between(t,{start:.3f},{end:.3f})'[mix{index}]")
        current=f"mix{index}"
    filters.append(
        f"[{current}]subtitles='{escaped}':force_style='FontName=Arial,FontSize={settings.SUBTITLE_FONT_SIZE},PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,BorderStyle=1,Outline=1,Shadow=0,Alignment=2,MarginV={settings.SUBTITLE_MARGIN_V}'[vout]"
    )
    command += ["-filter_complex",";".join(filters),"-map","[vout]","-map",f"{audio_index}:a?","-t",f"{duration:.3f}","-c:v","libx264","-preset","medium","-crf","20","-c:a","aac","-b:a","160k","-movflags","+faststart","-shortest",str(destination)]
    run(command)
    return destination

def extract_frame(source, timestamp_ms, destination):
    run([settings.FFMPEG_BINARY,"-y","-ss",f"{timestamp_ms/1000:.3f}","-i",str(source),"-frames:v","1","-q:v","2",str(destination)])
    return destination
