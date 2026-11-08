import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from .models import AfroStudioProject, StudioAsset
from .services.creative import CreativeSafetyError, enforce_originality
from .services.pipeline import analyze_project, generate_project


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
TEST_PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def audio_file(name="reference.wav"):
    return SimpleUploadedFile(name, b"RIFF-test-audio", content_type="audio/wav")


def direction_payload(story="Finding hope after a difficult season"):
    return {
        "story": story,
        "audience": "Young creators building a new life",
        "desired_mood": "Warm and triumphant",
        "genre": "AfroFusion",
        "lyrical_theme": "hope",
        "energy": "medium",
        "language": "english",
        "voice_profile": "warm",
        "originality_confirmed": "on",
    }


@override_settings(STORAGES=TEST_STORAGES, PASSWORD_HASHERS=TEST_PASSWORD_HASHERS)
class StudioViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="creator", password="test-pass-123")
        self.other = get_user_model().objects.create_user(username="other", password="test-pass-123")
        self.client.force_login(self.user)

    @patch("apps.music.views.dispatch_analysis")
    def test_upload_creates_owner_scoped_project_and_starts_analysis(self, dispatch):
        response = self.client.post(reverse("music:home"), {
            "title": "Sunrise study",
            "reference_audio": audio_file(),
            "source_rights_confirmed": "on",
            "analysis_only_confirmed": "on",
        })
        project = AfroStudioProject.objects.get()
        self.assertRedirects(response, reverse("music:detail", args=[project.id]))
        self.assertEqual(project.owner, self.user)
        self.assertEqual(project.original_filename, "reference.wav")
        dispatch.assert_called_once_with(project.id)

    @patch("apps.music.views.dispatch_analysis")
    def test_upload_requires_both_rights_confirmations(self, dispatch):
        response = self.client.post(reverse("music:home"), {
            "title": "Unsafe upload",
            "reference_audio": audio_file(),
            "source_rights_confirmed": "on",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AfroStudioProject.objects.exists())
        self.assertContains(response, "high-level musical analysis only")
        dispatch.assert_not_called()

    def test_project_is_private_to_its_owner(self):
        project = AfroStudioProject.objects.create(
            owner=self.other, title="Private session", reference_audio=audio_file(),
            source_rights_confirmed=True, analysis_only_confirmed=True,
        )
        response = self.client.get(reverse("music:detail", args=[project.id]))
        self.assertEqual(response.status_code, 404)

    @patch("apps.music.views.dispatch_generation")
    def test_direction_starts_original_generation(self, dispatch):
        project = AfroStudioProject.objects.create(
            owner=self.user, title="Direction", reference_audio=audio_file(),
            source_rights_confirmed=True, analysis_only_confirmed=True,
            status=AfroStudioProject.Status.DIRECTION,
            intelligence={"features": {"tempo_bpm": 104}},
        )
        response = self.client.post(reverse("music:direction", args=[project.id]), direction_payload())
        self.assertRedirects(response, reverse("music:detail", args=[project.id]))
        project.refresh_from_db()
        self.assertEqual(project.creative_direction["genre"], "AfroFusion")
        dispatch.assert_called_once_with(project.id)

    @patch("apps.music.views.dispatch_generation")
    def test_artist_imitation_request_is_rejected(self, dispatch):
        project = AfroStudioProject.objects.create(
            owner=self.user, title="Direction", reference_audio=audio_file(),
            source_rights_confirmed=True, analysis_only_confirmed=True,
            status=AfroStudioProject.Status.DIRECTION,
        )
        response = self.client.post(
            reverse("music:direction", args=[project.id]),
            direction_payload("Make this sound like a famous recording artist"),
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "not an artist", status_code=400)
        dispatch.assert_not_called()

    def test_review_exports_lyrics_and_structured_project(self):
        project = AfroStudioProject.objects.create(
            owner=self.user, title="Open Sky", reference_audio=audio_file(),
            source_rights_confirmed=True, analysis_only_confirmed=True,
            status=AfroStudioProject.Status.REVIEW, lyrics="[Chorus]\nWe rise",
            creative_plan={"title": "Open Sky"}, intelligence={"features": {}},
        )
        text_response = self.client.get(reverse("music:export", args=[project.id, "lyrics"]))
        json_response = self.client.get(reverse("music:export", args=[project.id, "json"]))
        self.assertEqual(text_response.content.decode(), "[Chorus]\nWe rise")
        self.assertIn("attachment", text_response["Content-Disposition"])
        self.assertEqual(json.loads(json_response.content)["title"], "Open Sky")


@override_settings(
    PIPELINE_ALLOW_MOCK_AI=True,
    GROQ_API_KEY="",
    PASSWORD_HASHERS=TEST_PASSWORD_HASHERS,
)
class StudioPipelineTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="producer", password="test-pass-123")
        self.project = AfroStudioProject.objects.create(
            owner=self.user, title="Pipeline", reference_audio=audio_file(),
            source_rights_confirmed=True, analysis_only_confirmed=True,
        )

    @patch("apps.music.services.pipeline.analyze_audio")
    def test_analysis_persists_report_and_opens_direction(self, analyze):
        analyze.return_value = (
            {"duration_seconds": 180, "bitrate_kbps": 320},
            {"tempo_bpm": 104, "tempo_confidence": .7, "groove": "balanced", "mood": "warm", "complexity": "focused"},
        )
        analyze_project(self.project.id)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, AfroStudioProject.Status.DIRECTION)
        self.assertEqual(self.project.progress, 100)
        self.assertIn("report", self.project.intelligence)

    def test_generation_creates_editable_assets(self):
        self.project.status = AfroStudioProject.Status.DIRECTION
        self.project.intelligence = {"features": {"tempo_bpm": 104}}
        self.project.creative_direction = {
            "story": "new beginnings", "audience": "builders", "genre": "AfroFusion",
            "language": "english", "voice_profile": "warm",
        }
        self.project.save()
        generate_project(self.project.id)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, AfroStudioProject.Status.REVIEW)
        self.assertTrue(self.project.lyrics)
        self.assertEqual(
            set(self.project.assets.values_list("kind", flat=True)),
            {StudioAsset.Kind.LYRICS, StudioAsset.Kind.PROJECT_JSON, StudioAsset.Kind.MELODY_JSON},
        )

    def test_originality_guard_rejects_clone_requests(self):
        with self.assertRaises(CreativeSafetyError):
            enforce_originality({"story": "Clone the voice of a celebrity"})


