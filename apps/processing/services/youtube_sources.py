"""Retain downloaded originals through review, then remove only managed sources."""
import logging
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.utils import timezone

from . import cloudinary_media, youtube
from .public_media import PublicMediaError, is_youtube_url, YOUTUBE_RECOVERY_MESSAGE

logger = logging.getLogger(__name__)


def source(asset, work, check_active=None):
    if not settings.YOUTUBE_IMPORTS_ENABLED:
        raise PublicMediaError(YOUTUBE_RECOVERY_MESSAGE)
    if not asset.rights_confirmed:
        raise PublicMediaError("Confirm your rights before importing a YouTube video.")
    youtube.canonical_url(asset.external_url)
    if asset.imported_file:
        try:
            cached = Path(asset.imported_file.path)
            if cached.is_file():
                return cached
        except (ValueError, NotImplementedError):
            pass
    if asset.cloudinary_public_id:
        if not asset.youtube_imported_at:
            asset.youtube_imported_at = timezone.now()
            asset.save(update_fields=["youtube_imported_at"])
        return cloudinary_media.download_source(asset, work / "youtube-restored.mkv")
    downloaded = youtube.import_video(asset.external_url, work, simulate=False, check_active=check_active)
    if check_active:
        check_active()
    try:
        with downloaded.open("rb") as handle:
            asset.imported_file.save(f"youtube-{asset.pk}{downloaded.suffix}", File(handle), save=False)
        asset.youtube_imported_at = timezone.now()
        asset.original_filename = f"youtube-{asset.pk}{downloaded.suffix}"
        asset.save(update_fields=["imported_file", "youtube_imported_at", "original_filename"])
    except Exception:
        if asset.imported_file:
            asset.imported_file.delete(save=False)
        raise
    return downloaded


def discard(asset):
    """Delete the managed original, retaining markers if cleanup needs retrying."""
    if not asset.youtube_imported_at:
        return True
    if asset.order.pipeline_runs.filter(status="running").exists():
        return False
    try:
        if asset.imported_file:
            asset.imported_file.delete(save=False)
            asset.save(update_fields=["imported_file"])
        if asset.cloudinary_public_id and is_youtube_url(asset.external_url) and not asset.file:
            cloudinary_media.delete_source(asset)
            asset.order.clips.exclude(preview_url="").update(preview_url="")
        asset.youtube_imported_at = None
        asset.save(update_fields=["youtube_imported_at"])
        return True
    except Exception:
        # Do not turn completed exports into a failed/charged-again production job.
        # Avoid provider exception text which may include credentials.
        logger.warning("YouTube source cleanup needs retry for asset %s", asset.pk)
        return False


def discard_order_sources(order):
    return all([discard(asset) for asset in order.source_assets.exclude(youtube_imported_at=None)])
