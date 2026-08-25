from django import forms
from django.conf import settings
from django.core.validators import FileExtensionValidator
from .models import ContentOrder, SourceAsset

PLATFORMS = [("linkedin", "LinkedIn"), ("x", "X / Twitter"), ("instagram", "Instagram"), ("youtube", "YouTube"), ("newsletter", "Newsletter / article")]
class ContentOrderForm(forms.ModelForm):
    target_platforms = forms.MultipleChoiceField(
        choices=PLATFORMS,
        widget=forms.CheckboxSelectMultiple,
        label="Publishing destinations",
        help_text="Choose every channel this project should be prepared for.",
    )

    class Meta:
        model = ContentOrder
        fields = ["title", "content_brief", "importance_definition", "moments_to_avoid", "desired_clip_count", "min_clip_seconds", "max_clip_seconds", "brand_voice", "target_platforms", "broll_mode", "broll_intensity", "include_audio_cleanup"]
        labels = {
            "content_brief": "Audience and project brief",
            "importance_definition": "What makes a moment worth clipping?",
            "moments_to_avoid": "What should the AI avoid?",
            "desired_clip_count": "Number of clips",
            "min_clip_seconds": "Minimum length",
            "max_clip_seconds": "Maximum length",
            "brand_voice": "Voice and style notes",
            "broll_mode": "B-roll direction",
            "broll_intensity": "B-roll frequency",
            "include_audio_cleanup": "Professional audio cleanup",
        }
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "e.g. The founder's playbook: episode 12"}),
            "content_brief": forms.Textarea(attrs={"rows": 4, "placeholder": "Who is this for, what should they learn, and what outcome should the content drive?"}),
            "importance_definition": forms.Textarea(attrs={"rows": 4, "placeholder": "Example: Prioritize surprising opinions and actionable advice for first-time founders."}),
            "moments_to_avoid": forms.Textarea(attrs={"rows": 4, "placeholder": "Example: Skip introductions, sponsor reads, repetition, and off-topic discussion."}),
            "brand_voice": forms.Textarea(attrs={"rows": 4, "placeholder": "Example: Clear, confident and conversational. Avoid hype and jargon."}),
            "desired_clip_count": forms.NumberInput(attrs={"min": 1, "max": 10, "inputmode": "numeric"}),
            "min_clip_seconds": forms.NumberInput(attrs={"min": 10, "max": 120, "inputmode": "numeric"}),
            "max_clip_seconds": forms.NumberInput(attrs={"min": 10, "max": 120, "inputmode": "numeric"}),
            "broll_mode": forms.RadioSelect,
            "broll_intensity": forms.RadioSelect,
        }

class SourceAssetForm(forms.ModelForm):
    rights_confirmed = forms.BooleanField(
        required=False,
        label="I confirm that I own this content or have permission to download, clip, and republish it.",
    )
    class Meta:
        model = SourceAsset
        fields = ["file", "external_url", "rights_confirmed"]
    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("file") and not cleaned.get("external_url"):
            raise forms.ValidationError("Upload a video/audio file or provide a link.")
        if cleaned.get("external_url") and not cleaned.get("rights_confirmed"):
            self.add_error("rights_confirmed", "You must confirm your rights before importing a public URL.")
        return cleaned


class SourceRecoveryUploadForm(forms.Form):
    file = forms.FileField(
        label="Upload the original video or audio",
        validators=[
            FileExtensionValidator(
                ["mp4", "mov", "mkv", "webm", "ogv", "ogg", "mp3", "wav", "m4a"]
            )
        ],
        widget=forms.ClearableFileInput(
            attrs={"accept": "video/*,audio/*", "data-source-recovery-file": ""}
        ),
    )

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        if uploaded.size > settings.PUBLIC_MEDIA_MAX_BYTES:
            raise forms.ValidationError("This source exceeds the configured upload limit.")
        return uploaded
