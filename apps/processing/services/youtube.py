"""Best-effort, single-video imports and metadata-only operator checks."""
import json
import os
import random
import re
import shutil
import time
import hashlib
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.core.cache import cache
import yt_dlp

from .public_media import PublicMediaError, YOUTUBE_HOSTS, YOUTUBE_RECOVERY_MESSAGE


def canonical_url(url):
    parsed = urlparse(url)
    if (parsed.scheme not in {"http", "https"} or parsed.hostname not in YOUTUBE_HOSTS
            or parsed.username or parsed.password or parsed.port not in {None, 80, 443}):
        raise PublicMediaError("Provide a YouTube video URL.")
    query = parse_qs(parsed.query)
    if "list" in query or parsed.path.startswith(("/playlist", "/channel", "/@")):
        raise PublicMediaError("YouTube playlists and channels are not supported. Provide one video URL.")
    parts = parsed.path.strip("/").split("/")
    video_id = (parts[0] if parsed.hostname == "youtu.be" else
                parts[1] if len(parts) == 2 and parts[0] in {"shorts", "embed", "live"} else
                query.get("v", [""])[0] if parsed.path == "/watch" else "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise PublicMediaError("Provide a valid single YouTube video URL.")
    return f"https://www.youtube.com/watch?v={video_id}"


class _QuietLogger:
    # Provider diagnostics can contain signed media URLs, cookie paths and proxy credentials.
    def debug(self, message): pass
    def info(self, message): pass
    def warning(self, message): pass
    def error(self, message): pass


@contextmanager
def _request_slot():
    """Serialize imports across processes sharing MEDIA_ROOT; persist cooldowns."""
    directory = Path(settings.MEDIA_ROOT) / ".youtube"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "requests.lock").open("a+b") as handle:
        handle.seek(0, 2)
        if not handle.tell():
            handle.write(b" ")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise PublicMediaError("Another YouTube import is running. Try again later.") from None
        try:
            handle.seek(1)
            raw = handle.read()
            try:
                state = json.loads(raw) if raw.strip() else {}
                next_request = float(state.get("next_request", 0))
            except (ValueError, KeyError, TypeError):
                raise PublicMediaError("YouTube request state is invalid; contact the operator.") from None
            if next_request > time.time():
                wait = next_request - time.time()
                if state.get("blocked") or wait > settings.YOUTUBE_SLEEP_MAX + 1:
                    raise PublicMediaError("YouTube imports are cooling down. Try again later or upload the original file.")
                time.sleep(wait)
            cooldown = random.uniform(settings.YOUTUBE_SLEEP_MIN, settings.YOUTUBE_SLEEP_MAX)
            blocked = False
            try:
                yield
            except yt_dlp.utils.DownloadError as exc:
                message = str(exc).lower()
                if any(word in message for word in ("429", "too many requests", "rate limit", "not a bot", "sign in to confirm", "403", "forbidden")):
                    cooldown = settings.YOUTUBE_BLOCK_COOLDOWN_SECONDS
                    blocked = True
                raise
            finally:
                handle.seek(1)
                handle.truncate()
                handle.write(json.dumps({"next_request": time.time() + cooldown, "blocked": blocked}).encode())
                handle.flush()
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def _options(directory, *, simulate, use_auth=False, check_active=None):
    sizes = {}

    def progress(event):
        if check_active:
            check_active()
        sizes[event.get("filename", "media")] = event.get("downloaded_bytes", 0)
        if sum(sizes.values()) > settings.PUBLIC_MEDIA_MAX_BYTES:
            raise PublicMediaError("YouTube source exceeds the configured import size limit.")

    def validate(info, *, incomplete=False):
        if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming", "post_live"}:
            raise PublicMediaError("Live and upcoming YouTube streams are not supported.")
        if info.get("filesize", 0) and info["filesize"] > settings.PUBLIC_MEDIA_MAX_BYTES:
            raise PublicMediaError("YouTube source exceeds the configured import size limit.")

    options = {
        "format": f"bestvideo[height<={settings.YOUTUBE_MAX_HEIGHT}]+bestaudio/best[height<={settings.YOUTUBE_MAX_HEIGHT}]",
        "outtmpl": str(Path(directory) / "source.%(ext)s"),
        "merge_output_format": "mkv", "ffmpeg_location": shutil.which(settings.FFMPEG_BINARY) or settings.FFMPEG_BINARY,
        "noplaylist": True, "allowed_extractors": ["youtube"],
        "simulate": simulate, "skip_download": simulate,
        "sleep_interval": settings.YOUTUBE_SLEEP_MIN,
        "max_sleep_interval": settings.YOUTUBE_SLEEP_MAX,
        "sleep_interval_requests": settings.YOUTUBE_SLEEP_REQUESTS,
        "retries": 0, "fragment_retries": 0, "extractor_retries": 0,
        "socket_timeout": 30, "concurrent_fragment_downloads": 1,
        "max_filesize": settings.PUBLIC_MEDIA_MAX_BYTES,
        "writesubtitles": False, "writeautomaticsub": False,
        "writethumbnail": False, "writeinfojson": False, "writedescription": False,
        "quiet": True, "noprogress": True, "logger": _QuietLogger(),
        "cachedir": False, "geo_bypass": False,
        "match_filter": validate, "progress_hooks": [progress],
        # Explicit empty proxy disables unexpected inherited proxy configuration.
        "proxy": settings.YOUTUBE_PROXY_URL,
        "js_runtimes": {settings.YOUTUBE_JS_RUNTIME: {}},
    }
    if settings.YOUTUBE_IP_FAMILY in {"4", "6"}:
        options["source_address"] = "0.0.0.0" if settings.YOUTUBE_IP_FAMILY == "4" else "::"
    if use_auth:
        if settings.YOUTUBE_COOKIE_FILE and settings.YOUTUBE_COOKIES_BROWSER:
            raise PublicMediaError("Configure a cookie file or a browser, not both.")
        if settings.YOUTUBE_COOKIE_FILE:
            if not Path(settings.YOUTUBE_COOKIE_FILE).is_file():
                raise PublicMediaError("The configured YouTube cookie file is missing.")
            # yt-dlp may write its jar on close. Keep the operator's original read-only.
            cookie_copy = Path(directory) / "session.cookies.txt"
            shutil.copyfile(settings.YOUTUBE_COOKIE_FILE, cookie_copy)
            options["cookiefile"] = str(cookie_copy)
        elif settings.YOUTUBE_COOKIES_BROWSER:
            options["cookiesfrombrowser"] = (settings.YOUTUBE_COOKIES_BROWSER, settings.YOUTUBE_BROWSER_PROFILE or None)
        else:
            raise PublicMediaError("Authenticated testing requires an operator-configured cookie source.")
    return options


