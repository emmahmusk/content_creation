import ipaddress
import os
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
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
YOUTUBE_RECOVERY_MESSAGE = (
    "YouTube could not verify this server. Your project is safe. Upload the original "
    "video or audio file to continue; if this is your channel, download the source from "
    "YouTube Studio first."
)


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


def is_youtube_url(url):
    hostname = (urlparse(url).hostname or "").lower()
    return hostname in YOUTUBE_HOSTS or hostname.endswith(".youtube.com")


def is_youtube_authentication_error(message):
    normalized = ANSI_ESCAPE.sub("", str(message or "")).lower()
    return any(
        marker in normalized
        for marker in (
            "sign in to confirm you’re not a bot",
            "sign in to confirm you're not a bot",
            "youtube could not verify this server",
            "youtube verification required",
        )
    )


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


def resolve_cookie_options():
    """Build yt-dlp cookie options without placing session data in source control."""
    cookie_file = str(getattr(settings, "YTDLP_COOKIES_FILE", "") or "").strip()
    if cookie_file:
        path = Path(cookie_file).expanduser()
        if not path.is_file():
            raise PublicMediaError(
                "The configured YouTube cookies file was not found. "
                "Check YTDLP_COOKIES_FILE and restart the worker."
            )
        return {"cookiefile": str(path.resolve())}

    browser_spec = str(getattr(settings, "YTDLP_COOKIES_FROM_BROWSER", "") or "").strip()
    if not browser_spec:
        return {}
    if os.getenv("RENDER", "").strip().lower() == "true":
        raise PublicMediaError(
            "YTDLP_COOKIES_FROM_BROWSER cannot be used on Render because the server has no "
            "signed-in browser profile. Upload youtube.cookies.txt as a Render Secret File, "
            "remove YTDLP_COOKIES_FROM_BROWSER, and set "
            "YTDLP_COOKIES_FILE=/etc/secrets/youtube.cookies.txt."
        )
    browser, separator, profile = browser_spec.partition(":")
    browser = browser.strip().lower()
    profile = profile.strip() if separator else None
    if not browser:
        raise PublicMediaError("YTDLP_COOKIES_FROM_BROWSER must name a browser, such as chrome or firefox.")
    return {"cookiesfrombrowser": (browser, profile or None, None, None)}


def resolve_po_token_options(url, using_cookies=False):
    """Configure an optional yt-dlp PO-token provider for YouTube server traffic."""
    provider_url = str(getattr(settings, "YTDLP_PO_TOKEN_PROVIDER_URL", "") or "").strip().rstrip("/")
    if not provider_url or not is_youtube_url(url):
        return {}
    parsed = urlparse(provider_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise PublicMediaError(
            "YTDLP_PO_TOKEN_PROVIDER_URL must be a complete HTTP(S) URL."
        )
    extractor_args = {
        "youtubepot-bgutilhttp": {"base_url": [provider_url]},
    }
    # mweb is yt-dlp's recommended client for provider-backed public video
    # requests. Account cookies and mweb are not combined because that client
    # does not support account-cookie authentication.
    if not using_cookies:
        extractor_args["youtube"] = {"player_client": ["mweb"]}
    return {"extractor_args": extractor_args}


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
    cookie_options = resolve_cookie_options()
    options.update(cookie_options)
    options.update(resolve_po_token_options(url, using_cookies=bool(cookie_options)))
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
        if is_youtube_url(url) and is_youtube_authentication_error(message):
            message = YOUTUBE_RECOVERY_MESSAGE
        raise PublicMediaError(f"The public video could not be imported: {message}") from exc
    existing = [Path(item) for item in candidates if item and Path(item).exists()]
    if not existing:
        existing = sorted(work.glob("public-source-*"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not existing:
        raise PublicMediaError("The provider did not return a downloadable media file.")
    return existing[0]
