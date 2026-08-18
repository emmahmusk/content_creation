from rest_framework import serializers
from .models import ContentOrder, OrderEvent, SourceAsset

class SourceAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = SourceAsset
        fields = ["id", "order", "file", "external_url", "original_filename", "duration_seconds", "cloudinary_public_id", "cloudinary_url", "rights_confirmed", "uploaded_at"]
        read_only_fields = ["original_filename", "cloudinary_public_id", "cloudinary_url", "uploaded_at"]
    def validate(self, attrs):
        if not attrs.get("file") and not attrs.get("external_url") and not getattr(self.instance, "file", None):
            raise serializers.ValidationError("A file or external_url is required.")
        if attrs.get("external_url") and not attrs.get("rights_confirmed"):
            raise serializers.ValidationError({"rights_confirmed": "Confirm that you own this content or have permission to repurpose it."})
        return attrs

class OrderEventSerializer(serializers.ModelSerializer):
    actor = serializers.StringRelatedField()
    class Meta:
        model = OrderEvent
        fields = ["id", "event_type", "message", "actor", "created_at"]

class ContentOrderSerializer(serializers.ModelSerializer):
    customer = serializers.StringRelatedField(read_only=True)
    source_assets = SourceAssetSerializer(many=True, read_only=True)
    events = OrderEventSerializer(many=True, read_only=True)
    deliverables_count = serializers.IntegerField(source="deliverables.count", read_only=True)
    class Meta:
        model = ContentOrder
        fields = ["id", "customer", "title", "content_brief", "importance_definition", "moments_to_avoid", "desired_clip_count", "min_clip_seconds", "max_clip_seconds", "brand_voice", "target_platforms", "broll_mode", "broll_intensity", "include_audio_cleanup", "status", "due_at", "delivered_at", "created_at", "updated_at", "source_assets", "events", "deliverables_count"]
        read_only_fields = ["status", "due_at", "delivered_at", "created_at", "updated_at"]

class StaffContentOrderSerializer(ContentOrderSerializer):
    class Meta(ContentOrderSerializer.Meta):
        read_only_fields = ["due_at", "delivered_at", "created_at", "updated_at"]
