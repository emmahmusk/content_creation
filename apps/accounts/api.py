from rest_framework import permissions, viewsets

from .models import SocialHandle
from .serializers import SocialHandleSerializer


class SocialHandleViewSet(viewsets.ModelViewSet):
    serializer_class = SocialHandleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SocialHandle.objects.filter(user=self.request.user)
