import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings


class PublicMediaError(RuntimeError):
    pass


DIRECT_MEDIA_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".ogv", ".ogg", ".mp3", ".wav", ".m4a"}


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


def download_with_ytdlp(url, work_directory):
    """Download one public video supported by yt-dlp and return its final path."""
    assert_public_url(url)
    try:
        import yt_dlp
    except ImportError as exc:
        raise PublicMediaError("Public video importing is unavailable because yt-dlp is not installed.") from exc
    work = Path(work_directory); work.mkdir(parents=True, exist_ok=True)
    output = str(work / "public-source-%(id)s.%(ext)s")
    options = {
        "outtmpl": output,
        "noplaylist": True,
        "restrictfilenames": True,
        "windowsfilenames": True,
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "merge_output_format": "mp4",
        "max_filesize": settings.PUBLIC_MEDIA_MAX_BYTES,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "quiet": True,
        "no_warnings": True,
        "ffmpeg_location": settings.FFMPEG_BINARY,
    }
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
            candidates = []
            if info.get("requested_downloads"):
                candidates.extend(item.get("filepath") for item in info["requested_downloads"])
            candidates.extend([info.get("filepath"), downloader.prepare_filename(info)])
    except Exception as exc:
        raise PublicMediaError(f"The public video could not be imported: {exc}") from exc
    existing = [Path(item) for item in candidates if item and Path(item).exists()]
    if not existing:
        existing = sorted(work.glob("public-source-*"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not existing:
        raise PublicMediaError("The provider did not return a downloadable media file.")
    return existing[0]
