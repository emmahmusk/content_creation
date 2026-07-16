from rest_framework import permissions, viewsets
from .models import ContentOrder, SourceAsset
from .serializers import ContentOrderSerializer, SourceAssetSerializer, StaffContentOrderSerializer

class ContentOrderViewSet(viewsets.ModelViewSet):
    filterset_fields = ["status", "include_audio_cleanup"]
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
