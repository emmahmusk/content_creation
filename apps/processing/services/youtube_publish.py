import tempfile
from pathlib import Path

import requests
from django.conf import settings
from django.utils import timezone

from apps.accounts.models import YouTubeAccount
from apps.accounts.services.youtube import YOUTUBE_SCOPES, decrypt_token, encrypt_token
from apps.processing.models import PublicationJob


def _download_clip(clip, target):
    url = clip.video_url
    maximum = int(getattr(settings, "YOUTUBE_UPLOAD_MAX_BYTES", 2 * 1024 * 1024 * 1024))
    if url:
        with requests.get(url, stream=True, timeout=(15, 120)) as response:
            response.raise_for_status()
            size = 0
            with open(target, "wb") as output:
                for chunk in response.iter_content(1024 * 1024):
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > maximum:
                        raise ValueError("This clip is larger than the configured YouTube upload limit.")
                    output.write(chunk)
        return
    if clip.video and clip.video.name:
        size = clip.video.size
        if size > maximum:
            raise ValueError("This clip is larger than the configured YouTube upload limit.")
        with clip.video.open("rb") as source, open(target, "wb") as output:
            while chunk := source.read(1024 * 1024):
                output.write(chunk)
        return
    raise ValueError("This clip has no rendered video file to upload yet.")


def _google_credentials(account):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    credentials = Credentials(
        token=decrypt_token(account.access_token_encrypted),
        refresh_token=decrypt_token(account.refresh_token_encrypted),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.YOUTUBE_CLIENT_ID,
        client_secret=settings.YOUTUBE_CLIENT_SECRET,
        scopes=account.scopes or YOUTUBE_SCOPES,
        expiry=account.token_expiry,
    )
    if not credentials.valid:
        if not credentials.refresh_token:
            raise ValueError("YouTube authorization expired. Disconnect and connect the channel again.")
        credentials.refresh(Request())
        account.access_token_encrypted = encrypt_token(credentials.token)
        account.token_expiry = credentials.expiry
        account.save(update_fields=["access_token_encrypted", "token_expiry", "updated_at"])
    return credentials


def publish_youtube_job(job_id):
    """Upload a rendered clip and persist the resulting YouTube video ID."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from django.db import close_old_connections

    close_old_connections()
    job = None
    try:
        job = PublicationJob.objects.select_related("clip", "user", "social_handle").get(pk=job_id)
        account = YouTubeAccount.objects.get(user=job.user)
        credentials = _google_credentials(account)
        payload = job.platform_payload or {}
        title = (payload.get("title") or job.clip.title).strip()[:100]
        description = (payload.get("caption") or job.clip.caption).strip()[:5000]
        privacy = payload.get("privacy_status", "unlisted")
        if privacy not in {"private", "unlisted", "public"}:
            privacy = "unlisted"
        with tempfile.TemporaryDirectory(prefix="kraftaa-youtube-") as temp_dir:
            video_path = str(Path(temp_dir) / "clip.mp4")
            _download_clip(job.clip, video_path)
            youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
            upload = youtube.videos().insert(
                part="snippet,status",
                body={"snippet": {"title": title or "Kraftaa clip", "description": description},
                      "status": {"privacyStatus": privacy}},
                media_body=MediaFileUpload(video_path, mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024),
            )
            result = upload.execute(num_retries=3)
        video_id = result.get("id")
        if not video_id:
            raise RuntimeError("YouTube completed the upload without returning a video ID.")
        job.external_id = video_id
        job.status = PublicationJob.Status.PUBLISHED
        job.error = ""
        job.save(update_fields=["external_id", "status", "error", "updated_at"])
    except Exception as exc:
        if job:
            job.status = PublicationJob.Status.FAILED
            job.error = str(exc)[:2000]
            job.save(update_fields=["status", "error", "updated_at"])
    finally:
        close_old_connections()


def youtube_video_url(video_id):
    return f"https://www.youtube.com/watch?v={video_id}"
