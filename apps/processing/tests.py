from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient
from apps.orders.models import ContentOrder
from apps.orders.models import SourceAsset
from apps.accounts.models import SocialHandle
from .models import BrollPlan, Clip, ContentIntelligence, PipelineRun, RepurposeAsset, StageRun, TranscriptSegment
from .services import groq_provider
from .services import media
from .services import cloudinary_media
from .services import public_media
from .services import content_intelligence
from .services import broll
from unittest.mock import Mock, patch
from django.test import override_settings
from django.core.files.base import ContentFile
from pathlib import Path
from tempfile import TemporaryDirectory
import io
import zipfile

class ProcessingAccessTests(TestCase):
    def setUp(self):
        self.owner=User.objects.create_user("pipeline-owner",password="safe-test-pass")
        self.other=User.objects.create_user("pipeline-other",password="safe-test-pass")
        self.order=ContentOrder.objects.create(customer=self.owner,title="Long video",content_brief="Educational show")
        self.run=PipelineRun.objects.create(order=self.order)
        StageRun.objects.create(pipeline=self.run,name="ingest")
        Clip.objects.create(order=self.order,rank=1,title="Moment",hook="Watch this",caption="Caption",start_ms=0,end_ms=30000)

    def test_pipeline_api_is_customer_scoped(self):
        client=APIClient(); client.force_authenticate(self.other)
        response=client.get("/api/v1/pipeline-runs/")
        self.assertEqual(response.data["count"],0)

    def test_owner_can_read_clip(self):
        client=APIClient(); client.force_authenticate(self.owner)
        response=client.get("/api/v1/clips/")
        self.assertEqual(response.data["count"],1)

    def test_unique_clip_rank_per_order(self):
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Clip.objects.create(order=self.order,rank=1,title="Duplicate",hook="",caption="",start_ms=0,end_ms=1000)

    @patch("apps.processing.api.dispatch_pipeline")
    def test_owner_can_start_pipeline_from_api(self, dispatch):
        client=APIClient(); client.force_authenticate(self.owner)
        response=client.post(f"/api/v1/pipeline-runs/{self.run.id}/start/")
        self.assertEqual(response.status_code,202)
        self.order.refresh_from_db();self.assertEqual(self.order.status,ContentOrder.Status.IN_PROGRESS)
        dispatch.assert_called_once_with(self.run.id)

    @patch("apps.processing.api.dispatch_pipeline")
    def test_other_customer_cannot_start_pipeline(self, dispatch):
        client=APIClient(); client.force_authenticate(self.other)
        response=client.post(f"/api/v1/pipeline-runs/{self.run.id}/start/")
        self.assertEqual(response.status_code,404)
        dispatch.assert_not_called()

    def test_owner_can_cancel_running_pipeline_from_api(self):
        self.run.status=PipelineRun.Status.RUNNING; self.run.current_stage="ingest"; self.run.progress=5; self.run.save()
        stage=self.run.stages.get(name="ingest");stage.status=StageRun.Status.RUNNING;stage.save()
        client=APIClient();client.force_authenticate(self.owner)

        response=client.post(f"/api/v1/pipeline-runs/{self.run.id}/cancel/")

        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data["status"],PipelineRun.Status.CANCELLED)
        self.run.refresh_from_db();stage.refresh_from_db();self.order.refresh_from_db()
        self.assertEqual(self.run.current_stage,"cancelled_for_edit")
        self.assertEqual(stage.status,StageRun.Status.SKIPPED)
        self.assertEqual(self.order.status,ContentOrder.Status.REVISION)

    def test_cancelled_worker_exits_without_reactivating_run(self):
        from .pipeline import execute_pipeline
        self.run.status=PipelineRun.Status.CANCELLED;self.run.current_stage="cancelled_for_edit";self.run.save()
        with TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            execute_pipeline(self.run.id)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status,PipelineRun.Status.CANCELLED)
        self.assertFalse(self.run.stages.filter(status=StageRun.Status.RUNNING).exists())

    @patch("apps.processing.api.dispatch_render")
    @patch("apps.processing.api.shutil.which",return_value="C:/tools/ffmpeg.exe")
    @override_settings(FFMPEG_BINARY="ffmpeg",FFPROBE_BINARY="ffprobe")
    def test_owner_can_render_existing_recommendations(self, which, dispatch):
        self.run.status=PipelineRun.Status.REVIEW; self.run.current_stage="recommendations_ready"; self.run.save()
        self.order.clips.update(status=Clip.Status.APPROVED)
        client=APIClient(); client.force_authenticate(self.owner)
        response=client.post(f"/api/v1/pipeline-runs/{self.run.id}/render-exports/")
        self.assertEqual(response.status_code,202)
        self.assertEqual(response.data["current_stage"],"broll")
        dispatch.assert_called_once_with(self.run.id)

    @patch("apps.processing.api.shutil.which",return_value=None)
    @override_settings(FFMPEG_BINARY="missing-ffmpeg",FFPROBE_BINARY="missing-ffprobe")
    def test_render_explains_when_ffmpeg_is_missing(self, which):
        self.run.status=PipelineRun.Status.REVIEW; self.run.save()
        self.order.clips.update(status=Clip.Status.APPROVED)
        client=APIClient(); client.force_authenticate(self.owner)
        response=client.post(f"/api/v1/pipeline-runs/{self.run.id}/render-exports/")
        self.assertEqual(response.status_code,424)
        self.assertIn("FFmpeg",response.data["detail"])

    def test_render_requires_an_approved_clip(self):
        self.run.status=PipelineRun.Status.REVIEW; self.run.save()
        client=APIClient(); client.force_authenticate(self.owner)
        response=client.post(f"/api/v1/pipeline-runs/{self.run.id}/render-exports/")
        self.assertEqual(response.status_code,409)
        self.assertIn("Approve",response.data["detail"])

    def test_owner_can_approve_and_reject_a_clip(self):
        clip=self.order.clips.get(rank=1)
        client=APIClient(); client.force_authenticate(self.owner)
        response=client.post(f"/api/v1/clips/{clip.id}/approve/")
        self.assertEqual(response.status_code,200); self.assertEqual(response.data["status"],Clip.Status.APPROVED)
        response=client.post(f"/api/v1/clips/{clip.id}/reject/")
        self.assertEqual(response.status_code,200); self.assertEqual(response.data["status"],Clip.Status.REJECTED)

    def test_download_bundle_contains_video_audio_and_subtitles(self):
        client=APIClient(); client.force_authenticate(self.owner)
        clip=self.order.clips.get(rank=1)
        with TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            clip.video.save("moment.mp4",ContentFile(b"video"))
            clip.audio.save("moment.mp3",ContentFile(b"audio"))
            clip.subtitle.save("moment.srt",ContentFile(b"captions"))
            response=client.get(f"/api/v1/pipeline-runs/{self.run.id}/download-exports/")
            self.assertEqual(response.status_code,200)
            archive=io.BytesIO(b"".join(response.streaming_content))
            with zipfile.ZipFile(archive) as bundle:
                self.assertEqual(set(bundle.namelist()),{"clip-01-video.mp4","clip-01-audio.mp3","clip-01-subtitles.srt"})

    def test_clip_exposes_readable_timecodes(self):
        clip=self.order.clips.get(rank=1); clip.start_ms=65000; clip.end_ms=3723000
        self.assertEqual(clip.start_timecode,"1:05")
        self.assertEqual(clip.end_timecode,"1:02:03")

    @override_settings(GROQ_API_KEY="",STORAGES={"default":{"BACKEND":"django.core.files.storage.FileSystemStorage"},"staticfiles":{"BACKEND":"django.contrib.staticfiles.storage.StaticFilesStorage"}})
    def test_intelligence_review_is_customer_scoped(self):
        clip=self.order.clips.get(rank=1)
        content_intelligence.generate_for_clip(clip.id)
        self.client.force_login(self.owner)
        response=self.client.get(f"/intelligence/clips/{clip.id}/")
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'class="clipper-channel-score"')
        self.assertContains(response,'aria-label="Channel fit score')
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f"/intelligence/clips/{clip.id}/").status_code,404)

    @patch("apps.processing.api.dispatch_intelligence")
    def test_intelligence_can_be_dispatched_from_clip_api(self,dispatch):
        clip=self.order.clips.get(rank=1);client=APIClient();client.force_authenticate(self.owner)
        response=client.post(f"/api/v1/clips/{clip.id}/analyze-intelligence/")
        self.assertEqual(response.status_code,202);dispatch.assert_called_once_with(clip.id)

    @override_settings(GROQ_API_KEY="")
    def test_intelligence_baseline_builds_full_report_and_assets(self):
        clip=self.order.clips.get(rank=1)
        intelligence=content_intelligence.generate_for_clip(clip.id)
        self.assertEqual(intelligence.status,ContentIntelligence.Status.READY)
        self.assertIn("overall_quality_score",intelligence.content_dna)
        self.assertEqual(len(intelligence.platform_strategy),7)
        self.assertEqual(clip.repurpose_assets.count(),10)

    def test_repurpose_asset_is_editable_by_owner(self):
        clip=self.order.clips.get(rank=1);asset=RepurposeAsset.objects.create(clip=clip,kind="linkedin_post",title="Post",content="Original")
        client=APIClient();client.force_authenticate(self.owner)
        response=client.patch(f"/api/v1/repurpose-assets/{asset.id}/",{"content":"Edited"},format="json")
        self.assertEqual(response.status_code,200);self.assertEqual(response.data["content"],"Edited")

    def test_publication_jobs_allow_drafts_but_not_fake_direct_publish(self):
        clip=self.order.clips.get(rank=1);handle=SocialHandle.objects.create(user=self.owner,platform="linkedin",handle="@owner")
        client=APIClient();client.force_authenticate(self.owner)
        payload={"clip":clip.id,"social_handle":handle.id,"action":"draft","platform_payload":{"title":"Custom"}}
        self.assertEqual(client.post("/api/v1/publication-jobs/",payload,format="json").status_code,201)
        payload["action"]="publish"
        response=client.post("/api/v1/publication-jobs/",payload,format="json")
        self.assertEqual(response.status_code,400);self.assertIn("authenticated",str(response.data))

    @override_settings(GROQ_API_KEY="")
    def test_accepting_trim_recommendation_updates_final_render_instructions(self):
        clip=self.order.clips.get(rank=1);intelligence=content_intelligence.generate_for_clip(clip.id)
        client=APIClient();client.force_authenticate(self.owner)
        response=client.post(f"/api/v1/content-intelligence/{intelligence.id}/accept-editor-recommendation/",{"action_id":"trim-start"},format="json")
        self.assertEqual(response.status_code,200)
        clip.refresh_from_db();self.assertEqual(clip.editing_instructions["trim_start_ms"],3000)

    @patch("apps.processing.services.broll.media.normalize_broll_asset")
    @patch("apps.processing.services.broll.nvidia.generate_broll_video")
    @patch("apps.processing.services.broll.nvidia.plan_broll")
    def test_broll_is_planned_and_generated_only_for_approved_clips(self, plan, generate, normalize):
        self.order.broll_mode=ContentOrder.BrollMode.AI_GENERATED
        self.order.broll_intensity=ContentOrder.BrollIntensity.MINIMAL
        self.order.save(update_fields=["broll_mode","broll_intensity"])
        clip=self.order.clips.get(rank=1);clip.status=Clip.Status.APPROVED;clip.save(update_fields=["status"])
        TranscriptSegment.objects.create(order=self.order,start_ms=0,end_ms=30000,text="A practical lesson for content teams.")
        plan.return_value={"scenes":[{"start_ms":3000,"duration_ms":2500,"visual_prompt":"Editorial team reviewing clips","stock_query":"video editing team","reason":"Shows the workflow."}]}
        generate.side_effect=lambda prompt,destination,seconds=4: Path(destination).write_bytes(b"video")
        normalize.side_effect=lambda source,destination,duration: Path(destination).write_bytes(b"normalized")

        with TemporaryDirectory() as folder:
            assets,report=broll.prepare_order_broll(self.order,[clip],Path(folder))

        self.assertEqual(report["scenes"],1)
        self.assertEqual(len(assets[clip.pk]),1)
        saved=BrollPlan.objects.get(clip=clip)
        self.assertEqual(saved.status,BrollPlan.Status.READY)
        self.assertEqual(saved.scenes[0]["source_type"],"generated_video")
        plan.assert_called_once()
        generate.assert_called_once()

    @patch("apps.processing.services.broll.nvidia.plan_broll")
    def test_no_broll_keeps_existing_render_path_and_spends_no_ai(self, plan):
        clip=self.order.clips.get(rank=1);clip.status=Clip.Status.APPROVED;clip.save(update_fields=["status"])
        with TemporaryDirectory() as folder:
            assets,report=broll.prepare_order_broll(self.order,[clip],Path(folder))
        self.assertEqual(assets,{})
        self.assertFalse(report["enabled"])
        self.assertFalse(BrollPlan.objects.exists())
        plan.assert_not_called()

    @patch("apps.processing.services.broll.media.normalize_broll_asset")
    @patch("apps.processing.services.broll.nvidia.generate_broll_image")
    @patch("apps.processing.services.broll.nvidia.generate_broll_video")
    @patch("apps.processing.services.broll.nvidia.plan_broll")
    def test_broll_provider_failure_is_fail_soft(self, plan, video, image, normalize):
        self.order.broll_mode=ContentOrder.BrollMode.AI_GENERATED
        self.order.save(update_fields=["broll_mode"])
        clip=self.order.clips.get(rank=1);clip.status=Clip.Status.APPROVED;clip.save(update_fields=["status"])
        plan.return_value={"scenes":[{"start_ms":3000,"duration_ms":2500,"visual_prompt":"A supporting visual","stock_query":"team editing","reason":"Adds visual context."}]}
        video.side_effect=RuntimeError("Video provider unavailable")
        image.side_effect=RuntimeError("Image provider unavailable")

        with TemporaryDirectory() as folder:
            assets,report=broll.prepare_order_broll(self.order,[clip],Path(folder))

        saved=BrollPlan.objects.get(clip=clip)
        self.assertEqual(saved.status,BrollPlan.Status.FAILED)
        self.assertEqual(assets[clip.pk],[])
        self.assertTrue(report["warnings"])
        normalize.assert_not_called()

