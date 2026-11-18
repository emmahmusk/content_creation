import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.orders.models import ContentOrder, SourceAsset
from apps.processing import pipeline, tasks
from apps.processing.models import PipelineRun
from apps.processing.services import source_handoff


@override_settings(CLOUDINARY_CLOUD_NAME="test", CLOUDINARY_API_KEY="public-key", CLOUDINARY_API_SECRET="private-secret",
                   CLOUDINARY_DIRECT_UPLOADS_ENABLED=True, PIPELINE_EXECUTION_MODE="celery")
class SourceHandoffTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("upload-owner")
        self.other = User.objects.create_user("upload-other")
        self.order = ContentOrder.objects.create(customer=self.user, title="Recording", content_brief="Find useful lessons")
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        self.client.force_login(self.user)
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        storage = override_settings(MEDIA_ROOT=self.root)
        storage.enable()
        self.addCleanup(storage.disable)

    def result(self, public_id="recast/source/uploads/test"):
        return {"public_id": public_id, "resource_type": "video", "type": "upload", "bytes": 9,
                "secure_url": f"https://res.cloudinary.com/test/video/upload/{public_id}.mp4", "duration": 60}

    def recording(self):
        return SimpleUploadedFile("recording.mp4", b"recording", content_type="video/mp4")

    def payload(self, **extra):
        return {"title": "Uploaded project", "content_brief": "A useful recording", "target_platforms": ["youtube"],
                "desired_clip_count": 1, "min_clip_seconds": 10, "max_clip_seconds": 30,
                "broll_mode": "none", "broll_intensity": "moderate", "rights_confirmed": True, **extra}

    def test_signing_endpoint_requires_login_and_rights_and_keeps_secret_server_side(self):
        endpoint = reverse("orders:source-upload")
        self.client.logout()
        self.assertEqual(self.client.post(endpoint).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(endpoint, json.dumps({"filename": "recording.mp4", "size": 9}), content_type="application/json").status_code, 400)
        response = self.client.post(endpoint, json.dumps({"filename": "recording.mp4", "size": 9, "rights_confirmed": True}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("private-secret", response.content.decode())
        self.assertTrue(response.json()["params"]["public_id"].startswith(f"recast/source/incoming/{self.user.pk}/"))
        self.assertEqual(response.json()["chunk_bytes"], 6_000_000)

    def test_signing_rejects_empty_oversized_and_non_media_files(self):
        for filename, size in (("file.exe", 9), ("video.mp4", 0), ("video.mp4", 10**12)):
            with self.assertRaises(source_handoff.SourceHandoffError):
                source_handoff.issue_upload(self.user, filename, size)

    @patch("cloudinary.api.resource")
    def test_direct_token_is_bound_to_owner_and_verified_against_storage(self, resource):
        ticket = source_handoff.issue_upload(self.user, "recording.mp4", 9)
        resource.return_value = self.result(ticket["params"]["public_id"])
        metadata = source_handoff.verify_upload(ticket["token"], self.user)
        self.assertEqual(metadata["cloudinary_public_id"], ticket["params"]["public_id"])
        with self.assertRaises(source_handoff.SourceHandoffError):
            source_handoff.verify_upload(ticket["token"], self.other)
        self.assertEqual(resource.call_count, 1)
        with self.assertRaises(source_handoff.SourceHandoffError):
            source_handoff.verify_upload(ticket["token"] + "tampered", self.user)

    @patch("cloudinary.api.resource")
    def test_direct_upload_creates_cloud_only_source_before_pipeline_record(self, resource):
        ticket = source_handoff.issue_upload(self.user, "recording.mp4", 9)
        resource.return_value = self.result(ticket["params"]["public_id"])
        response = self.client.post(reverse("orders:create"), self.payload(cloudinary_upload_token=ticket["token"]))
        self.assertEqual(response.status_code, 302)
        asset = SourceAsset.objects.get(cloudinary_public_id=ticket["params"]["public_id"])
        self.assertFalse(asset.file)
        self.assertEqual(asset.original_filename, "recording.mp4")
        self.assertEqual(asset.duration_seconds, 60)
        self.assertEqual(asset.order.pipeline_runs.count(), 1)
        self.assertFalse(list(self.root.rglob("*.mp4")))
        replay = self.client.post(reverse("orders:create"), self.payload(cloudinary_upload_token=ticket["token"]))
        self.assertEqual(replay.status_code, 200)
        self.assertContains(replay, "already attached")
        self.assertEqual(SourceAsset.objects.count(), 1)

    @patch("cloudinary.api.resource", side_effect=RuntimeError("credential detail"))
    def test_unverified_upload_creates_no_project_or_job(self, resource):
        ticket = source_handoff.issue_upload(self.user, "recording.mp4", 9)
        response = self.client.post(reverse("orders:create"), self.payload(cloudinary_upload_token=ticket["token"]))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("credential detail", response.content.decode())
        self.assertEqual(ContentOrder.objects.count(), 1)
        self.assertEqual(PipelineRun.objects.count(), 0)

    @patch("cloudinary.uploader.upload")
    def test_api_file_upload_persists_cloud_metadata_without_local_file(self, upload):
        upload.return_value = self.result()
        response = self.api.post("/api/v1/assets/", {"order": self.order.pk, "file": self.recording()}, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        asset = self.order.source_assets.get()
        self.assertFalse(asset.file)
        self.assertEqual(asset.cloudinary_public_id, self.result()["public_id"])
        self.assertFalse(list(self.root.rglob("*.mp4")))

    @patch("cloudinary.uploader.upload", side_effect=RuntimeError("secret provider error"))
    def test_api_storage_failure_does_not_accept_source(self, upload):
        response = self.api.post("/api/v1/assets/", {"order": self.order.pk, "file": self.recording()}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.order.source_assets.exists())
        self.assertNotIn("secret provider error", str(response.data))

    @patch("cloudinary.uploader.upload")
    def test_browser_without_javascript_still_uploads_before_creating_job(self, upload):
        upload.return_value = self.result()
        response = self.client.post(reverse("orders:create"), self.payload(file=self.recording()))
        self.assertEqual(response.status_code, 302)
        asset = SourceAsset.objects.get(cloudinary_public_id=self.result()["public_id"])
        self.assertFalse(asset.file)
        self.assertEqual(asset.order.pipeline_runs.count(), 1)

    @override_settings(CLOUDINARY_API_SECRET="")
    def test_celery_upload_is_rejected_when_remote_storage_is_unconfigured(self):
        with self.assertRaisesMessage(source_handoff.SourceHandoffError, "Cloudinary must be configured"):
            source_handoff.upload_file(self.recording(), self.user.pk)

    @patch("cloudinary.uploader.upload")
    @patch("apps.processing.tasks.process_order.apply_async")
    def test_legacy_local_upload_is_transferred_before_dispatch(self, dispatch, upload):
        upload.return_value = self.result()
        asset = SourceAsset.objects.create(order=self.order, file=self.recording())
        old_path = Path(asset.file.path)
        run = PipelineRun.objects.create(order=self.order)
        def enqueue(**kwargs):
            asset.refresh_from_db()
            self.assertFalse(asset.file)
            self.assertTrue(asset.cloudinary_public_id)
        dispatch.side_effect = enqueue
        with self.captureOnCommitCallbacks(execute=True):
            tasks.dispatch_pipeline(run.pk)
        self.assertFalse(old_path.exists())
        dispatch.assert_called_once()

    @patch("cloudinary.uploader.upload", side_effect=RuntimeError("unavailable"))
    @patch("apps.processing.tasks.process_order.apply_async")
    def test_failed_transfer_never_dispatches_and_preserves_local_source(self, dispatch, upload):
        asset = SourceAsset.objects.create(order=self.order, file=self.recording())
        run = PipelineRun.objects.create(order=self.order)
        with self.assertRaises(source_handoff.SourceHandoffError):
            tasks.dispatch_pipeline(run.pk)
        dispatch.assert_not_called()
        asset.refresh_from_db()
        self.assertTrue(Path(asset.file.path).exists())

    @patch("apps.processing.pipeline.cloudinary_media.download_source")
    def test_worker_with_empty_disk_resolves_the_source_from_cloudinary(self, download):
        asset = SourceAsset.objects.create(order=self.order, cloudinary_public_id="recast/source/recording", original_filename="recording.mp4")
        worker = self.root / "worker"
        worker.mkdir()
        def restore(asset, destination):
            destination.write_bytes(b"recording")
            return destination
        download.side_effect = restore
        resolved = pipeline._source(self.order, worker, None)
        self.assertEqual(resolved.read_bytes(), b"recording")
        download.assert_called_once_with(asset, worker / "source-original.mp4")

    @patch("cloudinary.api.resource")
    def test_provider_verified_oversized_recording_is_rejected(self, resource):
        ticket = source_handoff.issue_upload(self.user, "recording.mp4", 9)
        resource.return_value = {**self.result(ticket["params"]["public_id"]), "bytes": 10**12}
        with self.assertRaises(source_handoff.SourceHandoffError):
            source_handoff.verify_upload(ticket["token"], self.user)

    def test_create_page_exposes_progress_and_direct_upload_endpoint(self):
        response = self.client.get(reverse("orders:create"))
        self.assertContains(response, "data-direct-upload-url")
        self.assertContains(response, "data-source-upload-progress")
        self.assertContains(response, "source-upload.js")

    @patch("cloudinary.uploader.upload")
    def test_api_replacement_only_discards_local_copy_after_cloud_upload_succeeds(self, upload):
        asset = SourceAsset.objects.create(order=self.order, file=self.recording())
        old_path = Path(asset.file.path)
        upload.return_value = self.result()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.api.patch(f"/api/v1/assets/{asset.pk}/", {"file": self.recording()}, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(old_path.exists())
        asset.refresh_from_db()
        self.assertFalse(asset.file)
        self.assertTrue(asset.cloudinary_public_id)

    @patch("cloudinary.uploader.upload", side_effect=RuntimeError("storage unavailable"))
    def test_failed_replacement_preserves_existing_cloud_original(self, upload):
        asset = SourceAsset.objects.create(order=self.order, cloudinary_public_id="recast/source/old")
        response = self.api.patch(f"/api/v1/assets/{asset.pk}/", {"file": self.recording()}, format="multipart")
        self.assertEqual(response.status_code, 400)
        asset.refresh_from_db()
        self.assertEqual(asset.cloudinary_public_id, "recast/source/old")

    @patch("apps.processing.services.source_handoff.remove_unreferenced_original")
    @patch("cloudinary.api.resources")
    def test_abandoned_cleanup_preserves_referenced_and_recent_sources(self, resources, remove):
        from datetime import timedelta
        from django.core.management import call_command
        from django.utils import timezone
        import io
        old = (timezone.now() - timedelta(days=2)).isoformat()
        SourceAsset.objects.create(order=self.order, cloudinary_public_id="recast/source/retained")
        resources.return_value = {"resources": [
            {"public_id": "recast/source/retained", "created_at": old},
            {"public_id": "recast/source/orphan", "created_at": old},
            {"public_id": "recast/exports/clip", "created_at": old},
            {"public_id": "recast/source/incoming/recent", "created_at": timezone.now().isoformat()},
        ]}
        call_command("cleanup_unclaimed_sources", delete=True, stdout=io.StringIO())
        remove.assert_called_once_with("recast/source/orphan")
