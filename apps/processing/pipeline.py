import json, shutil
from pathlib import Path
from urllib.parse import urlparse
import requests
from django.conf import settings
from django.core.files import File
from django.db import transaction
from django.utils import timezone
from apps.deliverables.models import Deliverable
from apps.orders.models import ContentOrder, OrderEvent
from .models import Clip, PipelineRun, StageRun, TranscriptSegment
from .services import media, nvidia, openai_poc, cloudinary_media, public_media
from .services.thumbnails import create_thumbnail

STAGES=[("ingest",5),("audio",12),("transcribe",30),("strategy",48),("render",88),("package",100)]

def _stage(run,name):
    stage,_=StageRun.objects.get_or_create(pipeline=run,name=name)
    stage.status=StageRun.Status.RUNNING; stage.attempts+=1; stage.started_at=timezone.now(); stage.error=""; stage.save()
    run.current_stage=name; run.status=PipelineRun.Status.RUNNING; run.save(update_fields=["current_stage","status","updated_at"])
    return stage

def _complete(run,stage,metadata=None):
    stage.status=StageRun.Status.COMPLETED; stage.finished_at=timezone.now(); stage.metadata=metadata or {}; stage.save()
    run.progress=dict(STAGES)[stage.name]; run.save(update_fields=["progress","updated_at"])

def _download(url,destination):
    parsed=urlparse(url)
    if parsed.scheme not in {"http","https"}: raise ValueError("Only HTTP(S) source links are supported.")
    public_media.assert_public_url(url)
    with requests.get(url,stream=True,timeout=(15,120),allow_redirects=True) as response:
        response.raise_for_status()
        public_media.assert_public_url(response.url)
        declared=int(response.headers.get("content-length") or 0)
        if declared > settings.PUBLIC_MEDIA_MAX_BYTES: raise ValueError("This media file exceeds the configured import size limit.")
        downloaded=0
        with open(destination,"wb") as output:
            for chunk in response.iter_content(1024*1024):
                downloaded+=len(chunk)
                if downloaded > settings.PUBLIC_MEDIA_MAX_BYTES: raise ValueError("This media file exceeds the configured import size limit.")
                output.write(chunk)

def _source(order,work):
    asset=order.source_assets.first()
    if not asset: raise ValueError("This order has no source asset.")
    if asset.file: return Path(asset.file.path)
    if public_media.is_direct_media_url(asset.external_url):
        destination=work/"source-video"
        _download(asset.external_url,destination)
        return destination
    return public_media.download_with_ytdlp(asset.external_url,work)

def _transcript_text(order):
    return "\n".join(f"[{s.start_ms}-{s.end_ms}] {s.text}" for s in order.transcript_segments.all())

def _provider():
    return openai_poc if settings.AI_PROVIDER == "openai" else nvidia

def _deliver(order,kind,title,content="",file_path=None,creator=None):
    latest=Deliverable.objects.filter(order=order,kind=kind).order_by("-version").first()
    version=(latest.version+1) if latest else 1
    item=Deliverable(order=order,kind=kind,title=title,content=content,status=Deliverable.Status.READY,version=version,created_by=creator)
    if file_path:
        with open(file_path,"rb") as handle: item.file.save(Path(file_path).name,File(handle),save=False)
    item.save(); return item

