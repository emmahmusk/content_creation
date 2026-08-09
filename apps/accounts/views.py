from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from .forms import RegistrationForm
from .models import SocialHandle

def register(request):
    if request.user.is_authenticated:
        return redirect("orders:dashboard")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("orders:dashboard")
    return render(request, "account/register.html", {"form": form})

@login_required
def profile(request):
    return render(request, "account/profile.html", {"platforms": SocialHandle.Platform.choices, "social_handles": request.user.social_handles.all()})
