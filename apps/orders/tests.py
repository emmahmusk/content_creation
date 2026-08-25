from datetime import timedelta
from tempfile import TemporaryDirectory
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from .models import ContentOrder, SourceAsset
from .forms import SourceAssetForm
from apps.deliverables.models import Deliverable
from apps.processing.models import Clip, PipelineRun, StageRun, TranscriptSegment

class ContentOrderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("customer", password="safe-test-pass")
        self.other = User.objects.create_user("other", password="safe-test-pass")
        self.order = ContentOrder.objects.create(customer=self.user, title="Weekly show", content_brief="Create a practical content package.")

    def test_order_gets_24_hour_deadline(self):
        expected = self.order.created_at + timedelta(hours=24)
        self.assertLess(abs((self.order.due_at - expected).total_seconds()), 5)

    def test_customer_cannot_view_another_order(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse("orders:detail", args=[self.order.pk]))
        self.assertEqual(response.status_code, 404)

    def test_api_is_customer_scoped(self):
        ContentOrder.objects.create(customer=self.other, title="Hidden", content_brief="Private")
        client = APIClient(); client.force_authenticate(self.user)
        response = client.get("/api/v1/orders/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_source_requires_file_or_url(self):
        asset = SourceAsset(order=self.order)
        with self.assertRaisesMessage(Exception, "Upload a file or provide"):
            asset.full_clean()

    def test_public_url_requires_rights_confirmation(self):
        form=SourceAssetForm(data={"external_url":"https://www.youtube.com/watch?v=example"})
        self.assertFalse(form.is_valid())
        self.assertIn("rights_confirmed",form.errors)
        form=SourceAssetForm(data={"external_url":"https://www.youtube.com/watch?v=example","rights_confirmed":True})
        self.assertTrue(form.is_valid(),form.errors)

    def test_create_page_uses_accessible_platform_cards(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("orders:create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="platform-choice-grid"')
        self.assertContains(response, 'class="enhancement-choice-ui"')
        self.assertContains(response, 'name="target_platforms"', count=5)
        self.assertContains(response, 'type="checkbox"', count=7)
        self.assertContains(response, 'name="broll_mode"', count=4)
        self.assertContains(response, "B-roll generation starts only for moments your team approves")

    def test_dashboard_prioritizes_ranked_moments_for_human_review(self):
        PipelineRun.objects.create(
            order=self.order,
            status=PipelineRun.Status.REVIEW,
            current_stage="recommendations_ready",
            progress=72,
        )
        Clip.objects.create(
            order=self.order,
            rank=1,
            title="Strong founder moment",
            hook="A precise opening",
            caption="A useful caption",
            start_ms=1000,
            end_ms=31000,
            score=9.1,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("orders:dashboard"))

        self.assertContains(response, "CLIPPING COMMAND CENTER")
        self.assertContains(response, "Review 1 ranked moment")
        self.assertContains(response, "1 high-potential signal")
        self.assertContains(response, "Engine activity")

    def test_dashboard_orders_newest_first_but_numbers_by_creation_sequence(self):
        ContentOrder.objects.filter(pk=self.order.pk).update(
            created_at=timezone.now() - timedelta(days=3)
        )
        middle = ContentOrder.objects.create(
            customer=self.user,
            title="Middle project",
            content_brief="The second project.",
        )
        ContentOrder.objects.filter(pk=middle.pk).update(
            created_at=timezone.now() - timedelta(days=2)
        )
        newest = ContentOrder.objects.create(
            customer=self.user,
            title="Newest project",
            content_brief="The latest project.",
        )
        ContentOrder.objects.filter(pk=newest.pk).update(
            created_at=timezone.now() - timedelta(days=1)
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("orders:dashboard"))

        projects = response.context["orders"]
        self.assertEqual(
            [project.title for project in projects],
            ["Newest project", "Middle project", "Weekly show"],
        )
        self.assertEqual(
            [project.project_number for project in projects],
            [3, 2, 1],
        )
        html = response.content.decode()
        self.assertLess(html.index("PROJECT 03"), html.index("PROJECT 02"))
        self.assertLess(html.index("PROJECT 02"), html.index("PROJECT 01"))

    def test_running_render_shows_background_companion(self):
        PipelineRun.objects.create(
            order=self.order,
            status=PipelineRun.Status.RUNNING,
            current_stage="rendering_exports",
            progress=50,
        )
        Clip.objects.create(
            order=self.order,
            rank=1,
            title="A strong moment",
            hook="Listen",
            caption="Caption",
            start_ms=0,
            end_ms=1000,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("orders:detail", args=[self.order.pk]))

        self.assertContains(response, 'data-stage="rendering_exports"')
        self.assertContains(response, "Your exports are cooking.")
        self.assertContains(response, "You can leave this page, close the tab")
        self.assertContains(response, "Back to workspace")
        self.assertContains(response, "Your choices are locked in.")

    def edit_payload(self, **overrides):
        payload = {
            "title": self.order.title,
            "content_brief": self.order.content_brief,
            "importance_definition": "Prioritize practical founder advice.",
            "moments_to_avoid": "Skip sponsor messages.",
            "desired_clip_count": 5,
            "min_clip_seconds": 20,
            "max_clip_seconds": 60,
            "brand_voice": "Clear and direct.",
            "target_platforms": ["linkedin", "youtube"],
            "broll_mode": ContentOrder.BrollMode.NONE,
            "broll_intensity": ContentOrder.BrollIntensity.MODERATE,
        }
        payload.update(overrides)
        return payload

    def add_generated_analysis(self, status=PipelineRun.Status.REVIEW):
        run = PipelineRun.objects.create(
            order=self.order, status=status, current_stage="awaiting_approval", progress=100
        )
        TranscriptSegment.objects.create(order=self.order, start_ms=0, end_ms=1000, text="A useful moment")
        Clip.objects.create(
            order=self.order,
            rank=1,
            title="Moment",
            hook="Listen",
            caption="Caption",
            start_ms=0,
            end_ms=1000,
        )
        Deliverable.objects.create(
            order=self.order,
            kind=Deliverable.Kind.CLIP_PLAN,
            title="Clip plan",
            content="Old plan",
            created_by=self.user,
        )
        return run

    def test_completed_analysis_can_be_edited_and_prepared_for_restart(self):
        old_run = self.add_generated_analysis()
        SourceAsset.objects.create(
            order=self.order,
            external_url="https://example.com/source.mp4",
            rights_confirmed=True,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("orders:edit", args=[self.order.pk]),
            self.edit_payload(importance_definition="Choose counterintuitive, actionable lessons."),
        )

        self.assertRedirects(response, reverse("orders:detail", args=[self.order.pk]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.importance_definition, "Choose counterintuitive, actionable lessons.")
        self.assertEqual(self.order.status, ContentOrder.Status.SUBMITTED)
        self.assertEqual(self.order.pipeline_runs.count(), 2)
        self.assertEqual(self.order.pipeline_runs.first().status, PipelineRun.Status.QUEUED)
        self.assertEqual(PipelineRun.objects.get(pk=old_run.pk).status, PipelineRun.Status.REVIEW)
        self.assertFalse(self.order.clips.exists())
        self.assertFalse(self.order.transcript_segments.exists())
        self.assertFalse(self.order.deliverables.exists())
        self.assertEqual(self.order.source_assets.count(), 1)

    def test_title_only_edit_preserves_completed_analysis(self):
        self.order.importance_definition = "Prioritize practical founder advice."
        self.order.moments_to_avoid = "Skip sponsor messages."
        self.order.brand_voice = "Clear and direct."
        self.order.target_platforms = ["linkedin", "youtube"]
        self.order.save()
        self.add_generated_analysis()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("orders:edit", args=[self.order.pk]),
            self.edit_payload(title="A clearer project title"),
        )

        self.assertRedirects(response, reverse("orders:detail", args=[self.order.pk]))
        self.assertEqual(self.order.pipeline_runs.count(), 1)
        self.assertEqual(self.order.clips.count(), 1)
        self.assertEqual(self.order.deliverables.count(), 1)

    def test_running_analysis_requires_stop_before_editing(self):
        run = PipelineRun.objects.create(
            order=self.order, status=PipelineRun.Status.RUNNING, current_stage="strategy", progress=30
        )
        stage = StageRun.objects.create(
            pipeline=run, name="strategy", status=StageRun.Status.RUNNING
        )
        self.client.force_login(self.user)

        page = self.client.get(reverse("orders:edit", args=[self.order.pk]))
        self.assertContains(page, "Stop analysis and edit")
        self.assertNotContains(page, "Save project changes")

        stopped = self.client.post(reverse("orders:stop-analysis", args=[self.order.pk]))
        self.assertRedirects(stopped, reverse("orders:edit", args=[self.order.pk]))
        run.refresh_from_db(); stage.refresh_from_db(); self.order.refresh_from_db()
        self.assertEqual(run.status, PipelineRun.Status.CANCELLED)
        self.assertEqual(stage.status, StageRun.Status.SKIPPED)
        self.assertEqual(self.order.status, ContentOrder.Status.REVISION)

        saved = self.client.post(
            reverse("orders:edit", args=[self.order.pk]),
            self.edit_payload(content_brief="A sharper brief for the restarted analysis."),
        )
        self.assertRedirects(saved, reverse("orders:detail", args=[self.order.pk]))
        self.assertEqual(self.order.pipeline_runs.count(), 2)
        self.assertEqual(self.order.pipeline_runs.first().status, PipelineRun.Status.QUEUED)

    def test_customer_cannot_stop_another_customers_analysis(self):
        PipelineRun.objects.create(order=self.order, status=PipelineRun.Status.RUNNING)
        self.client.force_login(self.other)
        response = self.client.post(reverse("orders:stop-analysis", args=[self.order.pk]))
        self.assertEqual(response.status_code, 404)

    def test_blocked_youtube_source_can_be_replaced_without_losing_the_project(self):
        SourceAsset.objects.create(
            order=self.order,
            external_url="https://www.youtube.com/watch?v=blocked",
            rights_confirmed=True,
        )
        PipelineRun.objects.create(
            order=self.order,
            status=PipelineRun.Status.FAILED,
            current_stage="ingest",
            error="The public video could not be imported: YouTube could not verify this server.",
        )
        self.client.force_login(self.user)

        page = self.client.get(reverse("orders:detail", args=[self.order.pk]))
        self.assertContains(page, "Continue with the original file")
        self.assertContains(page, reverse("orders:replace-source", args=[self.order.pk]))

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse("orders:replace-source", args=[self.order.pk]),
                {"file": ContentFile(b"video-data", name="authorized-source.mp4")},
            )

            self.assertRedirects(response, reverse("orders:detail", args=[self.order.pk]))
            asset = self.order.source_assets.get()
            self.assertEqual(asset.external_url, "")
            self.assertEqual(asset.original_filename, "authorized-source.mp4")
            self.assertTrue(bool(asset.file))

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, ContentOrder.Status.SUBMITTED)
        self.assertEqual(self.order.pipeline_runs.count(), 2)
        self.assertEqual(self.order.pipeline_runs.first().status, PipelineRun.Status.QUEUED)

    def test_customer_cannot_replace_another_customers_source(self):
        SourceAsset.objects.create(
            order=self.order,
            external_url="https://www.youtube.com/watch?v=blocked",
            rights_confirmed=True,
        )
        self.client.force_login(self.other)
        response = self.client.post(
            reverse("orders:replace-source", args=[self.order.pk]),
            {"file": ContentFile(b"video-data", name="source.mp4")},
        )
        self.assertEqual(response.status_code, 404)

    def test_broll_preference_change_preserves_unrendered_analysis(self):
        self.order.importance_definition = "Prioritize practical founder advice."
        self.order.moments_to_avoid = "Skip sponsor messages."
        self.order.brand_voice = "Clear and direct."
        self.order.target_platforms = ["linkedin", "youtube"]
        self.order.save()
        self.add_generated_analysis()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("orders:edit", args=[self.order.pk]),
            self.edit_payload(
                broll_mode=ContentOrder.BrollMode.AI_GENERATED,
                broll_intensity=ContentOrder.BrollIntensity.MINIMAL,
            ),
        )

        self.assertRedirects(response, reverse("orders:detail", args=[self.order.pk]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.broll_mode, ContentOrder.BrollMode.AI_GENERATED)
        self.assertEqual(self.order.pipeline_runs.count(), 1)
        self.assertEqual(self.order.clips.count(), 1)
        self.assertEqual(self.order.transcript_segments.count(), 1)

    def test_broll_preference_change_reopens_only_rendered_clips(self):
        self.order.importance_definition = "Prioritize practical founder advice."
        self.order.moments_to_avoid = "Skip sponsor messages."
        self.order.brand_voice = "Clear and direct."
        self.order.target_platforms = ["linkedin", "youtube"]
        self.order.save()
        self.add_generated_analysis()
        clip = self.order.clips.get()
        clip.status = Clip.Status.RENDERED
        clip.video.save("rendered.mp4", ContentFile(b"rendered"), save=False)
        clip.save()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("orders:edit", args=[self.order.pk]),
            self.edit_payload(broll_mode=ContentOrder.BrollMode.AI_SELECTED),
        )

        self.assertRedirects(response, reverse("orders:detail", args=[self.order.pk]))
        clip.refresh_from_db()
        self.assertEqual(clip.status, Clip.Status.APPROVED)
        self.assertFalse(bool(clip.video))
        self.assertEqual(self.order.clips.count(), 1)
        self.assertEqual(self.order.transcript_segments.count(), 1)
        self.assertEqual(self.order.pipeline_runs.count(), 2)
