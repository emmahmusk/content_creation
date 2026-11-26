from django.urls import path
from .views import profile, register, youtube_callback, youtube_connect, youtube_disconnect
urlpatterns = [path("register/", register, name="register"), path("profile/", profile, name="profile"), path("youtube/connect/", youtube_connect, name="youtube-connect"), path("youtube/callback/", youtube_callback, name="youtube-callback"), path("youtube/disconnect/", youtube_disconnect, name="youtube-disconnect")]
