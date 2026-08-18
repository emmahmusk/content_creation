from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from .forms import MAX_REGISTRATION_SOCIAL_PROFILES, RegistrationForm, RegistrationSocialHandleFormSet
from .models import SocialHandle

def register(request):
    if request.user.is_authenticated:
        return redirect("orders:dashboard")
    form = RegistrationForm(request.POST or None)
    social_formset = RegistrationSocialHandleFormSet(request.POST or None, prefix="social")
    if request.method == "POST" and form.is_valid() and social_formset.is_valid():
        with transaction.atomic():
            user = form.save()
            handles = [
                SocialHandle(user=user, platform=item["platform"], handle=item["handle"])
                for item in social_formset.cleaned_data
                if item and not item.get("DELETE") and item.get("platform")
            ]
            SocialHandle.objects.bulk_create(handles)
        login(request, user)
        return redirect("orders:dashboard")
    return render(request, "account/register.html", {
        "form": form,
        "social_formset": social_formset,
        "social_platform_limit": MAX_REGISTRATION_SOCIAL_PROFILES,
    })

@login_required
def profile(request):
    return render(request, "account/profile.html", {"platforms": SocialHandle.Platform.choices, "social_handles": request.user.social_handles.all()})
