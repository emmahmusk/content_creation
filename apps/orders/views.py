from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .forms import ContentOrderForm, SourceAssetForm, SourceRecoveryUploadForm, WalkthroughWaitlistForm
from .models import ContentOrder, OrderEvent, WalkthroughWaitlist
from .services import (
    ANALYSIS_INPUT_FIELDS,
    RENDER_INPUT_FIELDS,
    has_generated_analysis,
    prepare_analysis_restart,
    prepare_render_restart,
)
from apps.processing.models import Clip, PipelineRun
from apps.processing.tasks import dispatch_render
from apps.processing.services.cloudinary_media import configured as cloudinary_configured
from apps.processing.services.public_media import is_youtube_authentication_error, is_youtube_url
from apps.processing.services.run_control import cancel_pipeline_run
from apps.credits.services import available_balance

@login_required
def dashboard(request):
    waitlist_form = WalkthroughWaitlistForm(
        request.POST or None,
        initial={"email": request.user.email},
    )
    if request.method == "POST":
        if waitlist_form.is_valid():
            email = waitlist_form.cleaned_data["email"]
            signup, created = WalkthroughWaitlist.objects.get_or_create(
                email=email,
                defaults={
                    "user": request.user,
                    "availability": waitlist_form.cleaned_data["availability"],
                },
            )
            if not created and signup.user_id is None:
                signup.user = request.user
                signup.save(update_fields=["user"])
            messages.success(
                request,
                "You’re on the walkthrough waitlist. We’ll email you when a session opens."
                if created
                else "That email is already on the walkthrough waitlist.",
            )
            return redirect("orders:dashboard")

    orders = list(
        request.user.content_orders.prefetch_related(
            "deliverables", "clips", "pipeline_runs"
        ).annotate(
            clip_total=Count("clips", distinct=True),
            high_potential_total=Count(
                "clips", filter=Q(clips__score__gte=8), distinct=True
            ),
            approved_total=Count(
                "clips", filter=Q(clips__status="approved"), distinct=True
            ),
        ).order_by("created_at", "pk")
    )
    # Keep the project label tied to creation order, independently of how the
    # dashboard is presented. The newest project remains at the top, but it no
    # longer gets mislabeled as Project 01.
    for project_number, order in enumerate(orders, start=1):
        order.project_number = project_number
    orders.reverse()
    active_statuses = {
        ContentOrder.Status.SUBMITTED,
        ContentOrder.Status.REVIEWING,
        ContentOrder.Status.IN_PROGRESS,
        ContentOrder.Status.QUALITY_CHECK,
        ContentOrder.Status.REVISION,
    }
    active_projects = sum(order.status in active_statuses for order in orders)
    completed_projects = sum(
        order.status == ContentOrder.Status.DELIVERED for order in orders
    )
    high_potential_moments = sum(order.high_potential_total for order in orders)
    total_moments = sum(order.clip_total for order in orders)

    priority_order = None
    priority_kind = "new"
    for order in orders:
        pipeline = order.pipeline_runs.first()
        if pipeline and pipeline.status == PipelineRun.Status.REVIEW:
            priority_order, priority_kind = order, "review"
            break
    if priority_order is None:
        for order in orders:
            pipeline = order.pipeline_runs.first()
            if pipeline and pipeline.status in {
                PipelineRun.Status.QUEUED,
                PipelineRun.Status.RUNNING,
            }:
                priority_order, priority_kind = order, "processing"
                break

    recent_events = list(
        OrderEvent.objects.filter(order__customer=request.user)
        .select_related("order")
        .order_by("-created_at")[:4]
    )
    waitlist_joined = WalkthroughWaitlist.objects.filter(
        Q(user=request.user)
        | Q(email__iexact=request.user.email)
    ).exists()
    credit_balance = available_balance(request.user)
    return render(
        request,
        "orders/dashboard.html",
        {
            "orders": orders,
            "active_projects": active_projects,
            "completed_projects": completed_projects,
            "high_potential_moments": high_potential_moments,
            "total_moments": total_moments,
            "priority_order": priority_order,
            "priority_kind": priority_kind,
            "recent_events": recent_events,
            "walkthrough_waitlist_form": waitlist_form,
            "walkthrough_waitlist_joined": waitlist_joined,
            "credit_balance": credit_balance,
            "show_welcome_credits_celebration": request.session.pop(
                "welcome_credits_celebration", False
            ),
        },
    )

@login_required
@transaction.atomic
def create_order(request):
    form, asset_form = ContentOrderForm(request.POST or None), SourceAssetForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid() and asset_form.is_valid():
        order = form.save(commit=False); order.customer = request.user; order.save()
        asset = asset_form.save(commit=False); asset.order = order
        if asset.file: asset.original_filename = asset.file.name
        asset.full_clean(); asset.save()
        OrderEvent.objects.create(order=order, actor=request.user, event_type="submitted", message="Content submitted for production.")
        PipelineRun.objects.create(order=order)
        messages.success(request, "Your content is in. The 24-hour clock has started.")
        return redirect("orders:detail", pk=order.pk)
    return render(request, "orders/create.html", {"form": form, "asset_form": asset_form})

