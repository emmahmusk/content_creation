from rest_framework import permissions, viewsets
from .models import Deliverable
from .serializers import DeliverableSerializer

class DeliverableViewSet(viewsets.ModelViewSet):
    serializer_class = DeliverableSerializer
    filterset_fields = ["order", "kind", "status"]
    search_fields = ["title", "content"]
    def get_queryset(self):
        qs = Deliverable.objects.select_related("order", "created_by")
        return qs if self.request.user.is_staff else qs.filter(order__customer=self.request.user)
    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "destroy"]:
            return [permissions.IsAdminUser()]
        return [permissions.IsAuthenticated()]
    def perform_create(self, serializer): serializer.save(created_by=self.request.user)
