import io
import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.orders.models import ContentOrder, SourceAsset
from apps.credits.models import CreditLedgerEntry
from .models import Clip, PipelineRun
from . import pipeline
from .services import youtube_sources


URL = "https://www.youtube.com/watch?v=YKDYhOq5wAY"


@override_settings(YOUTUBE_IMPORTS_ENABLED=True, MEDIA_PIPELINE_PRIMARY="local", CLOUDINARY_FALLBACK_ENABLED=False)
class YouTubeWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("youtube-workflow")
        self.order = ContentOrder.objects.create(customer=self.user, title="Test video", content_brief="Useful lessons", desired_clip_count=1)
        self.asset = SourceAsset.objects.create(order=self.order, external_url=URL, rights_confirmed=True)
        self.run = PipelineRun.objects.create(order=self.order)
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        settings_override = override_settings(MEDIA_ROOT=self.root)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.work = self.root / "test-work"
        self.work.mkdir()

    def retain(self):
        self.asset.imported_file.save("youtube-test.mkv", ContentFile(b"original"), save=False)
        self.asset.youtube_imported_at = timezone.now()
        self.asset.save()
        return Path(self.asset.imported_file.path)

    @patch("apps.processing.services.youtube_sources.youtube.import_video")
    def test_download_is_reused_between_analysis_and_render(self, importer):
        downloaded = self.work / "youtube-source.mkv"
        downloaded.write_bytes(b"original")
        importer.return_value = downloaded
        youtube_sources.source(self.asset, self.work)
        self.asset.refresh_from_db()
        self.assertTrue(self.asset.youtube_imported_at)
        cached = youtube_sources.source(self.asset, self.work)
        self.assertEqual(cached.read_bytes(), b"original")
        self.assertEqual(importer.call_count, 1)

    def test_cleanup_removes_managed_original_but_preserves_uploaded_file_and_clips(self):
        original = self.retain()
        self.asset.file.save("user-upload.mp4", ContentFile(b"user upload"))
        upload = Path(self.asset.file.path)
        clip = Clip.objects.create(order=self.order, rank=1, start_ms=0, end_ms=10000)
        clip.video.save("clip.mp4", ContentFile(b"rendered"))
        export = Path(clip.video.path)
        self.assertTrue(youtube_sources.discard(self.asset))
        self.assertFalse(original.exists())
        self.assertTrue(upload.exists())
        self.assertTrue(export.exists())
        self.asset.refresh_from_db()
        self.assertFalse(self.asset.imported_file)
        self.assertIsNone(self.asset.youtube_imported_at)

    @patch("apps.processing.services.youtube_sources.cloudinary_media.delete_source")
    def test_cleanup_removes_remote_original_and_dependent_previews(self, delete):
        self.retain()
        self.asset.cloudinary_public_id = "recast/source/original"
        self.asset.save()
        clip = Clip.objects.create(order=self.order, rank=1, start_ms=0, end_ms=10000, preview_url="https://example.test/preview")
        self.assertTrue(youtube_sources.discard(self.asset))
        delete.assert_called_once_with(self.asset)
        clip.refresh_from_db()
        self.assertEqual(clip.preview_url, "")

    @patch("apps.processing.services.youtube_sources.cloudinary_media.delete_source", side_effect=RuntimeError("failed"))
    def test_failed_remote_cleanup_keeps_marker_for_retry(self, delete):
        original = self.retain()
        self.asset.cloudinary_public_id = "recast/source/original"
        self.asset.save()
        self.assertFalse(youtube_sources.discard(self.asset))
        self.asset.refresh_from_db()
        self.assertIsNotNone(self.asset.youtube_imported_at)
        self.assertFalse(original.exists())

    def test_cleanup_waits_for_running_job(self):
        original = self.retain()
        self.run.status = PipelineRun.Status.RUNNING
        self.run.save()
        self.assertFalse(youtube_sources.discard(self.asset))
        self.assertTrue(original.exists())

    def test_expired_original_is_removed_by_cleanup_command(self):
        original = self.retain()
        self.asset.youtube_imported_at = timezone.now() - timedelta(hours=25)
        self.asset.save()
        call_command("cleanup_youtube_sources", stdout=io.StringIO())
        self.assertFalse(original.exists())

    @override_settings(PIPELINE_REQUIRE_APPROVAL=True, PIPELINE_ANALYSIS_ONLY=False, AI_PROVIDER="groq")
    @patch("apps.processing.pipeline.groq_provider.plan_package")
    @patch("apps.processing.pipeline.groq_provider.transcribe")
    @patch("apps.processing.pipeline.media.extract_audio")
    @patch("apps.processing.pipeline.media.probe")
    def test_analysis_retains_original_until_approved_clips_have_been_rendered(self, probe, audio, transcribe, plan):
        original = self.retain()
        probe.return_value = {"format": {"duration": "60"}}
        transcribe.return_value = [{"start_ms": 0, "end_ms": 15000, "text": "A useful lesson."}]
        plan.return_value = {"clips": [{"title": "Lesson", "start_ms": 0, "end_ms": 15000}]}
        CreditLedgerEntry.objects.create(user=self.user, amount=10, entry_type="gift", description="Test credits")
        pipeline.execute_pipeline(self.run.pk)
        self.run.refresh_from_db()
        self.assertEqual(self.run.current_stage, "awaiting_approval")
        self.assertTrue(original.exists())
        self.assertFalse((self.root / "work" / str(self.run.pk)).exists())
        clip = self.order.clips.get()
        clip.status = Clip.Status.APPROVED
        clip.save()
        def render(order, source, work, *args, **kwargs):
            self.assertTrue(Path(source).exists())
            clip.status = Clip.Status.RENDERED
            clip.video.save("completed.mp4", ContentFile(b"export"), save=False)
            clip.save()
            return 1
        with patch("apps.processing.pipeline._render_clip_files", side_effect=render):
            pipeline.render_existing_clips(self.run.pk)
        self.assertFalse(original.exists())
        clip.refresh_from_db()
        self.assertTrue(Path(clip.video.path).exists())

    @patch("apps.processing.pipeline._render_clip_files", side_effect=RuntimeError("render failed"))
    def test_failed_render_keeps_original_for_retry_but_clears_scratch_files(self, render):
        original = self.retain()
        Clip.objects.create(order=self.order, rank=1, start_ms=0, end_ms=10000, status=Clip.Status.APPROVED)
        CreditLedgerEntry.objects.create(user=self.user, amount=10, entry_type="gift", description="Test credits")
        with self.assertRaisesMessage(RuntimeError, "render failed"):
            pipeline.render_existing_clips(self.run.pk)
        self.assertTrue(original.exists())
        self.assertFalse((self.root / "work" / f"{self.run.pk}-exports").exists())

    @patch("apps.orders.views.generate_json")
    @patch("apps.orders.views.youtube.metadata")
    def test_url_alone_can_generate_editable_brief_fields(self, metadata, generate):
        metadata.return_value = {"title": "Source title", "description": "Useful video context", "duration": 60}
        generate.return_value = {"title": "Draft title", "content_brief": "Draft brief", "importance_definition": "Look for lessons", "moments_to_avoid": "Skip repetition", "brand_voice": "Clear", "unknown": "discard"}
        self.client.force_login(self.user)
        response = self.client.post(reverse("orders:suggest-clipping-brief"), data=json.dumps({"external_url": URL, "rights_confirmed": True}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["suggestions"]["title"], "Draft title")
        self.assertNotIn("unknown", response.json()["suggestions"])
        self.assertEqual(response.json()["based_on"], "youtube_metadata")
        self.assertIn("Source title", generate.call_args.args[1])

    @patch("apps.orders.views.youtube.metadata")
    def test_metadata_needs_rights_confirmation_and_login(self, metadata):
        endpoint = reverse("orders:suggest-clipping-brief")
        self.assertEqual(self.client.post(endpoint).status_code, 302)
        self.client.force_login(self.user)
        response = self.client.post(endpoint, data=json.dumps({"external_url": URL}), content_type="application/json")
        self.assertEqual(response.status_code, 400)
        metadata.assert_not_called()

    def test_create_page_places_suggestions_next_to_source(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("orders:create"))
        body = response.content.decode()
        self.assertLess(body.index("data-brief-suggest"), body.index("CLIPPING BRIEF"))
        self.assertContains(response, "remove the downloaded original")
