from django import forms
from .models import ContentOrder, SourceAsset

PLATFORMS = [("linkedin", "LinkedIn"), ("x", "X / Twitter"), ("instagram", "Instagram"), ("youtube", "YouTube"), ("newsletter", "Newsletter / article")]
class ContentOrderForm(forms.ModelForm):
    target_platforms = forms.MultipleChoiceField(choices=PLATFORMS, widget=forms.CheckboxSelectMultiple)
    class Meta:
        model = ContentOrder
        fields = ["title", "content_brief", "brand_voice", "target_platforms", "include_audio_cleanup"]

class SourceAssetForm(forms.ModelForm):
    class Meta:
        model = SourceAsset
        fields = ["file", "external_url"]
    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("file") and not cleaned.get("external_url"):
            raise forms.ValidationError("Upload a video/audio file or provide a link.")
        return cleaned