class GroqProviderTests(TestCase):
    @override_settings(GROQ_API_KEY="test-key", GROQ_TEXT_MODEL="test-model")
    @patch("apps.processing.services.groq_provider.requests.post")
    def test_ranker_sends_preferences_and_parses_schema_output(self, post):
        api_response=Mock(status_code=200, is_error=False, headers={})
        api_response.json.return_value={"choices":[{"message":{"content": '{"clips":[{"rank":1,"title":"Strong lesson","hook":"Most people miss this","caption":"Save this","start_ms":1000,"end_ms":31000,"score":9.2,"rationale":"Actionable","matched_preference":"Practical advice"}],"summary":"One match"}'}}]}
        post.return_value=api_response
        result=groq_provider.plan_package("[1000-31000] Useful lesson", "For founders", 600000, {"importance_definition":"Practical advice","moments_to_avoid":"Ads","desired_clip_count":1})
        self.assertEqual(result["clips"][0]["start_ms"],1000)
        sent=post.call_args.kwargs["json"]
        self.assertIn("Practical advice",sent["messages"][1]["content"])
        self.assertEqual(sent["response_format"]["type"],"json_schema")

    @override_settings(GROQ_API_KEY="test-key", GROQ_TRANSCRIPTION_MODEL="whisper-large-v3-turbo")
    @patch("apps.processing.services.groq_provider.requests.post")
    def test_transcription_converts_seconds_to_milliseconds(self, post):
        api_response=Mock(status_code=200, is_error=False, headers={})
        api_response.json.return_value={"text":"Hello world","segments":[{"start":1.25,"end":2.5,"text":"Hello world"}],"words":[{"start":1.25,"end":1.7,"word":"Hello"},{"start":1.7,"end":2.5,"word":"world"}]}
        post.return_value=api_response
        with TemporaryDirectory() as folder:
            audio=Path(folder)/"audio.wav"; audio.write_bytes(b"RIFF-test")
            result=groq_provider.transcribe(audio)
        self.assertEqual(result[0]["start_ms"],1250)
        self.assertEqual(result[0]["words"][1]["end_ms"],2500)

    @patch("apps.processing.services.groq_provider.logger")
    def test_rate_limit_error_logs_safe_headers_and_retry_after(self, logger):
        response=Mock(status_code=429, is_error=True, headers={
            "x-request-id":"req-test", "retry-after":"7",
            "x-ratelimit-remaining-tokens":"0", "x-ratelimit-reset-tokens":"7s",
        })
        response.json.return_value={"error":{"type":"rate_limit_exceeded","message":"Token limit reached"}}
        with self.assertRaisesRegex(Exception, "Retry after 7 seconds"):
            groq_provider._check_response(response,"chat/completions","test-model")
        logged=logger.log.call_args.args[2]
        self.assertIn('"remaining_tokens":"0"',logged)
        self.assertIn('"request_id":"req-test"',logged)
        self.assertIn('"error_code":"rate_limit_exceeded"',logged)

    @patch("apps.processing.services.groq_provider.GROQ_UPLOAD_LIMIT_BYTES",4)
    @patch("apps.processing.services.groq_provider._transcribe_file")
    @patch("apps.processing.services.groq_provider.media.split_audio")
    def test_large_audio_is_chunked_and_timestamps_are_merged(self, split_audio, transcribe_file):
        with TemporaryDirectory() as folder:
            source=Path(folder)/"large.mp3";source.write_bytes(b"large")
            first=Path(folder)/"chunk-000.mp3";first.write_bytes(b"one")
            second=Path(folder)/"chunk-001.mp3";second.write_bytes(b"two")
            split_audio.return_value=[first,second]
            transcribe_file.side_effect=[
                [{"start_ms":100,"end_ms":500,"text":"First","words":[{"word":"First","start_ms":100,"end_ms":500}]}],
                [{"start_ms":200,"end_ms":600,"text":"Second","words":[{"word":"Second","start_ms":200,"end_ms":600}]}],
            ]
            result=groq_provider.transcribe(source)
        self.assertEqual(result[1]["start_ms"],900200)
        self.assertEqual(result[1]["words"][0]["end_ms"],900600)
        split_audio.assert_called_once()

    @patch("apps.processing.services.media.run")
    def test_audio_extraction_is_compressed_for_transcription(self, run):
        with TemporaryDirectory() as folder:
            destination=Path(folder)/"audio.mp3"
            media.extract_audio("source.mp4",destination)
        command=run.call_args.args[0]
        self.assertIn("libmp3lame",command)
        self.assertIn("64k",command)
        self.assertIn("16000",command)

