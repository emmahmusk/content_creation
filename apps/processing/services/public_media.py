import ipaddress
import socket
import time
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from apps.processing.services.run_control import PipelineCancelled


class PublicMediaError(RuntimeError):
    pass


DIRECT_MEDIA_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".ogv", ".ogg", ".mp3", ".wav", ".m4a"}
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
    normalized = (message or "").lower()
    return any(
        phrase in normalized
        for phrase in (
            "could not verify this server",
            "sign in to confirm",
            "not a bot",
            "loginrequired",
            "http error 403",
            "403 forbidden",
        )
    )


def download_with_pytubefix(url, work_directory, run):
    """Download one authorized YouTube source, using the owner's device approval."""
    assert_public_url(url)
    if not is_youtube_url(url):
        raise PublicMediaError("This downloader accepts YouTube video links only.")
    try:
        from pytubefix import YouTube
    except ImportError as exc:
        raise PublicMediaError("YouTube importing is unavailable because pytubefix is not installed.") from exc
    work = Path(work_directory)
    work.mkdir(parents=True, exist_ok=True)
    token_file = work / "youtube-oauth-tokens.json"
    oauth_timeout_seconds = 10 * 60

    def request_user_approval(verification_url, user_code):
        from apps.processing.models import PipelineRun

        PipelineRun.objects.filter(pk=run.pk).update(
            youtube_auth_url=verification_url,
            youtube_auth_code=user_code,
            youtube_auth_confirmed=False,
        )
        deadline = time.monotonic() + oauth_timeout_seconds
        while time.monotonic() < deadline:
            current = PipelineRun.objects.only("status", "youtube_auth_confirmed").get(pk=run.pk)
            if current.status == PipelineRun.Status.CANCELLED:
                raise PipelineCancelled("Analysis stopped by the customer.")
            if current.youtube_auth_confirmed:
                return
            time.sleep(2)
        raise PublicMediaError(
            "YouTube sign-in expired before approval. Start the analysis again and complete the sign-in prompt."
        )

    try:
        video = YouTube(
            url,
            use_oauth=True,
            allow_oauth_cache=True,
            token_file=str(token_file),
            oauth_verifier=request_user_approval,
        )
        streams = video.streams.filter(progressive=True, file_extension="mp4")
        eligible = []
        for stream in streams:
            try:
                height = int(str(stream.resolution or "").rstrip("p"))
            except (TypeError, ValueError):
                continue
            size = getattr(stream, "filesize", None) or getattr(stream, "filesize_approx", None)
            if height <= 1080 and (not size or size <= settings.PUBLIC_MEDIA_MAX_BYTES):
                eligible.append((height, stream))
        if not eligible:
            raise PublicMediaError(
                "YouTube did not offer a progressive MP4 within the configured import limits. "
                "Upload the original recording to continue."
            )
        _, selected_stream = max(eligible, key=lambda item: item[0])
        downloaded = selected_stream.download(
            output_path=str(work),
            filename="public-source-youtube.mp4",
        )
    except Exception as exc:
        if isinstance(exc, PipelineCancelled):
            raise
        if isinstance(exc, PublicMediaError):
            raise
        message = str(exc).strip()
        normalized = message.lower()
        if any(token in normalized for token in ("bot", "403", "forbidden", "loginrequired")):
            message = YOUTUBE_RECOVERY_MESSAGE
        raise PublicMediaError(f"The YouTube video could not be imported: {message}") from exc
    finally:
        # Device-flow access tokens are scoped to this import and must not survive in
        # failed work directories that are retained for debugging or retries.
        token_file.unlink(missing_ok=True)
    downloaded_path = Path(downloaded)
    if not downloaded_path.is_file():
        raise PublicMediaError("YouTube did not return a local video file.")
    if downloaded_path.stat().st_size > settings.PUBLIC_MEDIA_MAX_BYTES:
        downloaded_path.unlink(missing_ok=True)
        raise PublicMediaError("This YouTube video exceeds the configured import size limit.")
    return downloaded_path