@login_required
def order_detail(request, pk):
    order = get_object_or_404(ContentOrder.objects.prefetch_related("source_assets", "deliverables", "events", "clips__broll_plan", "pipeline_runs__stages"), pk=pk, customer=request.user)
    pipeline = order.pipeline_runs.first()
    if pipeline is None: pipeline = PipelineRun.objects.create(order=order)
    clips=list(order.clips.all())
    rendered=sum(bool(clip.video_url) for clip in clips)
    missing_rendered=sum(clip.status == Clip.Status.RENDERED and not clip.video_url for clip in clips)
    approved=sum(clip.status == "approved" for clip in clips)
    source_asset = order.source_assets.order_by("-uploaded_at").first()
    source_recovery_required = bool(
        source_asset
        and source_asset.external_url
        and is_youtube_url(source_asset.external_url)
        and pipeline.status == PipelineRun.Status.FAILED
        and is_youtube_authentication_error(pipeline.error)
    )
    return render(request, "orders/detail.html", {
        "order": order,
        "pipeline": pipeline,
        "clip_count": len(clips),
        "rendered_count": rendered,
        "missing_rendered_count": missing_rendered,
        "can_restore_exports": bool(
            missing_rendered
            and source_asset
            and source_asset.cloudinary_public_id
            and cloudinary_configured()
            and order.transcript_segments.exists()
        ),
        "approved_count": approved,
        "exports_ready": rendered > 0 and approved == 0,
        "source_asset": source_asset,
        "source_recovery_required": source_recovery_required,
        "source_recovery_form": SourceRecoveryUploadForm(),
    })


@login_required
def restore_missing_exports(request, pk):
    if request.method != "POST":
        return redirect("orders:detail", pk=pk)
    order = get_object_or_404(
        ContentOrder.objects.prefetch_related("source_assets", "pipeline_runs"),
        pk=pk,
        customer=request.user,
    )
    pipeline = order.pipeline_runs.first()
    asset = order.source_assets.order_by("-uploaded_at").first()
    if not pipeline or not asset or not asset.cloudinary_public_id or not cloudinary_configured():
        messages.error(request, "This project has no available Cloudinary source copy to restore from.")
        return redirect("orders:detail", pk=order.pk)
    if pipeline.status == PipelineRun.Status.RUNNING:
        messages.info(request, "This project already has a production run in progress.")
        return redirect("orders:detail", pk=order.pk)
    missing = [clip for clip in order.clips.filter(status=Clip.Status.RENDERED) if not clip.video_url]
    if not missing:
        messages.info(request, "All rendered clips are already available.")
        return redirect("orders:detail", pk=order.pk)
    if not order.transcript_segments.exists():
        messages.error(request, "The transcript needed to rebuild these clips is unavailable.")
        return redirect("orders:detail", pk=order.pk)

    with transaction.atomic():
        run = PipelineRun.objects.select_for_update().get(pk=pipeline.pk)
        if run.status == PipelineRun.Status.RUNNING:
            messages.info(request, "This project already has a production run in progress.")
            return redirect("orders:detail", pk=order.pk)
        run.storage_recovery = True
        run.recovery_clip_ids = [clip.pk for clip in missing]
        run.status = PipelineRun.Status.RUNNING
        run.current_stage = "render"
        run.progress = 70
        run.error = ""
        run.finished_at = None
        run.save(update_fields=["storage_recovery", "recovery_clip_ids", "status", "current_stage", "progress", "error", "finished_at", "updated_at"])
        Clip.objects.filter(pk__in=run.recovery_clip_ids).update(status=Clip.Status.APPROVED)
        order.status = ContentOrder.Status.IN_PROGRESS
        order.save(update_fields=["status", "updated_at"])
    try:
        dispatch_render(run.id)
    except Exception as exc:
        Clip.objects.filter(pk__in=run.recovery_clip_ids).update(status=Clip.Status.RENDERED)
        run.storage_recovery = False
        run.recovery_clip_ids = []
        run.status = PipelineRun.Status.FAILED
        run.error = f"Could not start export recovery: {exc}"
        run.finished_at = timezone.now()
        run.save(update_fields=["storage_recovery", "recovery_clip_ids", "status", "error", "finished_at", "updated_at"])
        order.status = ContentOrder.Status.QUALITY_CHECK
        order.save(update_fields=["status", "updated_at"])
        messages.error(request, "We could not start the recovery. Please try again in a moment.")
        return redirect("orders:detail", pk=order.pk)
    messages.success(request, "Restoring your missing clips from the saved source. This will not use additional credits.")
    return redirect("orders:detail", pk=order.pk)


