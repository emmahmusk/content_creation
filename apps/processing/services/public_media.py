import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse

class PublicMediaError(RuntimeError):
    pass


DIRECT_MEDIA_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".ogv", ".ogg", ".mp3", ".wav", ".m4a"}
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
YOUTUBE_RECOVERY_MESSAGE = (
    "Kraftaa cannot import YouTube links reliably because YouTube may block or rate-limit "
    "app-based downloads. Upload the original video or audio file instead. If it is your "
    "channel, download your upload from YouTube Studio first."
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


def is_youtube_import_error(message):
    normalized = (message or "").lower()
    return is_youtube_authentication_error(normalized) or any(
        phrase in normalized
        for phrase in (
            "429",
            "too many requests",
            "rate limit",
            "rate-limited",
            "cannot import youtube links reliably",
            "youtube may block app-based imports",
        )
    )
