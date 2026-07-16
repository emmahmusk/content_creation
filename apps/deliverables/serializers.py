from rest_framework import serializers
from .models import Deliverable
class DeliverableSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    class Meta:
        model = Deliverable
        fields = ["id", "order", "kind", "kind_label", "title", "content", "file", "status", "version", "created_by", "created_at", "updated_at"]
        read_only_fields = ["created_by", "created_at", "updated_at"]
