from django.urls import path

from . import views

app_name = "music"
urlpatterns = [
    path("", views.studio_home, name="home"),
    path("<uuid:project_id>/", views.project_detail, name="detail"),
    path("<uuid:project_id>/direction/", views.set_direction, name="direction"),
    path("<uuid:project_id>/lyrics/", views.update_lyrics, name="lyrics"),
    path("<uuid:project_id>/retry/", views.retry_project, name="retry"),
    path("<uuid:project_id>/progress/", views.progress, name="progress"),
    path("<uuid:project_id>/export/<str:export_format>/", views.export_project, name="export"),
]
