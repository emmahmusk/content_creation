from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def token_cipher():
    key = getattr(settings, "YOUTUBE_TOKEN_ENCRYPTION_KEY", "")
    if not key:
        raise ImproperlyConfigured("Set YOUTUBE_TOKEN_ENCRYPTION_KEY before connecting YouTube.")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise ImproperlyConfigured("YOUTUBE_TOKEN_ENCRYPTION_KEY must be a valid Fernet key.") from exc


def encrypt_token(value):
    return token_cipher().encrypt(value.encode("utf-8")).decode("ascii") if value else ""


def decrypt_token(value):
    if not value:
        return ""
    try:
        return token_cipher().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ImproperlyConfigured("The saved YouTube token cannot be decrypted. Check YOUTUBE_TOKEN_ENCRYPTION_KEY.") from exc


def google_oauth_client_config():
    client_id = getattr(settings, "YOUTUBE_CLIENT_ID", "")
    client_secret = getattr(settings, "YOUTUBE_CLIENT_SECRET", "")
    redirect_uri = getattr(settings, "YOUTUBE_REDIRECT_URI", "")
    if not all((client_id, client_secret, redirect_uri)):
        raise ImproperlyConfigured("Set YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, and YOUTUBE_REDIRECT_URI.")
    return {"web": {
        "client_id": client_id,
        "client_secret": client_secret,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [redirect_uri],
    }}
