from django.conf import settings
from django.db import models

class Deliverable(models.Model):
    class Kind(models.TextChoices):
        CLIP_PLAN = "clip_plan", "10 clip suggestions"
        CAPTIONS_HOOKS = "captions_hooks", "Captions and hooks"
        SOCIAL_POSTS = "social_posts", "Social posts"
        YOUTUBE_PACKAGE = "youtube_package", "YouTube package"
        NEWSLETTER = "newsletter", "Newsletter / article"
        CLEAN_AUDIO = "clean_audio", "Cleaned audio"
        OTHER = "other", "Other"
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        READY = "ready", "Ready"
        REVISION = "revision", "Revision requested"
        APPROVED = "approved", "Approved"
    order = models.ForeignKey("orders.ContentOrder", on_delete=models.CASCADE, related_name="deliverables")
    kind = models.CharField(max_length=30, choices=Kind.choices)
    title = models.CharField(max_length=200)
    content = models.TextField(blank=True, help_text="Markdown or plain-text content.")
    file = models.FileField(upload_to="deliverables/%Y/%m/", blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    version = models.PositiveSmallIntegerField(default=1)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_deliverables")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["kind", "-version"]
        constraints = [models.UniqueConstraint(fields=["order", "kind", "version"], name="unique_deliverable_version")]
    def __str__(self): return self.title