class CloudinaryFallbackTests(TestCase):
    @override_settings(CLOUDINARY_CLOUD_NAME="demo",CLOUDINARY_API_KEY="key",CLOUDINARY_API_SECRET="secret")
    @patch("cloudinary.uploader.upload")
    def test_upload_persists_only_remote_asset_metadata(self, upload):
        upload.return_value={"public_id":"recast/source/test","secure_url":"https://example.test/video.webm","duration":42.4}
        user=User.objects.create_user("cloud-owner",password="safe-test-pass")
        order=ContentOrder.objects.create(customer=user,title="Cloud test",content_brief="Test")
        asset=SourceAsset.objects.create(order=order,external_url="https://example.test/source.webm")
        with TemporaryDirectory() as folder:
            source=Path(folder)/"source.webm"; source.write_bytes(b"test-media")
            cloudinary_media.ensure_uploaded(asset,source)
        asset.refresh_from_db()
        self.assertEqual(asset.cloudinary_public_id,"recast/source/test")
        self.assertEqual(asset.duration_seconds,42)
        upload.assert_called_once()

    @override_settings(CLOUDINARY_CLOUD_NAME="demo",CLOUDINARY_API_KEY="key",CLOUDINARY_API_SECRET="secret")
    def test_preview_url_contains_trim_and_vertical_transformations(self):
        url=cloudinary_media.preview_url("recast/source/test",1000,31000)
        self.assertIn("so_1.0",url); self.assertIn("eo_31.0",url)
        self.assertIn("c_fill",url); self.assertIn("h_960",url); self.assertIn("w_540",url)

class PublicMediaTests(TestCase):
    def test_direct_media_detection_does_not_treat_youtube_as_a_file(self):
        self.assertTrue(public_media.is_direct_media_url("https://cdn.example.com/show.mp4?token=abc"))
        self.assertFalse(public_media.is_direct_media_url("https://www.youtube.com/watch?v=abc"))

    def test_youtube_authentication_errors_are_identified_for_recovery(self):
        self.assertTrue(public_media.is_youtube_url("https://youtu.be/example"))
        self.assertTrue(
            public_media.is_youtube_authentication_error(
                "ERROR: Sign in to confirm you’re not a bot"
            )
        )
