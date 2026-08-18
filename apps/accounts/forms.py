from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.forms import BaseFormSet, formset_factory
from .models import CustomerProfile, SocialHandle

MAX_REGISTRATION_SOCIAL_PROFILES = len(SocialHandle.Platform.choices)


class RegistrationSocialHandleForm(forms.Form):
    platform = forms.ChoiceField(
        choices=[("", "Choose a platform"), *SocialHandle.Platform.choices],
        label="Platform",
    )
    handle = forms.CharField(
        max_length=160,
        label="Handle or profile URL",
        widget=forms.TextInput(attrs={"placeholder": "@yourhandle"}),
    )

    def clean_handle(self):
        return self.cleaned_data["handle"].strip()


class BaseRegistrationSocialHandleFormSet(BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        seen = set()
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):
                continue
            platform = form.cleaned_data.get("platform")
            if not platform:
                continue
            if platform in seen:
                form.add_error("platform", "Choose each social platform only once.")
            seen.add(platform)


RegistrationSocialHandleFormSet = formset_factory(
    RegistrationSocialHandleForm,
    formset=BaseRegistrationSocialHandleFormSet,
    extra=1,
    can_delete=True,
    max_num=MAX_REGISTRATION_SOCIAL_PROFILES,
    validate_max=True,
)

class RegistrationForm(UserCreationForm):
    email = forms.EmailField()
    organization = forms.CharField(max_length=160, required=False)
    audience_type = forms.ChoiceField(choices=CustomerProfile.Audience.choices)
    class Meta:
        model = User
        fields = ("username", "email", "organization", "audience_type", "password1", "password2")
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ""
    def save(self, commit=True):
        user = super().save(commit)
        if commit:
            user.email = self.cleaned_data["email"]
            user.save(update_fields=["email"])
            profile = user.customer_profile
            profile.organization = self.cleaned_data["organization"]
            profile.audience_type = self.cleaned_data["audience_type"]
            profile.save()
        return user

class WorkspaceAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ""