def import_video(url, work, *, simulate=True, use_auth=False, check_active=None, include_context=False):
    url = canonical_url(url)
    if not simulate and not settings.YOUTUBE_IMPORTS_ENABLED:
        raise PublicMediaError(YOUTUBE_RECOVERY_MESSAGE)
    if check_active:
        check_active()
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    try:
        with TemporaryDirectory(prefix="youtube-", dir=work) as temporary:
            options = _options(temporary, simulate=simulate, use_auth=use_auth, check_active=check_active)
            with _request_slot(), yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(url, download=not simulate)
            if not info or info.get("_type") in {"playlist", "multi_video"}:
                raise PublicMediaError("No single YouTube video was available.")
            options["match_filter"](info)
            if simulate:
                result = {key: info.get(key) for key in ("id", "title", "duration", "live_status")}
                if include_context:
                    result.update(description=str(info.get("description") or "")[:4000],
                                  channel=str(info.get("channel") or info.get("uploader") or "")[:200])
                return result
            if check_active:
                check_active()
            files = [path for path in Path(temporary).glob("source.*") if path.suffix in {".mp4", ".mkv", ".webm"}]
            if len(files) != 1 or not files[0].stat().st_size:
                raise PublicMediaError("YouTube did not return a complete media file within the import limit.")
            if files[0].stat().st_size > settings.PUBLIC_MEDIA_MAX_BYTES:
                raise PublicMediaError("YouTube source exceeds the configured import size limit.")
            destination = work / f"youtube-source{files[0].suffix}"
            shutil.move(str(files[0]), destination)
            return destination
    except yt_dlp.utils.DownloadError:
        raise PublicMediaError(YOUTUBE_RECOVERY_MESSAGE) from None
    except (yt_dlp.utils.YoutubeDLError, OSError, ValueError):
        raise PublicMediaError("YouTube import failed. Check the runtime, proxy, cookie configuration and media storage, or upload the original file.") from None


def metadata(url):
    """Cache bounded public metadata so repeated brief edits make fewer requests."""
    url = canonical_url(url)
    key = "youtube-metadata:" + hashlib.sha256(url.encode()).hexdigest()
    result = cache.get(key)
    if result is None:
        with TemporaryDirectory(prefix="youtube-metadata-") as temporary:
            result = import_video(url, temporary, simulate=True, include_context=True)
        cache.set(key, result, 300)
    return result
