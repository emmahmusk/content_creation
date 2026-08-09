from django import forms
from .models import ContentOrder, SourceAsset

PLATFORMS = [("linkedin", "LinkedIn"), ("x", "X / Twitter"), ("instagram", "Instagram"), ("youtube", "YouTube"), ("newsletter", "Newsletter / article")]
class ContentOrderForm(forms.ModelForm):
    target_platforms = forms.MultipleChoiceField(choices=PLATFORMS, widget=forms.CheckboxSelectMultiple)
    class Meta:
        model = ContentOrder
        fields = ["title", "content_brief", "importance_definition", "moments_to_avoid", "desired_clip_count", "min_clip_seconds", "max_clip_seconds", "brand_voice", "target_platforms", "include_audio_cleanup"]
        widgets = {
            "importance_definition": forms.Textarea(attrs={"placeholder": "Example: Prioritize surprising opinions and actionable advice for first-time founders."}),
            "moments_to_avoid": forms.Textarea(attrs={"placeholder": "Example: Skip introductions, sponsor reads, repetition, and off-topic discussion."}),
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
