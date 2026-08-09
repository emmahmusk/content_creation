from django.conf import settings
from django.db import models

class CustomerProfile(models.Model):
    class Audience(models.TextChoices):
        PODCASTER = "podcaster", "Podcaster"
        COACH = "coach", "Coach"
        CHURCH = "church", "Church"
        CONSULTANT = "consultant", "Consultant"
        YOUTUBE = "youtube", "YouTube creator"
        OTHER = "other", "Other"
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="customer_profile")
    organization = models.CharField(max_length=160, blank=True)
    audience_type = models.CharField(max_length=20, choices=Audience.choices, default=Audience.OTHER)
    website = models.URLField(blank=True)
    timezone = models.CharField(max_length=64, default="Africa/Lagos")
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return self.organization or self.user.get_username()


class SocialHandle(models.Model):
    class Platform(models.TextChoices):
        YOUTUBE = "youtube", "YouTube"
        INSTAGRAM = "instagram", "Instagram"
        TIKTOK = "tiktok", "TikTok"
        X = "x", "X / Twitter"
        LINKEDIN = "linkedin", "LinkedIn"
        FACEBOOK = "facebook", "Facebook"
        THREADS = "threads", "Threads"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="social_handles")
    platform = models.CharField(max_length=20, choices=Platform.choices)
    handle = models.CharField(max_length=160)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["platform"]
        constraints = [models.UniqueConstraint(fields=["user", "platform"], name="unique_user_social_platform")]

    def clean(self):
        from django.core.exceptions import ValidationError
        value = self.handle.strip()
        if not value:
            raise ValidationError({"handle": "Enter a social handle or profile URL."})
        self.handle = value

    def __str__(self):
        return f"{self.get_platform_display()}: {self.handle}"
