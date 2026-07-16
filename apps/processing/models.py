import uuid
from django.db import models

class PipelineRun(models.Model):
    class Status(models.TextChoices):
        QUEUED="queued","Queued"; RUNNING="running","Running"; REVIEW="review","Awaiting review"; COMPLETED="completed","Completed"; FAILED="failed","Failed"; CANCELLED="cancelled","Cancelled"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey("orders.ContentOrder", on_delete=models.CASCADE, related_name="pipeline_runs")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED, db_index=True)
    current_stage = models.CharField(max_length=40, blank=True)
    progress = models.PositiveSmallIntegerField(default=0)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta: ordering=["-created_at"]

class StageRun(models.Model):
    class Status(models.TextChoices):
        PENDING="pending","Pending"; RUNNING="running","Running"; COMPLETED="completed","Completed"; FAILED="failed","Failed"; SKIPPED="skipped","Skipped"
    pipeline = models.ForeignKey(PipelineRun, on_delete=models.CASCADE, related_name="stages")
    name = models.CharField(max_length=40)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering=["id"]
        constraints=[models.UniqueConstraint(fields=["pipeline","name"], name="unique_pipeline_stage")]

class TranscriptSegment(models.Model):
    order = models.ForeignKey("orders.ContentOrder", on_delete=models.CASCADE, related_name="transcript_segments")
    start_ms = models.PositiveIntegerField()
    end_ms = models.PositiveIntegerField()
    text = models.TextField()
    words = models.JSONField(default=list, blank=True)
    speaker = models.CharField(max_length=50, blank=True)
    class Meta: ordering=["start_ms"]

class Clip(models.Model):
    class Status(models.TextChoices):
        PLANNED="planned","Planned"; RENDERED="rendered","Rendered"; APPROVED="approved","Approved"; REJECTED="rejected","Rejected"
    order = models.ForeignKey("orders.ContentOrder", on_delete=models.CASCADE, related_name="clips")
    rank = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=160)
    hook = models.CharField(max_length=240)
    caption = models.TextField()
    start_ms = models.PositiveIntegerField()
    end_ms = models.PositiveIntegerField()
    score = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    rationale = models.TextField(blank=True)
    video = models.FileField(upload_to="clips/%Y/%m/", blank=True)
    subtitle = models.FileField(upload_to="clips/%Y/%m/", blank=True)
    thumbnail = models.ImageField(upload_to="thumbnails/%Y/%m/", blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=["rank"]
        constraints=[models.UniqueConstraint(fields=["order","rank"], name="unique_clip_rank")]
    @property
    def duration_seconds(self): return round((self.end_ms-self.start_ms)/1000, 1)
