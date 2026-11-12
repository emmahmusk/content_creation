import uuid
from datetime import timedelta
from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone

class ContentOrder(models.Model):
    class BrollMode(models.TextChoices):
        NONE = "none", "No B-roll"
        AI_SELECTED = "ai_selected", "AI-selected B-roll"
        AI_GENERATED = "ai_generated", "AI-generated B-roll"
        HYBRID = "hybrid", "Stock + AI-generated B-roll"

    class BrollIntensity(models.TextChoices):
        MINIMAL = "minimal", "Minimal"
        MODERATE = "moderate", "Moderate"
        AGGRESSIVE = "aggressive", "Aggressive"

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        REVIEWING = "reviewing", "Reviewing source"
        IN_PROGRESS = "in_progress", "In production"
        QUALITY_CHECK = "quality_check", "Quality check"
        DELIVERED = "delivered", "Delivered"
        REVISION = "revision", "Revision requested"
        CANCELLED = "cancelled", "Cancelled"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="content_orders")
    title = models.CharField(max_length=200)
    content_brief = models.TextField(help_text="Audience, goals, tone, and any important context.")
    brand_voice = models.TextField(blank=True)
    importance_definition = models.TextField(blank=True, help_text="Describe exactly what makes a moment valuable for this recording.")
    moments_to_avoid = models.TextField(blank=True, help_text="Topics or sections the clipper should exclude.")
    desired_clip_count = models.PositiveSmallIntegerField(default=5)
    min_clip_seconds = models.PositiveSmallIntegerField(default=20)
    max_clip_seconds = models.PositiveSmallIntegerField(default=60)
    target_platforms = models.JSONField(default=list, blank=True)
    include_audio_cleanup = models.BooleanField(default=False)
    broll_mode = models.CharField(
        max_length=20,
        choices=BrollMode.choices,
        default=BrollMode.NONE,
    )
    broll_intensity = models.CharField(
        max_length=20,
        choices=BrollIntensity.choices,
        default=BrollIntensity.MODERATE,
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED, db_index=True)
    due_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["customer", "status"])]
    def save(self, *args, **kwargs):
        if not self.due_at:
            self.due_at = timezone.now() + timedelta(hours=24)
        if self.status == self.Status.DELIVERED and not self.delivered_at:
            self.delivered_at = timezone.now()
        super().save(*args, **kwargs)

    def clean(self):
        from django.core.exceptions import ValidationError
        if not 1 <= self.desired_clip_count <= 10:
            raise ValidationError({"desired_clip_count": "Choose between 1 and 10 clips."})
        if self.min_clip_seconds < 10 or self.max_clip_seconds > 120 or self.min_clip_seconds > self.max_clip_seconds:
            raise ValidationError("Clip duration must be between 10 and 120 seconds, with minimum not exceeding maximum.")
    def __str__(self):
        return self.title

class SourceAsset(models.Model):
    order = models.ForeignKey(ContentOrder, on_delete=models.CASCADE, related_name="source_assets")
    file = models.FileField(upload_to="source/%Y/%m/", blank=True, validators=[FileExtensionValidator(["mp4", "mov", "mkv", "webm", "ogv", "ogg", "mp3", "wav", "m4a"])])
    external_url = models.URLField(blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    duration_seconds = models.PositiveIntegerField(blank=True, null=True)
    cloudinary_public_id = models.CharField(max_length=255, blank=True)
    cloudinary_url = models.URLField(blank=True)
    rights_confirmed = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.file and not self.external_url:
            raise ValidationError("Upload a file or provide an external video URL.")
        if self.external_url and not self.rights_confirmed:
            raise ValidationError({"rights_confirmed": "Confirm that you own this content or have permission to repurpose it."})
    def __str__(self):
        return self.original_filename or self.external_url or str(self.pk)

class OrderEvent(models.Model):
    order = models.ForeignKey(ContentOrder, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    event_type = models.CharField(max_length=50)
    message = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at"]


class WalkthroughWaitlist(models.Model):
    email = models.EmailField(unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="walkthrough_waitlist_signups",
    )
    availability = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "walkthrough waitlist signup"
        verbose_name_plural = "walkthrough waitlist signups"

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email
