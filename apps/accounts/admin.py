from django.contrib import admin
from .models import CustomerProfile, SocialHandle, YouTubeAccount
admin.site.register(CustomerProfile)
admin.site.register(SocialHandle)
admin.site.register(YouTubeAccount)
