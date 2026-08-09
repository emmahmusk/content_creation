import io
import shutil
import zipfile
from pathlib import Path
from django.conf import settings
from django.http import FileResponse
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Clip, ContentIntelligence, LearningSignal, PipelineRun, PublicationJob, RepurposeAsset, TranscriptSegment
from .serializers import ClipSerializer, ContentIntelligenceSerializer, LearningSignalSerializer, PipelineRunSerializer, PublicationJobSerializer, RepurposeAssetSerializer, TranscriptSegmentSerializer
from .tasks import dispatch_intelligence, dispatch_pipeline, dispatch_render

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

    @action(detail=True,methods=["post"],url_path="analyze-intelligence")
    def analyze_intelligence(self,request,pk=None):
        clip=self.get_object();intelligence,_=ContentIntelligence.objects.get_or_create(clip=clip)
        if intelligence.status==ContentIntelligence.Status.RUNNING: return Response(ContentIntelligenceSerializer(intelligence).data,status=202)
        intelligence.status=ContentIntelligence.Status.QUEUED;intelligence.error="";intelligence.save(update_fields=["status","error","updated_at"])
        dispatch_intelligence(clip.id)
        return Response(ContentIntelligenceSerializer(intelligence).data,status=202)

class TranscriptViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=TranscriptSegmentSerializer; filterset_fields=["order"]
    def get_queryset(self):
        qs=TranscriptSegment.objects.select_related("order")
        return qs if self.request.user.is_staff else qs.filter(order__customer=self.request.user)

class ContentIntelligenceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=ContentIntelligenceSerializer
    def get_queryset(self): return ContentIntelligence.objects.select_related("clip__order").filter(clip__order__customer=self.request.user)
    @action(detail=True,methods=["post"],url_path="accept-editor-recommendation")
    def accept_editor_recommendation(self,request,pk=None):
        intelligence=self.get_object();action_id=request.data.get("action_id")
        recommendation=next((item for item in intelligence.editor_recommendations if item.get("id")==action_id),None)
        if not recommendation: return Response({"detail":"This recommendation was not found."},status=404)
        instructions=dict(intelligence.clip.editing_instructions);accepted=list(instructions.get("accepted",[]))
        if action_id not in accepted: accepted.append(action_id)
        instructions["accepted"]=accepted
        if action_id=="trim-start": instructions["trim_start_ms"]=3000
        if action_id=="highlight-quote": instructions["highlight_quote"]=recommendation.get("description","")
        if action_id=="boost-hook": instructions["preferred_hook"]=intelligence.clip.hook
        intelligence.clip.editing_instructions=instructions;intelligence.clip.save(update_fields=["editing_instructions"])
        LearningSignal.objects.create(clip=intelligence.clip,event_type="editor_recommendation_accepted",value=1,metadata={"recommendation_id":action_id})
        return Response({"accepted":accepted,"editing_instructions":instructions})

class RepurposeAssetViewSet(viewsets.ModelViewSet):
    serializer_class=RepurposeAssetSerializer;http_method_names=["get","patch","head","options"]
    def get_queryset(self): return RepurposeAsset.objects.select_related("clip__order").filter(clip__order__customer=self.request.user)
    @action(detail=True,methods=["post"])
    def transform(self,request,pk=None):
        asset=self.get_object();operation=request.data.get("operation")
        if operation not in {"improve","shorten","expand","change_tone","regenerate"}: return Response({"detail":"Unsupported transformation."},status=400)
        text=asset.content
        if operation=="shorten": text=text[:max(80,len(text)//2)].rstrip()+("…" if len(text)>80 else "")
        elif operation=="expand": text=f"{text}\n\nKey context\nExpand this idea with one concrete example and a practical next step."
        elif operation=="improve": text=f"{text}\n\nPractical takeaway: make the next action specific, useful, and easy to remember."
        elif operation=="change_tone": text=f"{text}\n\nTone: clear, confident, and conversational."
        else: text=f"{asset.clip.hook}\n\n{asset.clip.caption}\n\n{asset.content.splitlines()[-1] if asset.content else ''}".strip()
        asset.content=text;asset.version+=1;asset.save(update_fields=["content","version","updated_at"])
        return Response(self.get_serializer(asset).data)

class PublicationJobViewSet(viewsets.ModelViewSet):
    serializer_class=PublicationJobSerializer;http_method_names=["get","post","head","options"]
    def get_queryset(self): return PublicationJob.objects.select_related("clip","social_handle").filter(user=self.request.user)

class LearningSignalViewSet(viewsets.ModelViewSet):
    serializer_class=LearningSignalSerializer;http_method_names=["get","post","head","options"]
    def get_queryset(self): return LearningSignal.objects.select_related("clip__order").filter(clip__order__customer=self.request.user)