@login_required
@transaction.atomic
def replace_blocked_source(request, pk):
    if request.method != "POST":
        return redirect("orders:detail", pk=pk)
    order = get_object_or_404(
        ContentOrder.objects.select_for_update().prefetch_related("source_assets", "pipeline_runs"),
        pk=pk,
        customer=request.user,
    )
    pipeline = order.pipeline_runs.first()
    if pipeline and pipeline.status == PipelineRun.Status.RUNNING:
        messages.error(request, "Wait for the active analysis to finish or stop it before replacing the source.")
        return redirect("orders:detail", pk=order.pk)

    form = SourceRecoveryUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Choose a supported video or audio file within the upload limit.")
        return redirect("orders:detail", pk=order.pk)

    asset = order.source_assets.first() or order.source_assets.create()
    old_file = (asset.file.storage, asset.file.name) if asset.file and asset.file.name else None
    uploaded = form.cleaned_data["file"]
    asset.file = uploaded
    asset.external_url = ""
    asset.original_filename = uploaded.name
    asset.duration_seconds = None
    asset.cloudinary_public_id = ""
    asset.cloudinary_url = ""
    asset.rights_confirmed = True
    asset.full_clean()
    asset.save()

    prepare_analysis_restart(order)
    order.status = ContentOrder.Status.SUBMITTED
    order.save(update_fields=["status", "updated_at"])
    OrderEvent.objects.create(
        order=order,
        actor=request.user,
        event_type="source_replaced",
        message="Blocked public source replaced with an uploaded recording.",
    )

    if old_file:
        storage, name = old_file

        def remove_old_source():
            try:
                storage.delete(name)
            except Exception:
                pass

        transaction.on_commit(remove_old_source)

    messages.success(request, "Source replaced. Your project is ready to analyze again.")
    return redirect("orders:detail", pk=order.pk)


@login_required
def edit_order(request, pk):
    order = get_object_or_404(
        ContentOrder.objects.prefetch_related("source_assets", "pipeline_runs"),
        pk=pk,
        customer=request.user,
    )
    pipeline = order.pipeline_runs.first()
    analysis_active = bool(pipeline and pipeline.status == PipelineRun.Status.RUNNING)

    if request.method == "POST":
        with transaction.atomic():
            order = get_object_or_404(
                ContentOrder.objects.select_for_update(), pk=pk, customer=request.user
            )
            pipeline = order.pipeline_runs.first()
            if pipeline and pipeline.status == PipelineRun.Status.RUNNING:
                messages.error(request, "Stop the current analysis before editing this project.")
                return redirect("orders:edit", pk=order.pk)

            form = ContentOrderForm(request.POST, instance=order)
            if form.is_valid():
                changed = set(form.changed_data)
                analysis_changes = changed & ANALYSIS_INPUT_FIELDS
                render_changes = changed & RENDER_INPUT_FIELDS
                was_cancelled = bool(pipeline and pipeline.status == PipelineRun.Status.CANCELLED)
                generated = has_generated_analysis(order)
                had_rendered_clips = order.clips.filter(
                    Q(status=Clip.Status.RENDERED)
                    | ~Q(video="")
                    | ~Q(audio="")
                    | ~Q(subtitle="")
                    | ~Q(thumbnail="")
                ).exists()
                form.save()

                restart_prepared = was_cancelled or bool(analysis_changes and generated)
                if restart_prepared:
                    prepare_analysis_restart(order)
                    order.status = ContentOrder.Status.SUBMITTED
                    order.save(update_fields=["status", "updated_at"])
                    message = "Project settings updated. A clean analysis is ready to restart."
                    event_type = "analysis_restart_prepared"
                elif render_changes and had_rendered_clips:
                    prepare_render_restart(order)
                    order.status = ContentOrder.Status.QUALITY_CHECK
                    order.save(update_fields=["status", "updated_at"])
                    message = "Finishing settings updated. Approved moments are ready to render again."
                    event_type = "render_restart_prepared"
                elif changed:
                    message = "Project settings updated."
                    event_type = "project_updated"
                else:
                    messages.info(request, "No project changes were made.")
                    return redirect("orders:detail", pk=order.pk)

                OrderEvent.objects.create(
                    order=order,
                    actor=request.user,
                    event_type=event_type,
                    message=message,
                )
                messages.success(request, message)
                return redirect("orders:detail", pk=order.pk)
    else:
        form = ContentOrderForm(instance=order)

    return render(
        request,
        "orders/edit.html",
        {
            "order": order,
            "form": form,
            "pipeline": pipeline,
            "analysis_active": analysis_active,
            "has_generated_analysis": has_generated_analysis(order),
            "source_asset": order.source_assets.first(),
        },
    )


@login_required
@transaction.atomic
def stop_analysis_for_edit(request, pk):
    if request.method != "POST":
        return redirect("orders:edit", pk=pk)
    order = get_object_or_404(ContentOrder, pk=pk, customer=request.user)
    pipeline = order.pipeline_runs.first()
    if pipeline:
        _, stopped = cancel_pipeline_run(pipeline, actor=request.user)
        if stopped:
            messages.success(request, "Analysis stopped safely. You can now edit the project brief.")
        else:
            messages.info(request, "The analysis was already inactive. You can edit the project now.")
    return redirect("orders:edit", pk=order.pk)
