from django.db import transaction

from apps.processing.models import PipelineRun


ANALYSIS_INPUT_FIELDS = frozenset(
    {
        "content_brief",
        "importance_definition",
        "moments_to_avoid",
        "desired_clip_count",
        "min_clip_seconds",
        "max_clip_seconds",
        "brand_voice",
        "target_platforms",
    }
)

RENDER_INPUT_FIELDS = frozenset(
    {"broll_mode", "broll_intensity", "include_audio_cleanup"}
)


def has_generated_analysis(order):
    return (
        order.clips.exists()
        or order.transcript_segments.exists()
        or order.deliverables.exists()
        or order.pipeline_runs.exclude(status=PipelineRun.Status.QUEUED, progress=0).exists()
    )


def prepare_analysis_restart(order):
    """Clear derived outputs while retaining the source and immutable run history."""
    stored_files = []
    for clip in order.clips.all():
        for name in ("video", "audio", "subtitle", "thumbnail"):
            field = getattr(clip, name)
            if field and field.name:
                stored_files.append((field.storage, field.name))
    for deliverable in order.deliverables.all():
        if deliverable.file and deliverable.file.name:
            stored_files.append((deliverable.file.storage, deliverable.file.name))

    order.clips.all().delete()
    order.transcript_segments.all().delete()
    order.deliverables.all().delete()
    run = PipelineRun.objects.create(order=order)

    def remove_replaced_files():
        for storage, name in stored_files:
            try:
                storage.delete(name)
            except Exception:
                pass

    transaction.on_commit(remove_replaced_files)
    return run


def prepare_render_restart(order):
    """Discard rendered files while preserving approved ranges and AI analysis."""
    stored_files = []
    for clip in order.clips.all():
        for name in ("video", "audio", "subtitle", "thumbnail"):
            field = getattr(clip, name)
            if field and field.name:
                stored_files.append((field.storage, field.name))
                setattr(clip, name, "")
        if clip.status == clip.Status.RENDERED:
            clip.status = clip.Status.APPROVED
        clip.save(update_fields=["video", "audio", "subtitle", "thumbnail", "status"])
        if hasattr(clip, "broll_plan"):
            clip.broll_plan.delete()
    run = PipelineRun.objects.create(order=order)

    def remove_replaced_files():
        for storage, name in stored_files:
            try:
                storage.delete(name)
            except Exception:
                pass

    transaction.on_commit(remove_replaced_files)
    return run
