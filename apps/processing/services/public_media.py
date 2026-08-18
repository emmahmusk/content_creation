import ipaddress
import re
import shutil
import socket
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings


class PublicMediaError(RuntimeError):
    pass


DIRECT_MEDIA_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".ogv", ".ogg", ".mp3", ".wav", ".m4a"}
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def assert_public_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise PublicMediaError("Only public HTTP(S) video or audio URLs are supported.")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise PublicMediaError("The media host could not be resolved.") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise PublicMediaError("Private or local-network media URLs are not allowed.")


def is_direct_media_url(url):
    return Path(urlparse(url).path).suffix.lower() in DIRECT_MEDIA_EXTENSIONS


def resolve_ffmpeg_location():
    """Return the actual FFmpeg path yt-dlp expects, not a bare command name."""
    configured = str(settings.FFMPEG_BINARY or "").strip()
    if not configured:
        return None
    candidate = Path(configured).expanduser()
    if candidate.exists():
        return str(candidate.resolve())
    discovered = shutil.which(configured)
    return str(Path(discovered).resolve()) if discovered else None


def resolve_js_runtime():
    """Resolve the JavaScript runtime required by yt-dlp's YouTube challenge solver."""
    configured = str(settings.YTDLP_JS_RUNTIME or "deno").strip()
    candidate = Path(configured).expanduser()
    if candidate.is_file():
        return str(candidate.resolve())
    discovered = shutil.which(configured)
    return str(Path(discovered).resolve()) if discovered else None


def download_with_ytdlp(url, work_directory):
    """Download one public video supported by yt-dlp and return its final path."""
    assert_public_url(url)
    try:
        import yt_dlp
    except ImportError as exc:
        raise PublicMediaError("Public video importing is unavailable because yt-dlp is not installed.") from exc
    work = Path(work_directory); work.mkdir(parents=True, exist_ok=True)
    output = str(work / "public-source-%(id)s.%(ext)s")
    ffmpeg_location = resolve_ffmpeg_location()
    js_runtime = resolve_js_runtime()
    options = {
        "outtmpl": output,
        "noplaylist": True,
        "restrictfilenames": True,
        "windowsfilenames": True,
        "max_filesize": settings.PUBLIC_MEDIA_MAX_BYTES,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "quiet": True,
        "no_warnings": True,
    }
    if js_runtime:
        options["js_runtimes"] = {"deno": {"path": js_runtime}}
    if ffmpeg_location:
        options.update({
            "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
            "merge_output_format": "mp4",
            "ffmpeg_location": ffmpeg_location,
        })
    else:
        # Progressive formats already contain video and audio, so yt-dlp does not
        # need to invoke FFmpeg merely to import the public source.
        options["format"] = "best[height<=1080][ext=mp4][vcodec!=none][acodec!=none]/best[height<=1080][vcodec!=none][acodec!=none]/best"
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
            candidates = []
            if info.get("requested_downloads"):
                candidates.extend(item.get("filepath") for item in info["requested_downloads"])
            candidates.extend([info.get("filepath"), downloader.prepare_filename(info)])
    except Exception as exc:
        message = ANSI_ESCAPE.sub("", str(exc)).strip()
        raise PublicMediaError(f"The public video could not be imported: {message}") from exc
    existing = [Path(item) for item in candidates if item and Path(item).exists()]
    if not existing:
        existing = sorted(work.glob("public-source-*"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not existing:
        raise PublicMediaError("The provider did not return a downloadable media file.")
    return existing[0]
