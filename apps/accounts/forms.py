from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from .models import CustomerProfile, SocialHandle

class RegistrationForm(UserCreationForm):
    email = forms.EmailField()
    organization = forms.CharField(max_length=160, required=False)
    audience_type = forms.ChoiceField(choices=CustomerProfile.Audience.choices)
    social_platform = forms.ChoiceField(choices=[("", "Choose a platform (optional)"), *SocialHandle.Platform.choices], required=False)
    social_handle = forms.CharField(max_length=160, required=False, help_text="Your @handle, channel name, or profile URL.")
    class Meta:
        model = User
        fields = ("username", "email", "organization", "audience_type", "social_platform", "social_handle", "password1", "password2")
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ""
    def clean(self):
        cleaned = super().clean()
        if bool(cleaned.get("social_platform")) != bool(cleaned.get("social_handle")):
            raise forms.ValidationError("Choose a social platform and enter its handle, or leave both blank.")
        return cleaned
    def save(self, commit=True):
        user = super().save(commit)
        if commit:
            user.email = self.cleaned_data["email"]
            user.save(update_fields=["email"])
            profile = user.customer_profile
            profile.organization = self.cleaned_data["organization"]
            profile.audience_type = self.cleaned_data["audience_type"]
            profile.save()
            if self.cleaned_data.get("social_platform"):
                SocialHandle.objects.create(user=user,platform=self.cleaned_data["social_platform"],handle=self.cleaned_data["social_handle"].strip())
        return user

class WorkspaceAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ""
