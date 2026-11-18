from django import forms
from django.conf import settings
from django.core.validators import FileExtensionValidator
from .models import ContentOrder, SourceAsset, WalkthroughWaitlist
from apps.processing.services.public_media import is_youtube_url
from apps.processing.services.youtube import canonical_url
from apps.processing.services.public_media import PublicMediaError
from apps.processing.services import source_handoff

PLATFORMS = [("linkedin", "LinkedIn"), ("x", "X / Twitter"), ("instagram", "Instagram"), ("youtube", "YouTube"), ("newsletter", "Newsletter / article")]
class ContentOrderForm(forms.ModelForm):
    target_platforms = forms.MultipleChoiceField(
        choices=PLATFORMS,
        widget=forms.CheckboxSelectMultiple,
        label="Publishing destinations",
        required=False,
        help_text="Choose every channel this project should be prepared for.",
    )

    class Meta:
        model = ContentOrder
        fields = ["title", "content_brief", "importance_definition", "moments_to_avoid", "desired_clip_count", "min_clip_seconds", "max_clip_seconds", "brand_voice", "target_platforms", "broll_mode", "broll_intensity", "include_captions", "include_audio_cleanup"]
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
            "include_captions": "Burn captions into the video",
        }
        help_texts = {
            "include_captions": "Show timed subtitles on the exported video. Captions use up to 4 words at a time.",
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
    cloudinary_upload_token = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        self.upload_metadata = None
        super().__init__(*args, **kwargs)

    rights_confirmed = forms.BooleanField(
        required=False,
        label="I confirm that I own this content or have permission to download, clip, and republish it.",
    )
    class Meta:
        model = SourceAsset
        fields = ["file", "external_url", "rights_confirmed"]
        widgets = {
            "external_url": forms.URLInput(attrs={
                "placeholder": "YouTube, Google Drive, Dropbox, or direct media link",
                "autocomplete": "url",
                "inputmode": "url",
            }),
        }

    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        if uploaded and uploaded.size > settings.PUBLIC_MEDIA_MAX_BYTES:
            limit_mb = settings.PUBLIC_MEDIA_MAX_BYTES // (1024 * 1024)
            raise forms.ValidationError(
                f"This source exceeds the {limit_mb} MB upload limit. Choose a smaller file or contact us for help."
            )
        return uploaded

    def clean(self):
        cleaned = super().clean()
        token = cleaned.get("cloudinary_upload_token")
        if token:
            if not self.user or cleaned.get("file") or cleaned.get("external_url"):
                raise forms.ValidationError("Choose one recording or one source link.")
            if not cleaned.get("rights_confirmed"):
                self.add_error("rights_confirmed", "Confirm your rights before uploading the recording.")
            else:
                try:
                    self.upload_metadata = source_handoff.verify_upload(token, self.user)
                    for key, value in self.upload_metadata.items():
                        setattr(self.instance, key, value)
                except source_handoff.SourceHandoffError as exc:
                    self.add_error("cloudinary_upload_token", str(exc))
        if not cleaned.get("file") and not cleaned.get("external_url") and not token:
            raise forms.ValidationError("Upload a video/audio file or provide a link.")
        if cleaned.get("external_url") and not cleaned.get("rights_confirmed"):
            self.add_error("rights_confirmed", "You must confirm your rights before importing a public URL.")
        if not settings.YOUTUBE_IMPORTS_ENABLED and cleaned.get("external_url") and not cleaned.get("file") and is_youtube_url(cleaned["external_url"]):
            self.add_error(
                "external_url",
                "YouTube links cannot be imported reliably. Upload the original video file instead. "
                "If it is your channel, download your upload from YouTube Studio first.",
            )
        elif cleaned.get("external_url") and not cleaned.get("file") and is_youtube_url(cleaned["external_url"]):
            try:
                canonical_url(cleaned["external_url"])
            except (PublicMediaError, ValueError):
                self.add_error("external_url", "Provide a valid single YouTube video URL.")
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


class WalkthroughWaitlistForm(forms.ModelForm):
    class Meta:
        model = WalkthroughWaitlist
        fields = ["email", "availability"]
        labels = {
            "email": "Email address",
            "availability": "Best time for you (optional)",
        }
        widgets = {
            "email": forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@example.com"}),
            "availability": forms.TextInput(attrs={"placeholder": "Weekday afternoons (WAT)"}),
        }

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()
