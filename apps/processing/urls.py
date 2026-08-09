from django.urls import path
from .views import intelligence_review

app_name="processing"
urlpatterns=[path("clips/<int:clip_id>/",intelligence_review,name="intelligence-review")]
