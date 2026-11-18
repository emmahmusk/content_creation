"""Upload/verify sources before a job can depend on another service's disk."""
import time
import uuid
from pathlib import Path

from django.conf import settings
from django.core import signing
from django.db import transaction

from . import cloudinary_media
from .public_media import DIRECT_MEDIA_EXTENSIONS

SALT = "kraftaa-source-upload-v1"


class SourceHandoffError(RuntimeError):
    pass


def required():
    return settings.PIPELINE_EXECUTION_MODE == "celery"


def _validate_file(name, size):
    name = str(name).replace("\\", "/").split("/")[-1][:255]
    if Path(name).suffix.lower() not in DIRECT_MEDIA_EXTENSIONS:
        raise SourceHandoffError("Choose a supported video or audio recording.")
    if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= settings.PUBLIC_MEDIA_MAX_BYTES:
        raise SourceHandoffError("The recording is empty or exceeds the configured upload limit.")
    return name


def _metadata(result, filename):
    if (result.get("resource_type") != "video" or result.get("type", "upload") != "upload"
            or not result.get("public_id") or not result.get("secure_url", "").startswith("https://")):
        raise SourceHandoffError("The recording has not finished uploading. Please retry.")
    size = result.get("bytes")
    if not isinstance(size, int) or not 0 < size <= settings.PUBLIC_MEDIA_MAX_BYTES:
        raise SourceHandoffError("The uploaded recording exceeds the configured size limit or is incomplete.")
    duration = result.get("duration")
    return {"file": "", "external_url": "", "original_filename": filename,
            "cloudinary_public_id": result["public_id"], "cloudinary_url": result["secure_url"],
            "duration_seconds": max(1, round(float(duration))) if duration is not None else None}


def issue_upload(user, filename, size):
    filename = _validate_file(filename, size)
    if not settings.CLOUDINARY_DIRECT_UPLOADS_ENABLED or not cloudinary_media.configured():
        raise SourceHandoffError("Recording uploads are unavailable. Please contact support.")
    cloudinary_media._configure()
    from cloudinary.utils import api_sign_request
    public_id = f"recast/source/incoming/{user.pk}/{uuid.uuid4().hex}"
    params = {"timestamp": int(time.time()), "public_id": public_id, "overwrite": "false"}
    return {
        "upload_url": f"https://api.cloudinary.com/v1_1/{settings.CLOUDINARY_CLOUD_NAME}/video/upload",
        "api_key": settings.CLOUDINARY_API_KEY, "params": params,
        "signature": api_sign_request(params, settings.CLOUDINARY_API_SECRET),
        "token": signing.dumps({"user": user.pk, "public_id": public_id, "filename": filename}, salt=SALT),
        "chunk_bytes": 6_000_000,
    }


def verify_upload(token, user):
    try:
        data = signing.loads(token, salt=SALT, max_age=3600)
    except signing.BadSignature:
        raise SourceHandoffError("This upload has expired or is invalid. Choose the recording again.") from None
    if data.get("user") != user.pk or not str(data.get("public_id", "")).startswith(f"recast/source/incoming/{user.pk}/"):
        raise SourceHandoffError("This upload does not belong to your account.")
    if not cloudinary_media.configured():
        raise SourceHandoffError("Recording storage is unavailable. Please contact support.")
    cloudinary_media._configure()
    import cloudinary.api
    try:
        result = cloudinary.api.resource(data["public_id"], resource_type="video", timeout=30)
        if result.get("public_id") != data["public_id"]:
            raise SourceHandoffError("The recording could not be verified.")
        return _metadata(result, data["filename"])
    except SourceHandoffError:
        raise
    except Exception:
        raise SourceHandoffError("The uploaded recording could not be verified. Please retry shortly.") from None


def claim_upload(metadata, user):
    """Call inside the creation transaction; serialize replay checks per owner."""
    from django.contrib.auth import get_user_model
    from apps.orders.models import SourceAsset
    get_user_model().objects.select_for_update().get(pk=user.pk)
    if SourceAsset.objects.filter(cloudinary_public_id=metadata["cloudinary_public_id"]).exists():
        raise SourceHandoffError("This recording is already attached to a project. Upload it again for a new project.")


def upload_file(uploaded, user_id):
    """Server-side fallback for API clients and browsers without direct upload."""
    name = _validate_file(uploaded.name, uploaded.size)
    if not cloudinary_media.configured():
        if required():
            raise SourceHandoffError("Cloudinary must be configured before recordings can be queued for processing.")
        return None
    cloudinary_media._configure()
    import cloudinary.uploader
    options = {"resource_type": "video", "public_id": f"recast/source/uploads/{user_id}/{uuid.uuid4().hex}",
               "overwrite": False, "timeout": 120}
    try:
        uploaded.seek(0)
        if uploaded.size > 95 * 1024 * 1024:
            result = cloudinary.uploader.upload_large(uploaded, chunk_size=6_000_000, **options)
        else:
            result = cloudinary.uploader.upload(uploaded, **options)
        return _metadata(result, name)
    except SourceHandoffError:
        raise
    except Exception:
        raise SourceHandoffError("The recording could not be stored. Please retry; processing has not been queued.") from None


def ensure_ready(asset):
    """Migrate older local uploads before dispatch; remove local copies after commit."""
    if not asset:
        return
    if asset.cloudinary_public_id:
        if required() and not cloudinary_media.configured():
            raise SourceHandoffError("Cloudinary must be configured on the web service and worker.")
        return
    if not asset.file:
        return  # URL sources are fetched by the worker.
    try:
        with asset.file.open("rb") as handle:
            metadata = upload_file(handle, asset.order.customer_id)
    except (OSError, ValueError):
        raise SourceHandoffError("The recording is no longer on this server. Please upload it again.") from None
    if metadata is None:
        return
    old_storage, old_name = asset.file.storage, asset.file.name
    for key, value in metadata.items():
        setattr(asset, key, value)
    asset.save(update_fields=list(metadata))
    def remove_local_copy():
        try:
            old_storage.delete(old_name)
        except Exception:
            import logging
            logging.getLogger(__name__).warning("Local source cleanup needs retry for asset %s", asset.pk)
    transaction.on_commit(remove_local_copy)


def prepare_run(run_id):
    from apps.processing.models import PipelineRun
    run = PipelineRun.objects.select_related("order").get(pk=run_id)
    ensure_ready(run.order.source_assets.order_by("-uploaded_at").first())


def remove_unreferenced_original(public_id):
    """Best-effort cleanup after a successful replacement/deletion transaction."""
    from apps.orders.models import SourceAsset
    if not public_id or not public_id.startswith("recast/source/") or SourceAsset.objects.filter(cloudinary_public_id=public_id).exists():
        return
    try:
        cloudinary_media._configure()
        import cloudinary.uploader
        result = cloudinary.uploader.destroy(public_id, resource_type="video", invalidate=True)
        if result.get("result") not in {"ok", "not found"}:
            raise SourceHandoffError("Cleanup needs retry.")
    except Exception:
        import logging
        logging.getLogger(__name__).warning("Unreferenced original cleanup needs retry")
