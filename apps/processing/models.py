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
    youtube_auth_url = models.URLField(blank=True)
    youtube_auth_code = models.CharField(max_length=32, blank=True)
    youtube_auth_confirmed = models.BooleanField(default=False)
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
    preview_url = models.URLField(blank=True, max_length=1000)
    editing_instructions = models.JSONField(default=dict, blank=True)
    video = models.FileField(upload_to="clips/%Y/%m/", blank=True)
    audio = models.FileField(upload_to="clips/%Y/%m/", blank=True)
    subtitle = models.FileField(upload_to="clips/%Y/%m/", blank=True)
    thumbnail = models.ImageField(upload_to="thumbnails/%Y/%m/", blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=["rank"]
        constraints=[models.UniqueConstraint(fields=["order","rank"], name="unique_clip_rank")]
    @property
    def duration_seconds(self): return round((self.end_ms-self.start_ms)/1000, 1)
    @staticmethod
    def _timecode(milliseconds):
        seconds=max(0,milliseconds//1000); minutes,seconds=divmod(seconds,60); hours,minutes=divmod(minutes,60)
        return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"
    @property
    def start_timecode(self): return self._timecode(self.start_ms)
    @property
    def end_timecode(self): return self._timecode(self.end_ms)


class BrollPlan(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PLANNING = "planning", "Planning"
        READY = "ready", "Ready"
        PARTIAL = "partial", "Partially generated"
        SKIPPED = "skipped", "Skipped"
        FAILED = "failed", "Failed"

    clip = models.OneToOneField(Clip, on_delete=models.CASCADE, related_name="broll_plan")
    mode = models.CharField(max_length=20)
    intensity = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    scenes = models.JSONField(default=list, blank=True)
    provider = models.CharField(max_length=80, default="NVIDIA NIM")
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["clip__rank"]


class ContentIntelligence(models.Model):
    class Status(models.TextChoices):
        QUEUED="queued","Queued"; RUNNING="running","Running"; READY="ready","Ready"; FAILED="failed","Failed"
    clip=models.OneToOneField(Clip,on_delete=models.CASCADE,related_name="intelligence")
    status=models.CharField(max_length=20,choices=Status.choices,default=Status.QUEUED,db_index=True)
    content_dna=models.JSONField(default=dict,blank=True)
    selection_reasoning=models.JSONField(default=dict,blank=True)
    platform_strategy=models.JSONField(default=dict,blank=True)
    business_impact=models.JSONField(default=dict,blank=True)
    audience_matching=models.JSONField(default=dict,blank=True)
    semantic_graph=models.JSONField(default=dict,blank=True)
    editor_recommendations=models.JSONField(default=list,blank=True)
    confidence=models.PositiveSmallIntegerField(default=0)
    model=models.CharField(max_length=100,blank=True)
    error=models.TextField(blank=True)
    version=models.PositiveIntegerField(default=1)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)


class RepurposeAsset(models.Model):
    class Kind(models.TextChoices):
        LINKEDIN="linkedin_post","LinkedIn post"; X_THREAD="x_thread","X thread"; INSTAGRAM="instagram_caption","Instagram caption"; YOUTUBE="youtube_description","YouTube description"; NEWSLETTER="newsletter","Newsletter"; BLOG="blog_outline","Blog outline"; SEO="seo_metadata","SEO metadata"; EMAIL="email","Email"; CAROUSEL="carousel_outline","Carousel outline"; PODCAST="podcast_summary","Podcast summary"
    clip=models.ForeignKey(Clip,on_delete=models.CASCADE,related_name="repurpose_assets")
    kind=models.CharField(max_length=30,choices=Kind.choices)
    title=models.CharField(max_length=200)
    content=models.TextField(blank=True)
    metadata=models.JSONField(default=dict,blank=True)
    version=models.PositiveIntegerField(default=1)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        ordering=["kind"]
        constraints=[models.UniqueConstraint(fields=["clip","kind"],name="unique_clip_repurpose_kind")]


class PublicationJob(models.Model):
    class Action(models.TextChoices):
        DRAFT="draft","Save draft"; QUEUE="queue","Queue"; SCHEDULE="schedule","Schedule"; PUBLISH="publish","Publish now"; REPUBLISH="republish","Republish"
    class Status(models.TextChoices):
        DRAFT="draft","Draft"; QUEUED="queued","Queued"; SCHEDULED="scheduled","Scheduled"; PUBLISHING="publishing","Publishing"; PUBLISHED="published","Published"; FAILED="failed","Failed"
    clip=models.ForeignKey(Clip,on_delete=models.CASCADE,related_name="publication_jobs")
    user=models.ForeignKey("auth.User",on_delete=models.CASCADE,related_name="publication_jobs")
    social_handle=models.ForeignKey("accounts.SocialHandle",on_delete=models.PROTECT,related_name="publication_jobs")
    action=models.CharField(max_length=20,choices=Action.choices)
    status=models.CharField(max_length=20,choices=Status.choices,default=Status.DRAFT,db_index=True)
    scheduled_for=models.DateTimeField(null=True,blank=True)
    platform_payload=models.JSONField(default=dict)
    external_id=models.CharField(max_length=255,blank=True)
    error=models.TextField(blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)


class LearningSignal(models.Model):
    clip=models.ForeignKey(Clip,on_delete=models.CASCADE,related_name="learning_signals")
    publication=models.ForeignKey(PublicationJob,on_delete=models.SET_NULL,null=True,blank=True,related_name="learning_signals")
    event_type=models.CharField(max_length=40)
    value=models.FloatField(default=0)
    metadata=models.JSONField(default=dict,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
