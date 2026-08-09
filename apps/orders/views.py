from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from .forms import ContentOrderForm, SourceAssetForm
from .models import ContentOrder, OrderEvent
from apps.processing.models import PipelineRun

@login_required
def dashboard(request):
    orders = request.user.content_orders.prefetch_related("deliverables")
    return render(request, "orders/dashboard.html", {"orders": orders})

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
    order = get_object_or_404(ContentOrder.objects.prefetch_related("source_assets", "deliverables", "events", "clips", "pipeline_runs__stages"), pk=pk, customer=request.user)
    pipeline = order.pipeline_runs.first()
    if pipeline is None: pipeline = PipelineRun.objects.create(order=order)
    clips=list(order.clips.all())
    rendered=sum(bool(clip.video) for clip in clips)
    approved=sum(clip.status == "approved" for clip in clips)
    return render(request, "orders/detail.html", {
        "order": order,
        "pipeline": pipeline,
        "clip_count": len(clips),
        "rendered_count": rendered,
        "approved_count": approved,
        "exports_ready": rendered > 0 and approved == 0,
    })
