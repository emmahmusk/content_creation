from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.core.views import home, health
from apps.orders.api import ContentOrderViewSet, SourceAssetViewSet
from apps.deliverables.api import DeliverableViewSet
from apps.processing.api import ClipViewSet, ContentIntelligenceViewSet, LearningSignalViewSet, PipelineRunViewSet, PublicationJobViewSet, RepurposeAssetViewSet, TranscriptViewSet
from apps.accounts.api import SocialHandleViewSet

router = DefaultRouter()
router.register("orders", ContentOrderViewSet, basename="order")
router.register("assets", SourceAssetViewSet, basename="asset")
router.register("deliverables", DeliverableViewSet, basename="deliverable")
router.register("pipeline-runs", PipelineRunViewSet, basename="pipeline-run")
router.register("clips", ClipViewSet, basename="clip")
router.register("transcript", TranscriptViewSet, basename="transcript")
router.register("social-handles", SocialHandleViewSet, basename="social-handle")
router.register("content-intelligence",ContentIntelligenceViewSet,basename="content-intelligence")
router.register("repurpose-assets",RepurposeAssetViewSet,basename="repurpose-asset")
router.register("publication-jobs",PublicationJobViewSet,basename="publication-job")
router.register("learning-signals",LearningSignalViewSet,basename="learning-signal")

urlpatterns = [
    path("admin/", admin.site.urls), path("", home, name="home"), path("health/", health, name="health"),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="account/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/", include("apps.accounts.urls")), path("orders/", include("apps.orders.urls")), path("intelligence/",include("apps.processing.urls")),
    path("api/v1/", include((router.urls, "api"), namespace="v1")), path("api-auth/", include("rest_framework.urls")),
]
if DEBUG := settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
