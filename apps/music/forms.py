from django import forms

from .models import AfroStudioProject


class StudioUploadForm(forms.ModelForm):
    class Meta:
        model = AfroStudioProject
        fields = ("title", "reference_audio", "source_rights_confirmed", "analysis_only_confirmed")
        widgets = {
            "reference_audio": forms.FileInput(attrs={"accept": ".mp3,.wav,.flac,.aac,.m4a,audio/*"}),
        }
        labels = {
            "reference_audio": "Reference song",
            "source_rights_confirmed": "I own this recording or have permission to analyze it.",
            "analysis_only_confirmed": "Use this upload only for high-level musical analysis—not copying.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ""

    def clean_reference_audio(self):
        audio = self.cleaned_data["reference_audio"]
        if audio.size > 150 * 1024 * 1024:
            raise forms.ValidationError("Choose an audio file smaller than 150 MB.")
        return audio


class CreativeDirectionForm(forms.Form):
    GENRES = [(value, value) for value in ["AfroFusion", "Afrobeats", "AfroSoul", "Afro Pop", "Afro R&B", "Highlife", "Amapiano Fusion"]]
    THEMES = [(value.lower(), value) for value in ["Love", "Victory", "Prayer", "Money", "Street", "Success", "Heartbreak", "Family", "Celebration", "Hope"]]
    ENERGIES = [(value.lower(), value) for value in ["Low", "Medium", "High", "Festival", "Club", "Relaxed", "Driving", "Workout"]]
    LANGUAGES = [(value.lower(), value) for value in ["English", "Pidgin", "Yoruba", "Igbo", "Hausa", "French", "Spanish", "Mixed"]]

    story = forms.CharField(label="What story should this song tell?", widget=forms.Textarea(attrs={"rows": 3, "placeholder": "A specific feeling, moment, or transformation…"}))
    audience = forms.CharField(max_length=200, widget=forms.TextInput(attrs={"placeholder": "Who should feel seen by this song?"}))
    desired_mood = forms.CharField(max_length=120, widget=forms.TextInput(attrs={"placeholder": "Warm, triumphant, reflective…"}))
    genre = forms.ChoiceField(choices=GENRES)
    lyrical_theme = forms.ChoiceField(choices=THEMES)
    energy = forms.ChoiceField(choices=ENERGIES)
    language = forms.ChoiceField(choices=LANGUAGES)
    voice_profile = forms.ChoiceField(choices=[("warm", "Warm"), ("soulful", "Soulful"), ("deep", "Deep"), ("modern", "Modern"), ("traditional", "Traditional"), ("expressive", "Expressive")])
    originality_confirmed = forms.BooleanField(label="Create an original composition without artist imitation, copied lyrics, samples, or melodies.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ""
