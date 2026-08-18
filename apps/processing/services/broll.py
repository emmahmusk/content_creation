from pathlib import Path

import requests
from django.conf import settings

from apps.orders.models import ContentOrder
from apps.processing.models import BrollPlan
from . import media, nvidia


SCENE_LIMITS = {"minimal": 1, "moderate": 2, "aggressive": 3}
MAX_STOCK_DOWNLOAD_BYTES = 150 * 1024 * 1024


def _clip_context(clip):
    segments = clip.order.transcript_segments.filter(
        start_ms__lt=clip.end_ms, end_ms__gt=clip.start_ms
    )
    transcript = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
    return (
        f"Title: {clip.title}\nHook: {clip.hook}\nCaption: {clip.caption}\n"
        f"Why selected: {clip.rationale}\nTranscript: {transcript}"
    )


def _clean_scenes(raw_scenes, clip_duration_ms, intensity):
    limit = SCENE_LIMITS.get(intensity, 2)
    scenes = []
    previous_end = 2000
    for raw in (raw_scenes or [])[:limit]:
        start = max(2000, int(raw.get("start_ms") or previous_end))
        duration = max(1800, min(int(raw.get("duration_ms") or 3000), 4000))
        if start + duration > clip_duration_ms:
            start = max(2000, clip_duration_ms - duration)
        if start < previous_end:
            start = previous_end
        if start + duration > clip_duration_ms or clip_duration_ms < 4000:
            continue
        scenes.append(
            {
                "start_ms": start,
                "duration_ms": duration,
                "visual_prompt": str(raw.get("visual_prompt") or "Cinematic supporting visual, no text")[:1200],
                "stock_query": str(raw.get("stock_query") or clip.title)[:160],
                "reason": str(raw.get("reason") or "Supports the spoken idea visually.")[:500],
            }
        )
        previous_end = start + duration + 500
    return scenes


def _download(url, destination):
    with requests.get(url, stream=True, timeout=(15, 120)) as response:
        response.raise_for_status()
        declared_size = int(response.headers.get("Content-Length") or 0)
        if declared_size > MAX_STOCK_DOWNLOAD_BYTES:
            raise RuntimeError("The selected stock video is larger than the safe import limit.")
        downloaded = 0
        with open(destination, "wb") as output:
            for chunk in response.iter_content(1024 * 512):
                downloaded += len(chunk)
                if downloaded > MAX_STOCK_DOWNLOAD_BYTES:
                    raise RuntimeError("The selected stock video exceeded the safe import limit.")
                output.write(chunk)
    return destination


def _stock_video(query, destination):
    if not settings.PEXELS_API_KEY:
        raise RuntimeError("PEXELS_API_KEY is not configured.")
    response = requests.get(
        "https://api.pexels.com/v1/videos/search",
        headers={"Authorization": settings.PEXELS_API_KEY},
        params={"query": query, "orientation": "portrait", "size": "medium", "per_page": 6},
        timeout=(15, 60),
    )
    response.raise_for_status()
    videos = response.json().get("videos") or []
    if not videos:
        raise RuntimeError("No suitable licensed stock video was found.")
    video = videos[0]
    files = [item for item in video.get("video_files", []) if item.get("file_type") == "video/mp4"]
    files.sort(key=lambda item: (item.get("height", 0) < item.get("width", 0), abs((item.get("height", 1) / max(item.get("width", 1), 1)) - (16 / 9)), -item.get("height", 0)))
    if not files:
        raise RuntimeError("The selected stock result has no MP4 rendition.")
    _download(files[0]["link"], destination)
    return {
        "provider": "Pexels",
        "source_url": video.get("url", ""),
        "creator": (video.get("user") or {}).get("name", "Pexels contributor"),
        "creator_url": (video.get("user") or {}).get("url", ""),
    }


