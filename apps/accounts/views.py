import secrets
import requests

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.core.exceptions import ImproperlyConfigured
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from apps.credits.models import CreditLedgerEntry
from .forms import MAX_REGISTRATION_SOCIAL_PROFILES, RegistrationForm, RegistrationSocialHandleFormSet
from .models import SocialHandle, YouTubeAccount
from .services.youtube import YOUTUBE_SCOPES, decrypt_token, encrypt_token, google_oauth_client_config

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
            CreditLedgerEntry.objects.create(
                user=user,
                entry_type=CreditLedgerEntry.Type.WELCOME,
                amount=4,
                description="Welcome gift · 4 free clip credits",
            )
        login(request, user)
        request.session["welcome_credits_celebration"] = True
        return redirect("orders:dashboard")
    return render(request, "account/register.html", {
        "form": form,
        "social_formset": social_formset,
        "social_platform_limit": MAX_REGISTRATION_SOCIAL_PROFILES,
    })

@login_required
def profile(request):
    return render(request, "account/profile.html", {"platforms": SocialHandle.Platform.choices, "social_handles": request.user.social_handles.all(), "youtube_account": YouTubeAccount.objects.filter(user=request.user).first()})


@login_required
def youtube_connect(request):
    try:
        config = google_oauth_client_config()
        # A Fernet key is required before we let the user authorize storage of tokens.
        encrypt_token("configuration-check")
        flow = Flow.from_client_config(config, scopes=YOUTUBE_SCOPES, redirect_uri=settings.YOUTUBE_REDIRECT_URI)
        state = secrets.token_urlsafe(32)
        request.session["youtube_oauth_state"] = state
        next_url = request.GET.get("next", "")
        request.session["youtube_oauth_next"] = next_url if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()) else reverse("profile")
        authorization_url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent", state=state)
        return redirect(authorization_url)
    except ImproperlyConfigured as exc:
        messages.error(request, str(exc))
        return redirect("profile")


@login_required
def youtube_callback(request):
    next_url = request.session.pop("youtube_oauth_next", reverse("profile"))
    expected_state = request.session.pop("youtube_oauth_state", "")
    if request.GET.get("error"):
        messages.error(request, "YouTube connection was cancelled or denied.")
        return redirect(next_url)
    if not expected_state or not secrets.compare_digest(expected_state, request.GET.get("state", "")):
        messages.error(request, "YouTube connection could not be verified. Please try connecting again.")
        return redirect(next_url)
    try:
        flow = Flow.from_client_config(google_oauth_client_config(), scopes=YOUTUBE_SCOPES, state=expected_state, redirect_uri=settings.YOUTUBE_REDIRECT_URI)
        flow.fetch_token(authorization_response=request.build_absolute_uri())
        credentials = flow.credentials
        youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
        channels = youtube.channels().list(part="snippet", mine=True).execute().get("items", [])
        if not channels:
            raise ValueError("The selected Google account does not have a YouTube channel.")
        channel = channels[0]
        snippet = channel.get("snippet", {})
        old_account = YouTubeAccount.objects.filter(user=request.user).first()
        refresh_token = credentials.refresh_token or (old_account and decrypt_token(old_account.refresh_token_encrypted))
        if not refresh_token:
            raise ValueError("Google did not return a refresh token. Disconnect this app from your Google Account and connect again.")
        YouTubeAccount.objects.update_or_create(user=request.user, defaults={
            "channel_id": channel["id"],
            "channel_title": snippet.get("title", ""),
            "access_token_encrypted": encrypt_token(credentials.token or ""),
            "refresh_token_encrypted": encrypt_token(refresh_token),
            "token_expiry": credentials.expiry,
            "scopes": list(credentials.scopes or YOUTUBE_SCOPES),
        })
        handle, _ = SocialHandle.objects.get_or_create(user=request.user, platform=SocialHandle.Platform.YOUTUBE, defaults={"handle": snippet.get("title") or channel["id"]})
        if handle.handle != (snippet.get("title") or channel["id"]):
            handle.handle = snippet.get("title") or channel["id"]
            handle.save(update_fields=["handle", "updated_at"])
        messages.success(request, f"YouTube channel {snippet.get('title', '')} connected.")
    except Exception as exc:
        messages.error(request, f"Could not connect YouTube: {exc}")
    return redirect(next_url)


@login_required
def youtube_disconnect(request):
    if request.method != "POST":
        return redirect("profile")
    account = YouTubeAccount.objects.filter(user=request.user).first()
    if account:
        try:
            requests.post("https://oauth2.googleapis.com/revoke", data={"token": decrypt_token(account.refresh_token_encrypted)}, timeout=10)
        except requests.RequestException:
            pass
        account.delete()
    messages.success(request, "YouTube was disconnected. Your saved YouTube destination remains available for drafts.")
    return redirect("profile")
