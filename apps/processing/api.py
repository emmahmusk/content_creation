from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Clip, PipelineRun, TranscriptSegment
from .serializers import ClipSerializer, PipelineRunSerializer, TranscriptSegmentSerializer
from .tasks import dispatch_pipeline

class PipelineRunViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=PipelineRunSerializer
    def get_queryset(self):
        qs=PipelineRun.objects.select_related("order").prefetch_related("stages")
        return qs if self.request.user.is_staff else qs.filter(order__customer=self.request.user)
    @action(detail=True,methods=["post"])
    def start(self,request,pk=None):
        run=self.get_object()
        if run.status not in [PipelineRun.Status.FAILED,PipelineRun.Status.QUEUED]: return Response({"detail":"Only queued or failed runs can be started."},status=409)
        run.status=PipelineRun.Status.RUNNING; run.error=""; run.progress=0; run.current_stage="starting"; run.finished_at=None; run.save()
        try:
            dispatch_pipeline(run.id)
        except Exception as exc:
            run.status=PipelineRun.Status.FAILED; run.error=f"Could not dispatch job: {exc}"; run.save()
            return Response({"detail":run.error},status=503)
        return Response(self.get_serializer(run).data,status=202)

    @action(detail=True,methods=["post"])
    def retry(self,request,pk=None):
        return self.start(request,pk)

class ClipViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=ClipSerializer; filterset_fields=["order","status"]
    def get_queryset(self):
        qs=Clip.objects.select_related("order")
        return qs if self.request.user.is_staff else qs.filter(order__customer=self.request.user)

class TranscriptViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=TranscriptSegmentSerializer; filterset_fields=["order"]
    def get_queryset(self):
        qs=TranscriptSegment.objects.select_related("order")
        return qs if self.request.user.is_staff else qs.filter(order__customer=self.request.user)
