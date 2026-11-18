import ipaddress
import re
import socket
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

class PublicMediaError(RuntimeError):
    pass


DIRECT_MEDIA_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".ogv", ".ogg", ".mp3", ".wav", ".m4a"}
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
GOOGLE_DRIVE_HOSTS = {"drive.google.com", "www.drive.google.com"}
DROPBOX_HOSTS = {"dropbox.com", "www.dropbox.com"}
YOUTUBE_RECOVERY_MESSAGE = (
    "Kraftaa cannot import YouTube links reliably because YouTube may block or rate-limit "
    "app-based downloads. Upload the original video or audio file instead. If it is your "
    "channel, download your upload from YouTube Studio first."
)


def assert_public_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
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


def shared_media_download_url(url):
    """Convert supported public share pages into provider download URLs."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    query = parse_qs(parsed.query, keep_blank_values=True)

    if host in GOOGLE_DRIVE_HOSTS:
        match = re.match(r"^/file/d/([A-Za-z0-9_-]{10,})(?:/|$)", parsed.path)
        file_id = match.group(1) if match else (query.get("id", [""])[0] if parsed.path in {"/open", "/uc"} else "")
        if not file_id or not re.fullmatch(r"[A-Za-z0-9_-]{10,}", file_id):
            raise PublicMediaError("Use a Google Drive share link to one video or audio file, not a folder or document.")
        download_params = {"id": file_id, "export": "download", "confirm": "t"}
        resource_key = query.get("resourcekey", [""])[0]
        if resource_key:
            download_params["resourcekey"] = resource_key
        return urlunparse(("https", "drive.usercontent.google.com", "/download", "", urlencode(download_params), ""))

    if host in DROPBOX_HOSTS:
        if not (re.match(r"^/s/[A-Za-z0-9_-]+/", parsed.path) or re.match(r"^/scl/fi/[A-Za-z0-9_-]+/", parsed.path)):
            raise PublicMediaError("Use a Dropbox share link to one video or audio file, not a folder.")
        query["dl"] = ["1"]
        query.pop("raw", None)
        normalized_query = urlencode([(key, value) for key, values in query.items() for value in values])
        return urlunparse(("https", "www.dropbox.com", parsed.path, "", normalized_query, ""))

    return url


def is_supported_shared_media_url(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in GOOGLE_DRIVE_HOSTS:
        return bool(re.match(r"^/file/d/[A-Za-z0-9_-]{10,}(?:/|$)", parsed.path) or (parsed.path in {"/open", "/uc"} and parse_qs(parsed.query).get("id")))
    if host in DROPBOX_HOSTS:
        return bool(re.match(r"^/s/[A-Za-z0-9_-]+/", parsed.path) or re.match(r"^/scl/fi/[A-Za-z0-9_-]+/", parsed.path))
    return False


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
            "youtube imports are cooling down",
            "youtube import failed",
            "youtube did not return",
            "cannot import youtube links reliably",
            "youtube may block app-based imports",
        )
    )
