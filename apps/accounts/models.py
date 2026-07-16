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
