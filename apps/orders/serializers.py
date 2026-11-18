from rest_framework import serializers
from django.conf import settings
from django.db import transaction
from .models import ContentOrder, OrderEvent, SourceAsset
from apps.processing.services.public_media import is_youtube_url
from apps.processing.services import youtube_sources, youtube, source_handoff
from apps.processing.services.public_media import PublicMediaError

class SourceAssetSerializer(serializers.ModelSerializer):
    cloudinary_upload_token = serializers.CharField(write_only=True, required=False)
    class Meta:
        model = SourceAsset
        fields = ["id", "order", "file", "external_url", "original_filename", "duration_seconds", "cloudinary_public_id", "cloudinary_url", "rights_confirmed", "uploaded_at", "cloudinary_upload_token"]
        read_only_fields = ["original_filename", "cloudinary_public_id", "cloudinary_url", "uploaded_at"]
    def validate(self, attrs):
        if self.instance and "order" in attrs and attrs["order"].pk != self.instance.order_id:
            raise serializers.ValidationError("A recording cannot be moved to another project.")
        self.upload_metadata = None
        token = attrs.pop("cloudinary_upload_token", None)
        if token:
            if attrs.get("file") or attrs.get("external_url") or not attrs.get("rights_confirmed"):
                raise serializers.ValidationError("Choose one recording and confirm your content rights.")
            try:
                self.upload_metadata = source_handoff.verify_upload(token, self.context["request"].user)
                attrs.update(self.upload_metadata)
            except source_handoff.SourceHandoffError as exc:
                raise serializers.ValidationError({"cloudinary_upload_token": str(exc)}) from None
        if not attrs.get("file") and not attrs.get("external_url") and not attrs.get("cloudinary_public_id") and not getattr(self.instance, "file", None) and not getattr(self.instance, "cloudinary_public_id", None) and not getattr(self.instance, "external_url", None):
            raise serializers.ValidationError("A file or external_url is required.")
        if attrs.get("external_url") and not attrs.get("rights_confirmed"):
            raise serializers.ValidationError({"rights_confirmed": "Confirm that you own this content or have permission to repurpose it."})
        if not settings.YOUTUBE_IMPORTS_ENABLED and attrs.get("external_url") and not attrs.get("file") and not getattr(self.instance, "file", None) and is_youtube_url(attrs["external_url"]):
            raise serializers.ValidationError({"external_url": "Upload the original video file instead of a YouTube link."})
        if attrs.get("external_url") and is_youtube_url(attrs["external_url"]) and settings.YOUTUBE_IMPORTS_ENABLED:
            try:
                youtube.canonical_url(attrs["external_url"])
            except (PublicMediaError, ValueError):
                raise serializers.ValidationError({"external_url": "Provide a valid single YouTube video URL."}) from None
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        try:
            if self.upload_metadata:
                source_handoff.claim_upload(self.upload_metadata, self.context["request"].user)
            elif validated_data.get("file"):
                uploaded = validated_data["file"]
                metadata = source_handoff.upload_file(uploaded, validated_data["order"].customer_id)
                if metadata:
                    validated_data.update(metadata)
            return super().create(validated_data)
        except source_handoff.SourceHandoffError as exc:
            raise serializers.ValidationError({"file": str(exc)}) from None

    @transaction.atomic
    def update(self, instance, validated_data):
        old_public_id = instance.cloudinary_public_id
        old_file = (instance.file.storage, instance.file.name) if instance.file else None
        replacing = "file" in validated_data or ("external_url" in validated_data and validated_data["external_url"] != instance.external_url)
        if replacing and instance.order.pipeline_runs.filter(status="running").exists():
            raise serializers.ValidationError("Stop active processing before replacing this recording.")
        try:
            if self.upload_metadata:
                source_handoff.claim_upload(self.upload_metadata, self.context["request"].user)
            elif validated_data.get("file"):
                uploaded = validated_data["file"]
                metadata = source_handoff.upload_file(uploaded, instance.order.customer_id)
                if metadata:
                    validated_data.update(metadata)
                else:
                    validated_data.update(external_url="", cloudinary_public_id="", cloudinary_url="", duration_seconds=None, original_filename=uploaded.name)
            elif "external_url" in validated_data and validated_data["external_url"] != instance.external_url:
                validated_data.update(file="", cloudinary_public_id="", cloudinary_url="", original_filename="", duration_seconds=None)
        except source_handoff.SourceHandoffError as exc:
            raise serializers.ValidationError({"file": str(exc)}) from None
        if replacing and instance.youtube_imported_at:
            if not youtube_sources.discard(instance):
                raise serializers.ValidationError("Stop active processing and retry source cleanup before replacing this recording.")
        result = super().update(instance, validated_data)
        if replacing and old_public_id and old_public_id != result.cloudinary_public_id:
            transaction.on_commit(lambda: source_handoff.remove_unreferenced_original(old_public_id))
        if replacing and old_file and old_file[1] != result.file.name:
            storage, name = old_file
            def remove_old_file():
                try:
                    storage.delete(name)
                except Exception:
                    pass
            transaction.on_commit(remove_old_file)
        return result

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
        fields = ["id", "customer", "title", "content_brief", "importance_definition", "moments_to_avoid", "desired_clip_count", "min_clip_seconds", "max_clip_seconds", "brand_voice", "target_platforms", "broll_mode", "broll_intensity", "include_captions", "include_audio_cleanup", "status", "due_at", "delivered_at", "created_at", "updated_at", "source_assets", "events", "deliverables_count"]
        read_only_fields = ["status", "due_at", "delivered_at", "created_at", "updated_at"]

class StaffContentOrderSerializer(ContentOrderSerializer):
    class Meta(ContentOrderSerializer.Meta):
        read_only_fields = ["due_at", "delivered_at", "created_at", "updated_at"]
