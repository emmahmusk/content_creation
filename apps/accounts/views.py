from django.contrib.auth import login
from django.shortcuts import redirect, render
from .forms import RegistrationForm

def register(request):
    if request.user.is_authenticated:
        return redirect("orders:dashboard")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("orders:dashboard")
    return render(request, "account/register.html", {"form": form})
