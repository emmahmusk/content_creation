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
    class Meta:
        model = SourceAsset
        fields = ["file", "external_url"]
    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("file") and not cleaned.get("external_url"):
            raise forms.ValidationError("Upload a video/audio file or provide a link.")
        return cleaned
