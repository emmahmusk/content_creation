from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import CustomerProfile

class RegistrationForm(UserCreationForm):
    email = forms.EmailField()
    organization = forms.CharField(max_length=160, required=False)
    audience_type = forms.ChoiceField(choices=CustomerProfile.Audience.choices)
    class Meta:
        model = User
        fields = ("username", "email", "organization", "audience_type", "password1", "password2")
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
