import io
import shutil
import zipfile
from pathlib import Path
from django.conf import settings
from django.http import FileResponse
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Clip, PipelineRun, TranscriptSegment
from .serializers import ClipSerializer, PipelineRunSerializer, TranscriptSegmentSerializer
from .tasks import dispatch_pipeline, dispatch_render

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

    @action(detail=True,methods=["post"],url_path="render-exports")
    def render_exports(self,request,pk=None):
        run=self.get_object()
        if run.status == PipelineRun.Status.RUNNING:
            return Response({"detail":"This job is already running."},status=409)
        if not run.order.clips.filter(status=Clip.Status.APPROVED).exists():
            return Response({"detail":"Approve at least one suggested clip before rendering exports."},status=409)
        missing=[binary for binary in (settings.FFMPEG_BINARY,settings.FFPROBE_BINARY) if not (Path(binary).exists() or shutil.which(binary))]
        if missing:
            return Response({"detail":f"Media rendering is unavailable because {', '.join(missing)} is not installed. Install FFmpeg and FFprobe or run the Docker stack."},status=424)
        run.status=PipelineRun.Status.RUNNING; run.error=""; run.progress=50; run.current_stage="rendering_exports"; run.finished_at=None; run.save()
        try:
            dispatch_render(run.id)
        except Exception as exc:
            run.status=PipelineRun.Status.FAILED; run.error=f"Could not dispatch export job: {exc}"; run.save()
            return Response({"detail":run.error},status=503)
        return Response(self.get_serializer(run).data,status=202)

    @action(detail=True,methods=["get"],url_path="download-exports")
    def download_exports(self,request,pk=None):
        run=self.get_object(); clips=list(run.order.clips.all())
        if not any(clip.video or clip.audio or clip.subtitle for clip in clips):
            return Response({"detail":"No rendered exports are available yet."},status=404)
        archive=io.BytesIO()
        with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as bundle:
            for clip in clips:
                for label,field in (("video",clip.video),("audio",clip.audio),("subtitles",clip.subtitle),("thumbnail",clip.thumbnail)):
                    if not field: continue
                    suffix=Path(field.name).suffix
                    with field.open("rb") as source:
                        bundle.writestr(f"clip-{clip.rank:02}-{label}{suffix}",source.read())
        archive.seek(0)
        filename=f"{run.order.title[:60].strip().replace(' ','-') or 'recast'}-clips.zip"
        return FileResponse(archive,as_attachment=True,filename=filename,content_type="application/zip")

class ClipViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=ClipSerializer; filterset_fields=["order","status"]
    def get_queryset(self):
        qs=Clip.objects.select_related("order")
        return qs if self.request.user.is_staff else qs.filter(order__customer=self.request.user)

    @action(detail=True,methods=["post"])
    def approve(self,request,pk=None):
        clip=self.get_object()
        if clip.status == Clip.Status.RENDERED:
            return Response({"detail":"This clip has already been rendered."},status=409)
        clip.status=Clip.Status.APPROVED; clip.save(update_fields=["status"])
        return Response(self.get_serializer(clip).data)

    @action(detail=True,methods=["post"])
    def reject(self,request,pk=None):
        clip=self.get_object()
        if clip.status == Clip.Status.RENDERED:
            return Response({"detail":"This clip has already been rendered."},status=409)
        clip.status=Clip.Status.REJECTED; clip.save(update_fields=["status"])
        return Response(self.get_serializer(clip).data)

class TranscriptViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=TranscriptSegmentSerializer; filterset_fields=["order"]
    def get_queryset(self):
        qs=TranscriptSegment.objects.select_related("order")
        return qs if self.request.user.is_staff else qs.filter(order__customer=self.request.user)