def _make_scene_asset(scene, mode, work, clip_rank, scene_index):
    stem = work / f"clip-{clip_rank:02}-broll-{scene_index:02}"
    credit = None
    source_type = "generated_video"
    raw = stem.with_suffix(".mp4")
    if mode in {ContentOrder.BrollMode.AI_SELECTED, ContentOrder.BrollMode.HYBRID} and (
        mode == ContentOrder.BrollMode.AI_SELECTED or scene_index % 2
    ):
        try:
            credit = _stock_video(scene["stock_query"], raw)
            source_type = "licensed_stock"
        except Exception:
            raw = stem.with_suffix(".png")
            nvidia.generate_broll_image(scene["visual_prompt"], raw)
            source_type = "generated_image"
    else:
        try:
            nvidia.generate_broll_video(
                scene["visual_prompt"], raw, seconds=max(2, round(scene["duration_ms"] / 1000))
            )
        except Exception:
            raw = stem.with_suffix(".png")
            nvidia.generate_broll_image(scene["visual_prompt"], raw)
            source_type = "generated_image"
    normalized = stem.with_name(f"{stem.name}-vertical.mp4")
    media.normalize_broll_asset(raw, normalized, scene["duration_ms"])
    return normalized, source_type, credit


def prepare_order_broll(order, clips, work, run=None):
    """Plan and build B-roll only after clips have been explicitly approved."""
    if order.broll_mode == ContentOrder.BrollMode.NONE:
        return {}, {"enabled": False, "clips": 0, "scenes": 0, "warnings": []}
    assets = {}
    warnings = []
    generated_scenes = 0
    for clip in clips:
        if run:
            from .run_control import assert_pipeline_active
            assert_pipeline_active(run)
        plan, _ = BrollPlan.objects.update_or_create(
            clip=clip,
            defaults={
                "mode": order.broll_mode,
                "intensity": order.broll_intensity,
                "provider": (
                    "Pexels + NVIDIA NIM"
                    if order.broll_mode == ContentOrder.BrollMode.HYBRID
                    else "Pexels"
                    if order.broll_mode == ContentOrder.BrollMode.AI_SELECTED
                    else "NVIDIA NIM"
                ),
                "status": BrollPlan.Status.PLANNING,
                "scenes": [],
                "error": "",
            },
        )
        try:
            raw = nvidia.plan_broll(_clip_context(clip), order.broll_intensity, int(clip.duration_seconds * 1000))
            scenes = _clean_scenes(raw.get("scenes"), int(clip.duration_seconds * 1000), order.broll_intensity)
            clip_assets = []
            saved_scenes = []
            for scene_index, scene in enumerate(scenes, start=1):
                try:
                    path, source_type, credit = _make_scene_asset(scene, order.broll_mode, work, clip.rank, scene_index)
                    clip_assets.append({**scene, "path": path})
                    saved_scenes.append({**scene, "source_type": source_type, "credit": credit or {}})
                    generated_scenes += 1
                except Exception as exc:
                    saved_scenes.append({**scene, "source_type": "unavailable", "warning": str(exc)[:500]})
                    warnings.append(f"Clip {clip.rank}, scene {scene_index}: {exc}")
            assets[clip.pk] = clip_assets
            plan.scenes = saved_scenes
            if clip_assets and len(clip_assets) == len(scenes):
                plan.status = BrollPlan.Status.READY
            elif clip_assets:
                plan.status = BrollPlan.Status.PARTIAL
            else:
                plan.status = BrollPlan.Status.FAILED
            plan.error = "\n".join(warnings[-3:])
            plan.save(update_fields=["scenes", "status", "error", "updated_at"])
        except Exception as exc:
            plan.status = BrollPlan.Status.FAILED
            plan.error = str(exc)[:1000]
            plan.save(update_fields=["status", "error", "updated_at"])
            warnings.append(f"Clip {clip.rank}: {exc}")
            assets[clip.pk] = []
    return assets, {
        "enabled": True,
        "mode": order.broll_mode,
        "intensity": order.broll_intensity,
        "clips": len(clips),
        "scenes": generated_scenes,
        "warnings": warnings,
    }
