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
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    run([settings.FFMPEG_BINARY,"-y","-i",str(source),"-vn","-ac","1","-ar","16000","-c:a","pcm_s16le",str(destination)])
    return destination

def clean_audio(source, destination):
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    run([settings.FFMPEG_BINARY,"-y","-i",str(source),"-af","highpass=f=70,lowpass=f=15000,afftdn=nf=-25,loudnorm=I=-16:TP=-1.5:LRA=11","-c:a","libmp3lame","-b:a","192k",str(destination)])
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

def render_vertical(source, start_ms, end_ms, subtitle, destination):
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    escaped=str(subtitle).replace("\\","/").replace(":","\\:").replace("'","\\'")
    vf=("scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x101714,"
        f"subtitles='{escaped}':force_style='FontName=Arial,FontSize=18,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=3,Outline=2,Shadow=0,Alignment=2,MarginV=170'")
    run([settings.FFMPEG_BINARY,"-y","-ss",f"{start_ms/1000:.3f}","-to",f"{end_ms/1000:.3f}","-i",str(source),"-vf",vf,"-c:v","libx264","-preset","medium","-crf","20","-c:a","aac","-b:a","160k","-movflags","+faststart",str(destination)])
    return destination

def extract_frame(source, timestamp_ms, destination):
    run([settings.FFMPEG_BINARY,"-y","-ss",f"{timestamp_ms/1000:.3f}","-i",str(source),"-frames:v","1","-q:v","2",str(destination)])
    return destination
