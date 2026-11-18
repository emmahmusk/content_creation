from rest_framework import permissions, viewsets
from django.db import transaction
from .models import ContentOrder, SourceAsset
from .serializers import ContentOrderSerializer, SourceAssetSerializer, StaffContentOrderSerializer

class ContentOrderViewSet(viewsets.ModelViewSet):
    filterset_fields = ["status", "include_captions", "include_audio_cleanup", "broll_mode", "broll_intensity"]
    search_fields = ["title", "content_brief"]
    ordering_fields = ["created_at", "due_at", "updated_at"]
    def get_queryset(self):
        qs = ContentOrder.objects.select_related("customer").prefetch_related("source_assets", "events", "deliverables")
        return qs if self.request.user.is_staff else qs.filter(customer=self.request.user)
    def get_serializer_class(self):
        return StaffContentOrderSerializer if self.request.user.is_staff else ContentOrderSerializer
    def perform_create(self, serializer):
        serializer.save(customer=self.request.user)

class SourceAssetViewSet(viewsets.ModelViewSet):
    serializer_class = SourceAssetSerializer
    def get_queryset(self):
        qs = SourceAsset.objects.select_related("order", "order__customer")
        return qs if self.request.user.is_staff else qs.filter(order__customer=self.request.user)
    def perform_create(self, serializer):
        order = serializer.validated_data["order"]
        if not self.request.user.is_staff and order.customer_id != self.request.user.id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You cannot add an asset to this order.")
        asset = serializer.save()
        if asset.file and not asset.original_filename:
            asset.original_filename = asset.file.name; asset.save(update_fields=["original_filename"])

    def perform_destroy(self, instance):
        from rest_framework.exceptions import ValidationError
        from apps.processing.services.youtube_sources import discard
        if instance.order.pipeline_runs.filter(status="running").exists() or not discard(instance):
            raise ValidationError("Stop active processing and retry source cleanup before deleting this recording.")
        old_public_id = instance.cloudinary_public_id
        instance.delete()
        from apps.processing.services.source_handoff import remove_unreferenced_original
        transaction.on_commit(lambda: remove_unreferenced_original(old_public_id))
