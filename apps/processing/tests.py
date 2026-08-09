from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient
from apps.orders.models import ContentOrder
from apps.orders.models import SourceAsset
from .models import Clip, PipelineRun, StageRun
from .services import openai_poc
from .services import cloudinary_media
from .services import public_media
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
        dispatch.assert_called_once_with(self.run.id)

    @patch("apps.processing.api.dispatch_pipeline")
    def test_other_customer_cannot_start_pipeline(self, dispatch):
        client=APIClient(); client.force_authenticate(self.other)
        response=client.post(f"/api/v1/pipeline-runs/{self.run.id}/start/")
        self.assertEqual(response.status_code,404)
        dispatch.assert_not_called()

    @patch("apps.processing.api.dispatch_render")
    @patch("apps.processing.api.shutil.which",return_value="C:/tools/ffmpeg.exe")
    def test_owner_can_render_existing_recommendations(self, which, dispatch):
        self.run.status=PipelineRun.Status.REVIEW; self.run.current_stage="recommendations_ready"; self.run.save()
        self.order.clips.update(status=Clip.Status.APPROVED)
        client=APIClient(); client.force_authenticate(self.owner)
        response=client.post(f"/api/v1/pipeline-runs/{self.run.id}/render-exports/")
        self.assertEqual(response.status_code,202)
        self.assertEqual(response.data["current_stage"],"rendering_exports")
        dispatch.assert_called_once_with(self.run.id)

    @patch("apps.processing.api.shutil.which",return_value=None)
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

class OpenAIPocTests(TestCase):
    @override_settings(OPENAI_API_KEY="test-key", OPENAI_TEXT_MODEL="test-model")
    @patch("apps.processing.services.openai_poc.requests.post")
    def test_ranker_sends_preferences_and_parses_schema_output(self, post):
        api_response=Mock(); api_response.raise_for_status.return_value=None
        api_response.json.return_value={"output_text": '{"clips":[{"rank":1,"title":"Strong lesson","hook":"Most people miss this","caption":"Save this","start_ms":1000,"end_ms":31000,"score":9.2,"rationale":"Actionable","matched_preference":"Practical advice"}],"summary":"One match"}'}
        post.return_value=api_response
        result=openai_poc.plan_package("[1000-31000] Useful lesson", "For founders", 600000, {"importance_definition":"Practical advice","moments_to_avoid":"Ads","desired_clip_count":1})
        self.assertEqual(result["clips"][0]["start_ms"],1000)
        sent=post.call_args.kwargs["json"]
        self.assertIn("Practical advice",sent["input"])
        self.assertEqual(sent["text"]["format"]["type"],"json_schema")

    @override_settings(OPENAI_API_KEY="test-key", OPENAI_TRANSCRIPTION_MODEL="whisper-1")
    @patch("apps.processing.services.openai_poc.requests.post")
    def test_transcription_converts_seconds_to_milliseconds(self, post):
        api_response=Mock(); api_response.raise_for_status.return_value=None
        api_response.json.return_value={"text":"Hello world","segments":[{"start":1.25,"end":2.5,"text":"Hello world"}],"words":[{"start":1.25,"end":1.7,"word":"Hello"},{"start":1.7,"end":2.5,"word":"world"}]}
        post.return_value=api_response
        with TemporaryDirectory() as folder:
            audio=Path(folder)/"audio.wav"; audio.write_bytes(b"RIFF-test")
            result=openai_poc.transcribe(audio)
        self.assertEqual(result[0]["start_ms"],1250)
        self.assertEqual(result[0]["words"][1]["end_ms"],2500)

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

    @override_settings(PUBLIC_MEDIA_MAX_BYTES=1000000,FFMPEG_BINARY="ffmpeg")
    @patch("apps.processing.services.public_media.socket.getaddrinfo",return_value=[(2,1,6,"",("8.8.8.8",443))])
    @patch("yt_dlp.YoutubeDL")
    def test_hosted_video_download_is_single_video_and_size_limited(self,downloader_class,getaddrinfo):
        with TemporaryDirectory() as folder:
            output=Path(folder)/"public-source-test.mp4";output.write_bytes(b"video")
            downloader=downloader_class.return_value.__enter__.return_value
            downloader.extract_info.return_value={"id":"test","filepath":str(output)}
            downloader.prepare_filename.return_value=str(output)
            result=public_media.download_with_ytdlp("https://www.youtube.com/watch?v=test",folder)
        self.assertEqual(result,output)
        options=downloader_class.call_args.args[0]
        self.assertTrue(options["noplaylist"]);self.assertEqual(options["max_filesize"],1000000)