def _render_clip_files(order, source, work):
    """Render every approved AI range into video, audio, captions and artwork."""
    segments=list(order.transcript_segments.all())
    clips=list(order.clips.filter(status=Clip.Status.APPROVED))
    if not clips: raise ValueError("Approve at least one suggested clip before rendering exports.")
    for clip in clips:
        srt=work/f"clip-{clip.rank:02}.srt"
        video=work/f"clip-{clip.rank:02}.mp4"
        audio=work/f"clip-{clip.rank:02}.mp3"
        frame=work/f"clip-{clip.rank:02}.jpg"
        thumb=work/f"clip-{clip.rank:02}-thumbnail.jpg"
        media.write_srt(segments,clip.start_ms,clip.end_ms,srt)
        media.render_vertical(source,clip.start_ms,clip.end_ms,srt,video)
        media.render_audio_clip(source,clip.start_ms,clip.end_ms,audio)
        media.extract_frame(source,clip.start_ms+min(2000,(clip.end_ms-clip.start_ms)//2),frame)
        create_thumbnail(frame,clip.title,thumb)
        with open(video,"rb") as handle: clip.video.save(video.name,File(handle),save=False)
        with open(audio,"rb") as handle: clip.audio.save(audio.name,File(handle),save=False)
        with open(srt,"rb") as handle: clip.subtitle.save(srt.name,File(handle),save=False)
        with open(thumb,"rb") as handle: clip.thumbnail.save(thumb.name,File(handle),save=False)
        clip.status=Clip.Status.RENDERED
        clip.save()
    return len(clips)

def render_existing_clips(run_id):
    """Resume an analysis-only run at export without repeating transcription or AI."""
    run=PipelineRun.objects.select_related("order").get(pk=run_id); order=run.order
    work=Path(settings.MEDIA_ROOT)/"work"/f"{run.id}-exports"; work.mkdir(parents=True,exist_ok=True)
    run.started_at=run.started_at or timezone.now(); run.error=""; run.progress=50; run.save()
    try:
        source=_source(order,work)
        stage=_stage(run,"render")
        rendered=_render_clip_files(order,source,work)
        _complete(run,stage,{"rendered":rendered,"formats":["mp4","mp3","srt","jpg"]})
        run.status=PipelineRun.Status.REVIEW; run.current_stage="quality_review"; run.progress=100; run.finished_at=timezone.now(); run.save()
        order.status=ContentOrder.Status.QUALITY_CHECK; order.save()
        OrderEvent.objects.create(order=order,event_type="exports_ready",message=f"{rendered} video and audio clip exports are ready to download.")
    except Exception as exc:
        current=run.stages.filter(status=StageRun.Status.RUNNING).last()
        if current: current.status=StageRun.Status.FAILED; current.error=str(exc); current.finished_at=timezone.now(); current.save()
        run.status=PipelineRun.Status.FAILED; run.error=str(exc); run.finished_at=timezone.now(); run.save()
        raise
    finally:
        shutil.rmtree(work,ignore_errors=True)

def execute_pipeline(run_id):
    run=PipelineRun.objects.select_related("order").get(pk=run_id); order=run.order
    work=Path(settings.MEDIA_ROOT)/"work"/str(run.id); work.mkdir(parents=True,exist_ok=True)
    run.started_at=run.started_at or timezone.now(); run.error=""; run.save()
    try:
        stage=_stage(run,"ingest"); source=_source(order,work); asset=order.source_assets.first()
        cloudinary_first=settings.MEDIA_PIPELINE_PRIMARY == "cloudinary" and cloudinary_media.configured()
        if cloudinary_first:
            try:
                remote=cloudinary_media.ensure_uploaded(asset,source)
                duration_ms=int(float(remote.get("duration") or asset.duration_seconds or 0)*1000); ingest_engine="cloudinary"
            except Exception:
                info=media.probe(source)
                duration_ms=int(float(info.get("format",{}).get("duration",0))*1000); ingest_engine="ffprobe-fallback"
        else:
            try:
                info=media.probe(source)
                duration_ms=int(float(info.get("format",{}).get("duration",0))*1000); ingest_engine="ffprobe"
            except media.MediaError:
                if not settings.CLOUDINARY_FALLBACK_ENABLED: raise
                remote=cloudinary_media.ensure_uploaded(asset,source)
                duration_ms=int(float(remote.get("duration") or asset.duration_seconds or 0)*1000); ingest_engine="cloudinary-fallback"
        if duration_ms<5000: raise ValueError("The source must be at least five seconds long.")
        if settings.PIPELINE_ANALYSIS_ONLY and duration_ms > 11 * 60 * 1000:
            raise ValueError("The proof of concept accepts recordings up to 11 minutes. Trim this source and try again.")
        _complete(run,stage,{"source":str(source),"duration_ms":duration_ms,"engine":ingest_engine,"cloudinary_public_id":asset.cloudinary_public_id})

        stage=_stage(run,"audio")
        if cloudinary_first and asset.cloudinary_public_id:
            try:
                audio=work/"audio.mp3"; cloudinary_media.download_audio(asset,source,audio); audio_engine="cloudinary"
            except Exception:
                audio=work/"audio.wav"; media.extract_audio(source,audio); audio_engine="ffmpeg-fallback"
        else:
            audio=work/"audio.wav"; audio_engine="ffmpeg"
            try:
                media.extract_audio(source,audio)
            except media.MediaError:
                if not settings.CLOUDINARY_FALLBACK_ENABLED: raise
                audio=work/"audio.mp3"; cloudinary_media.download_audio(asset,source,audio); audio_engine="cloudinary-fallback"
        _complete(run,stage,{"audio":str(audio),"engine":audio_engine})

        stage=_stage(run,"transcribe")
        provider = _provider()
        transcript=provider.transcribe(audio,order.content_brief)
        with transaction.atomic():
            order.transcript_segments.all().delete()
            TranscriptSegment.objects.bulk_create([TranscriptSegment(order=order,**segment) for segment in transcript])
        _complete(run,stage,{"segments":len(transcript),"provider":settings.AI_PROVIDER})

        stage=_stage(run,"strategy")
        preferences={"importance_definition":order.importance_definition,"moments_to_avoid":order.moments_to_avoid,"desired_clip_count":order.desired_clip_count,"min_clip_seconds":order.min_clip_seconds,"max_clip_seconds":order.max_clip_seconds}
        if settings.AI_PROVIDER == "openai":
            package=provider.plan_package(_transcript_text(order),f"{order.content_brief}\nVoice: {order.brand_voice}",duration_ms,preferences)
        else:
            package=provider.plan_package(_transcript_text(order),f"{order.content_brief}\nImportance: {order.importance_definition}\nAvoid: {order.moments_to_avoid}\nVoice: {order.brand_voice}",duration_ms)
        order.clips.all().delete()
        clips=[]
        for idx,data in enumerate(package.get("clips",[])[:order.desired_clip_count],1):
            start=max(0,min(int(data.get("start_ms",0)),duration_ms-1000)); end=max(start+1000,min(int(data.get("end_ms",start+30000)),duration_ms))
            rationale=data.get("rationale","")
            if data.get("matched_preference"): rationale=f"{data['matched_preference']} — {rationale}"
            preview=cloudinary_media.preview_url(asset.cloudinary_public_id,start,end) if asset.cloudinary_public_id else ""
            clips.append(Clip(order=order,rank=idx,title=str(data.get("title",f"Clip {idx}"))[:160],hook=str(data.get("hook",""))[:240],caption=data.get("caption",""),start_ms=start,end_ms=end,score=data.get("score",0),rationale=rationale,preview_url=preview))
        while len(clips)<order.desired_clip_count:
            idx=len(clips)+1; span=max(5000,duration_ms//10); start=min((idx-1)*span,duration_ms-1000); end=min(duration_ms,start+span)
            preview=cloudinary_media.preview_url(asset.cloudinary_public_id,start,end) if asset.cloudinary_public_id else ""
            clips.append(Clip(order=order,rank=idx,title=f"Clip {idx}",hook="A key moment",caption="",start_ms=start,end_ms=end,preview_url=preview))
        Clip.objects.bulk_create(clips)
        (work/"package.json").write_text(json.dumps(package,indent=2),encoding="utf-8")
        _complete(run,stage,{"clips":len(clips),"provider":settings.AI_PROVIDER,"model":settings.OPENAI_TEXT_MODEL if settings.AI_PROVIDER == "openai" else settings.NVIDIA_LLM_MODEL,"summary":package.get("summary","")})

        if settings.PIPELINE_REQUIRE_APPROVAL or settings.PIPELINE_ANALYSIS_ONLY:
            stage,_=StageRun.objects.get_or_create(pipeline=run,name="render"); stage.status=StageRun.Status.SKIPPED; stage.metadata={"reason":"Awaiting customer clip approval"}; stage.finished_at=timezone.now(); stage.save()
            stage=_stage(run,"package")
            clip_text="\n\n".join(f"{c.rank}. {c.title}\n{c.start_ms/1000:.1f}s–{c.end_ms/1000:.1f}s · Score {c.score}/10\nHook: {c.hook}\nWhy: {c.rationale}\nCaption: {c.caption}" for c in order.clips.all())
            _deliver(order,Deliverable.Kind.CLIP_PLAN,f"{len(clips)} AI-ranked clip recommendations",clip_text,creator=run.order.customer)
            _complete(run,stage,{"deliverables":1,"awaiting_approval":True,"cloudinary_previews":bool(asset.cloudinary_public_id)})
            run.status=PipelineRun.Status.REVIEW; run.current_stage="awaiting_approval"; run.progress=100; run.finished_at=timezone.now(); run.save()
            order.status=ContentOrder.Status.QUALITY_CHECK; order.save()
            OrderEvent.objects.create(order=order,event_type="analysis_complete",message="Your AI-ranked clip recommendations are ready.")
            shutil.rmtree(work,ignore_errors=True)
            return

        stage=_stage(run,"render")
        rendered=_render_clip_files(order,source,work)
        _complete(run,stage,{"rendered":rendered,"formats":["mp4","mp3","srt","jpg"]})

        stage=_stage(run,"package")
        clip_text="\n\n".join(f"{c.rank}. {c.title}\n{c.start_ms/1000:.1f}s–{c.end_ms/1000:.1f}s\nHook: {c.hook}\nCaption: {c.caption}" for c in order.clips.all())
        _deliver(order,Deliverable.Kind.CLIP_PLAN,"10 short-form clips",clip_text,creator=run.order.customer)
        social=package.get("social_posts",{}); _deliver(order,Deliverable.Kind.SOCIAL_POSTS,"LinkedIn, X and Instagram posts",json.dumps(social,indent=2),creator=run.order.customer)
        youtube=package.get("youtube",{}); _deliver(order,Deliverable.Kind.YOUTUBE_PACKAGE,"YouTube title, description and chapters",json.dumps(youtube,indent=2),creator=run.order.customer)
        newsletter=package.get("newsletter",{}); _deliver(order,Deliverable.Kind.NEWSLETTER,newsletter.get("title","Newsletter / article"),newsletter.get("body",""),creator=run.order.customer)
        delivered=4
        if order.include_audio_cleanup:
            cleaned=work/"cleaned-audio.mp3"; media.clean_audio(source,cleaned)
            _deliver(order,Deliverable.Kind.CLEAN_AUDIO,"Cleaned master audio",file_path=cleaned,creator=run.order.customer); delivered+=1
        _complete(run,stage,{"deliverables":delivered})
        run.status=PipelineRun.Status.REVIEW; run.current_stage="quality_review"; run.finished_at=timezone.now(); run.save()
        order.status=ContentOrder.Status.QUALITY_CHECK; order.save()
        OrderEvent.objects.create(order=order,event_type="pipeline_complete",message="Your clips and content package are ready for quality review.")
    except Exception as exc:
        current=run.stages.filter(status=StageRun.Status.RUNNING).last()
        if current: current.status=StageRun.Status.FAILED; current.error=str(exc); current.finished_at=timezone.now(); current.save()
        run.status=PipelineRun.Status.FAILED; run.error=str(exc); run.finished_at=timezone.now(); run.save()
        raise
    finally:
        if run.status==PipelineRun.Status.REVIEW: shutil.rmtree(work,ignore_errors=True)
