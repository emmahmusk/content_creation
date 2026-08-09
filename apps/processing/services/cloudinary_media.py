from pathlib import Path
import time

import requests
from django.conf import settings


class CloudinaryConfigurationError(RuntimeError):
    pass


def configured():
    return all([settings.CLOUDINARY_CLOUD_NAME, settings.CLOUDINARY_API_KEY, settings.CLOUDINARY_API_SECRET])


def _configure():
    if not configured():
        raise CloudinaryConfigurationError("Cloudinary fallback is enabled but its credentials are incomplete.")
    import cloudinary
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )


def ensure_uploaded(asset, source_path):
    """Upload once and persist only non-secret Cloudinary identifiers."""
    _configure()
    if asset.cloudinary_public_id:
        return {"public_id": asset.cloudinary_public_id, "secure_url": asset.cloudinary_url, "duration": asset.duration_seconds}
    import cloudinary.uploader
    path = Path(source_path)
    options = {"resource_type": "video", "folder": "recast/source", "use_filename": True, "unique_filename": True}
    if path.stat().st_size > 95 * 1024 * 1024:
        result = cloudinary.uploader.upload_large(str(path), chunk_size=10 * 1024 * 1024, **options)
    else:
        result = cloudinary.uploader.upload(str(path), **options)
    asset.cloudinary_public_id = result["public_id"]
    asset.cloudinary_url = result.get("secure_url", "")
    if result.get("duration") is not None:
        asset.duration_seconds = max(1, round(float(result["duration"])))
    asset.save(update_fields=["cloudinary_public_id", "cloudinary_url", "duration_seconds"])
    return result


def audio_url(public_id):
    _configure()
    import cloudinary.utils
    url, _ = cloudinary.utils.cloudinary_url(
        public_id,
        resource_type="video",
        format="mp3",
        secure=True,
        transformation=[{"audio_codec": "mp3", "audio_frequency": 16000, "bit_rate": "64k"}],
    )
    return url


def preview_url(public_id, start_ms, end_ms):
    """Build a lazy Cloudinary transformation URL; no eager render is required."""
    _configure()
    import cloudinary.utils
    start = round(max(0, start_ms) / 1000, 3)
    end = round(max(start_ms + 1000, end_ms) / 1000, 3)
    url, _ = cloudinary.utils.cloudinary_url(
        public_id,
        resource_type="video",
        format="mp4",
        secure=True,
        transformation=[
            {"start_offset": start, "end_offset": end},
            {"width": 540, "height": 960, "crop": "fill", "gravity": "auto"},
            {"quality": "auto", "fetch_format": "auto"},
        ],
    )
    return url


def download_audio(asset, source_path, destination):
    result = ensure_uploaded(asset, source_path)
    url = audio_url(result["public_id"])
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    response = None
    for attempt in range(10):
        response = requests.get(url, stream=True, timeout=(20, 600))
        if response.status_code not in {420, 423}:
            break
        response.close(); time.sleep(min(2 + attempt, 8))
    with response:
        response.raise_for_status()
        with open(destination, "wb") as output:
            for chunk in response.iter_content(1024 * 1024):
                if chunk: output.write(chunk)
    return destination, result
