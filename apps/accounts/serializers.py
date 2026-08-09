from rest_framework import serializers

from .models import SocialHandle


class SocialHandleSerializer(serializers.ModelSerializer):
    platform_label = serializers.CharField(source="get_platform_display", read_only=True)

    class Meta:
        model = SocialHandle
        fields = ["id", "platform", "platform_label", "handle", "created_at", "updated_at"]

    def validate_handle(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Enter a social handle or profile URL.")
        return value

    def validate(self, attrs):
        user = self.context["request"].user
        platform = attrs.get("platform", getattr(self.instance, "platform", None))
        duplicate = SocialHandle.objects.filter(user=user, platform=platform)
        if self.instance:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError({"platform": "You already have a handle for this platform. Update it instead."})
        return attrs

    def create(self, validated_data):
        return SocialHandle.objects.create(user=self.context["request"].user, **validated_data)
