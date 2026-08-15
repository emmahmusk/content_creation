import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import CreativeDirectionForm, StudioUploadForm
from .models import AfroStudioProject
from .services.creative import CreativeSafetyError, enforce_originality
from .tasks import dispatch_analysis, dispatch_generation


def _project(user, project_id):
    return get_object_or_404(AfroStudioProject.objects.prefetch_related("assets"), pk=project_id, owner=user)


@login_required
def studio_home(request):
    projects = AfroStudioProject.objects.filter(owner=request.user)[:12]
    form = StudioUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        project = form.save(commit=False)
        project.owner = request.user
        project.original_filename = request.FILES["reference_audio"].name
        project.save()
        dispatch_analysis(project.id)
        messages.success(request, "Reference uploaded. Music intelligence is running.")
        return redirect("music:detail", project_id=project.id)
    return render(request, "music/home.html", {"projects": projects, "form": form})


@login_required
def project_detail(request, project_id):
    project = _project(request.user, project_id)
    initial = project.creative_direction or None
    direction_form = CreativeDirectionForm(initial=initial)
    return render(request, "music/detail.html", {"project": project, "direction_form": direction_form})


@login_required
@require_POST
def set_direction(request, project_id):
    project = _project(request.user, project_id)
    if project.status not in {AfroStudioProject.Status.DIRECTION, AfroStudioProject.Status.REVIEW}:
        messages.error(request, "Finish the music analysis before setting creative direction.")
        return redirect("music:detail", project_id=project.id)
    form = CreativeDirectionForm(request.POST)
    if form.is_valid():
        try:
            enforce_originality(form.cleaned_data)
        except CreativeSafetyError as exc:
            form.add_error("story", str(exc))
        else:
            project.creative_direction = form.cleaned_data
            project.save(update_fields=["creative_direction", "updated_at"])
            dispatch_generation(project.id)
            messages.success(request, "Original song concept is being created.")
            return redirect("music:detail", project_id=project.id)
    return render(request, "music/detail.html", {"project": project, "direction_form": form}, status=400)


@login_required
@require_POST
def update_lyrics(request, project_id):
    project = _project(request.user, project_id)
    if project.status != AfroStudioProject.Status.REVIEW:
        raise Http404
    lyrics = request.POST.get("lyrics", "").strip()
    if not lyrics:
        messages.error(request, "Lyrics cannot be empty.")
    else:
        project.lyrics = lyrics
        project.save(update_fields=["lyrics", "updated_at"])
        asset = project.assets.filter(kind="lyrics").first()
        if asset:
            asset.text_content = lyrics
            asset.save(update_fields=["text_content"])
        messages.success(request, "Lyrics saved.")
    return redirect("music:detail", project_id=project.id)


@login_required
@require_POST
def retry_project(request, project_id):
    project = _project(request.user, project_id)
    if project.status == AfroStudioProject.Status.FAILED:
        if project.creative_direction and project.current_stage in {
            AfroStudioProject.Stage.CREATIVE_PLAN,
            AfroStudioProject.Stage.LYRICS,
            AfroStudioProject.Stage.REVIEW,
        }:
            dispatch_generation(project.id)
            messages.success(request, "Original song generation restarted.")
        else:
            dispatch_analysis(project.id)
            messages.success(request, "Analysis restarted.")
    return redirect("music:detail", project_id=project.id)


@login_required
def export_project(request, project_id, export_format):
    project = _project(request.user, project_id)
    if project.status != AfroStudioProject.Status.REVIEW:
        raise Http404
    safe_name = "".join(character if character.isalnum() else "-" for character in project.title.lower()).strip("-") or "afrofusion-project"
    if export_format == "lyrics":
        response = HttpResponse(project.lyrics, content_type="text/plain; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{safe_name}-lyrics.txt"'
        return response
    if export_format == "json":
        payload = {"title": project.title, "analysis": project.intelligence, "direction": project.creative_direction, "creative_plan": project.creative_plan, "lyrics": project.lyrics}
        response = HttpResponse(json.dumps(payload, indent=2), content_type="application/json")
        response["Content-Disposition"] = f'attachment; filename="{safe_name}-project.json"'
        return response
    raise Http404


@login_required
def progress(request, project_id):
    project = _project(request.user, project_id)
    return JsonResponse({"status": project.status, "stage": project.current_stage, "stage_label": project.get_current_stage_display(), "progress": project.progress, "error": project.error_message})
