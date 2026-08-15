from django.db import transaction
from django.utils import timezone

from ..models import AfroStudioProject, StudioAsset
from .audio import analyze_audio
from .creative import build_report, generate_original_song


def _progress(project, stage, value, status=None):
    project.current_stage = stage
    project.progress = value
    if status:
        project.status = status
    project.error_message = ""
    project.save(update_fields=["current_stage", "progress", "status", "error_message", "updated_at"])


def analyze_project(project_id):
    project = AfroStudioProject.objects.get(pk=project_id)
    try:
        _progress(project, AfroStudioProject.Stage.AUDIO_INTELLIGENCE, 12, AfroStudioProject.Status.ANALYZING)
        metadata, features = analyze_audio(project.reference_audio.path)
        project.audio_metadata = metadata
        project.intelligence = {"features": features}
        project.save(update_fields=["audio_metadata", "intelligence", "updated_at"])
        _progress(project, AfroStudioProject.Stage.MUSIC_REPORT, 68)
        report = build_report(features)
        project.intelligence = {"features": features, "report": report}
        project.analyzed_at = timezone.now()
        project.status = AfroStudioProject.Status.DIRECTION
        project.progress = 100
        project.save(update_fields=["intelligence", "analyzed_at", "status", "progress", "updated_at"])
    except Exception as exc:
        project.status = AfroStudioProject.Status.FAILED
        project.error_message = str(exc)[:1000]
        project.save(update_fields=["status", "error_message", "updated_at"])
        raise


def generate_project(project_id):
    project = AfroStudioProject.objects.get(pk=project_id)
    try:
        _progress(project, AfroStudioProject.Stage.CREATIVE_PLAN, 18, AfroStudioProject.Status.GENERATING)
        result = generate_original_song(project.intelligence.get("features", {}), project.creative_direction)
        _progress(project, AfroStudioProject.Stage.LYRICS, 76)
        with transaction.atomic():
            project.creative_plan = {key: value for key, value in result.items() if key != "lyrics"}
            project.lyrics = result["lyrics"]
            project.generated_at = timezone.now()
            project.current_stage = AfroStudioProject.Stage.REVIEW
            project.status = AfroStudioProject.Status.REVIEW
            project.progress = 100
            project.save()
            StudioAsset.objects.update_or_create(project=project, kind=StudioAsset.Kind.LYRICS, defaults={"label": "Original lyrics", "text_content": project.lyrics})
            StudioAsset.objects.update_or_create(project=project, kind=StudioAsset.Kind.PROJECT_JSON, defaults={"label": "Studio project", "payload": {"analysis": project.intelligence, "direction": project.creative_direction, "plan": project.creative_plan}})
            StudioAsset.objects.update_or_create(project=project, kind=StudioAsset.Kind.MELODY_JSON, defaults={"label": "Original melody plan", "payload": project.creative_plan.get("melody_plan", {})})
    except Exception as exc:
        project.status = AfroStudioProject.Status.FAILED
        project.error_message = str(exc)[:1000]
        project.save(update_fields=["status", "error_message", "updated_at"])
        raise
