import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models


class AfroStudioProject(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ANALYZING = "analyzing", "Analyzing reference"
        DIRECTION = "direction", "Creative direction"
        GENERATING = "generating", "Creating original concept"
        REVIEW = "review", "Studio review"
        FAILED = "failed", "Needs attention"

    class Stage(models.TextChoices):
        UPLOAD = "upload", "Upload"
        AUDIO_INTELLIGENCE = "audio_intelligence", "Audio intelligence"
        MUSIC_REPORT = "music_report", "Music report"
        CREATIVE_PLAN = "creative_plan", "Creative plan"
        LYRICS = "lyrics", "Original lyrics"
        REVIEW = "review", "Studio review"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="afrofusion_projects")
    title = models.CharField(max_length=160)
    reference_audio = models.FileField(
        upload_to="music/references/%Y/%m/",
        validators=[FileExtensionValidator(["mp3", "wav", "flac", "aac", "m4a"])],
    )
    original_filename = models.CharField(max_length=255, blank=True)
    source_rights_confirmed = models.BooleanField(default=False)
    analysis_only_confirmed = models.BooleanField(default=False)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT, db_index=True)
    current_stage = models.CharField(max_length=32, choices=Stage.choices, default=Stage.UPLOAD)
    progress = models.PositiveSmallIntegerField(default=0)
    audio_metadata = models.JSONField(default=dict, blank=True)
    intelligence = models.JSONField(default=dict, blank=True)
    creative_direction = models.JSONField(default=dict, blank=True)
    creative_plan = models.JSONField(default=dict, blank=True)
    lyrics = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    analyzed_at = models.DateTimeField(blank=True, null=True)
    generated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["owner", "status"])]

    def clean(self):
        errors = {}
        if not self.source_rights_confirmed:
            errors["source_rights_confirmed"] = "Confirm that you own the audio or have permission to analyze it."
        if not self.analysis_only_confirmed:
            errors["analysis_only_confirmed"] = "Confirm that the upload is for high-level musical analysis only."
        if self.progress > 100:
            errors["progress"] = "Progress cannot exceed 100."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.title


class StudioAsset(models.Model):
    class Kind(models.TextChoices):
        LYRICS = "lyrics", "Lyrics"
        PROJECT_JSON = "project_json", "Project data"
        MELODY_JSON = "melody_json", "Melody plan"
        MIDI = "midi", "MIDI"
        AUDIO = "audio", "Audio preview"
        STEM = "stem", "Stem"

    project = models.ForeignKey(AfroStudioProject, on_delete=models.CASCADE, related_name="assets")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    label = models.CharField(max_length=120)
    file = models.FileField(upload_to="music/exports/%Y/%m/", blank=True)
    payload = models.JSONField(default=dict, blank=True)
    text_content = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind", "created_at"]

    def __str__(self):
        return f"{self.project.title}: {self.label}"