@override_settings(PASSWORD_HASHERS=TEST_PASSWORD_HASHERS)
class StudioApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="api-user", password="test-pass-123")
        self.other = get_user_model().objects.create_user(username="api-other", password="test-pass-123")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_api_list_never_leaks_other_users_projects(self):
        own = AfroStudioProject.objects.create(
            owner=self.user, title="Mine", reference_audio=audio_file("mine.wav"),
            source_rights_confirmed=True, analysis_only_confirmed=True,
        )
        AfroStudioProject.objects.create(
            owner=self.other, title="Theirs", reference_audio=audio_file("theirs.wav"),
            source_rights_confirmed=True, analysis_only_confirmed=True,
        )
        response = self.client.get(reverse("v1:music-project-list"))
        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.data["results"]]
        self.assertEqual(ids, [str(own.id)])

    @patch("apps.music.api.dispatch_analysis")
    def test_api_upload_validates_rights_and_dispatches(self, dispatch):
        response = self.client.post(reverse("v1:music-project-list"), {
            "title": "API session", "reference_audio": audio_file(),
            "source_rights_confirmed": True, "analysis_only_confirmed": True,
        }, format="multipart")
        self.assertEqual(response.status_code, 201)
        project = AfroStudioProject.objects.get(title="API session")
        dispatch.assert_called_once_with(project.id)

    @patch("apps.music.api.dispatch_generation")
    def test_api_direction_is_validated_and_starts_generation(self, dispatch):
        project = AfroStudioProject.objects.create(
            owner=self.user, title="API direction", reference_audio=audio_file(),
            source_rights_confirmed=True, analysis_only_confirmed=True,
            status=AfroStudioProject.Status.DIRECTION,
        )
        payload = direction_payload()
        payload["originality_confirmed"] = True
        response = self.client.post(reverse("v1:music-project-direction", args=[project.id]), payload, format="json")
        self.assertEqual(response.status_code, 202)
        project.refresh_from_db()
        self.assertEqual(project.creative_direction["language"], "english")
        dispatch.assert_called_once_with(project.id)

    def test_api_lyrics_update_stays_owner_scoped(self):
        project = AfroStudioProject.objects.create(
            owner=self.user, title="API lyrics", reference_audio=audio_file(),
            source_rights_confirmed=True, analysis_only_confirmed=True,
            status=AfroStudioProject.Status.REVIEW, lyrics="First draft",
        )
        response = self.client.patch(
            reverse("v1:music-project-lyrics", args=[project.id]),
            {"lyrics": "[Chorus]\nA stronger line"}, format="json",
        )
        self.assertEqual(response.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.lyrics, "[Chorus]\nA stronger line")
        self.assertEqual(project.assets.get(kind=StudioAsset.Kind.LYRICS).text_content, project.lyrics)
