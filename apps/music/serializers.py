from rest_framework import serializers

from .models import AfroStudioProject, StudioAsset
from .services.creative import CreativeSafetyError, enforce_originality


class StudioAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudioAsset
        fields = ("id", "kind", "label", "file", "payload", "text_content", "created_at")
        read_only_fields = fields


class AfroStudioProjectSerializer(serializers.ModelSerializer):
    assets = StudioAssetSerializer(many=True, read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    stage_label = serializers.CharField(source="get_current_stage_display", read_only=True)

    class Meta:
        model = AfroStudioProject
        fields = (
            "id", "title", "reference_audio", "original_filename", "source_rights_confirmed",
            "analysis_only_confirmed", "status", "status_label", "current_stage", "stage_label", "progress",
            "audio_metadata", "intelligence", "creative_direction", "creative_plan", "lyrics", "error_message",
            "assets", "created_at", "updated_at", "analyzed_at", "generated_at",
        )
        read_only_fields = (
            "id", "original_filename", "status", "current_stage", "progress", "audio_metadata", "intelligence",
            "creative_direction", "creative_plan", "lyrics", "error_message", "assets", "created_at", "updated_at",
            "analyzed_at", "generated_at",
        )

    def validate(self, attrs):
        if not attrs.get("source_rights_confirmed") or not attrs.get("analysis_only_confirmed"):
            raise serializers.ValidationError("Both rights and analysis-only confirmations are required.")
        audio = attrs.get("reference_audio")
        if audio and audio.size > 150 * 1024 * 1024:
            raise serializers.ValidationError({"reference_audio": "Choose an audio file smaller than 150 MB."})
        return attrs


class CreativeDirectionSerializer(serializers.Serializer):
    story = serializers.CharField(max_length=1200)
    audience = serializers.CharField(max_length=200)
    desired_mood = serializers.CharField(max_length=120)
    genre = serializers.ChoiceField(choices=["AfroFusion", "Afrobeats", "AfroSoul", "Afro Pop", "Afro R&B", "Highlife", "Amapiano Fusion"])
    lyrical_theme = serializers.ChoiceField(choices=["love", "victory", "prayer", "money", "street", "success", "heartbreak", "family", "celebration", "hope"])
    energy = serializers.ChoiceField(choices=["low", "medium", "high", "festival", "club", "relaxed", "driving", "workout"])
    language = serializers.ChoiceField(choices=["english", "pidgin", "yoruba", "igbo", "hausa", "french", "spanish", "mixed"])
    voice_profile = serializers.ChoiceField(choices=["warm", "soulful", "deep", "modern", "traditional", "expressive"])
    originality_confirmed = serializers.BooleanField()

    def validate(self, attrs):
        if not attrs.get("originality_confirmed"):
            raise serializers.ValidationError({"originality_confirmed": "Original, non-imitative creation must be confirmed."})
        try:
            enforce_originality(attrs)
        except CreativeSafetyError as exc:
            raise serializers.ValidationError({"story": str(exc)}) from exc
        return attrs


class LyricsUpdateSerializer(serializers.Serializer):
    lyrics = serializers.CharField(trim_whitespace=True, allow_blank=False, max_length=50000)
