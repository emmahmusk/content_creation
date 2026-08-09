from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from apps.processing.models import Clip, ContentIntelligence


@login_required
def intelligence_review(request, clip_id):
    clip=get_object_or_404(Clip.objects.select_related("order").prefetch_related("order__transcript_segments","repurpose_assets"),pk=clip_id,order__customer=request.user)
    intelligence,_=ContentIntelligence.objects.get_or_create(clip=clip)
    segments=clip.order.transcript_segments.filter(start_ms__lt=clip.end_ms,end_ms__gt=clip.start_ms)
    return render(request,"processing/intelligence_review.html",{"clip":clip,"intelligence":intelligence,"segments":segments,"social_handles":request.user.social_handles.all()})
