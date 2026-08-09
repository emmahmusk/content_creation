from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient
from apps.orders.models import ContentOrder
from .models import Clip, PipelineRun, StageRun
from .services import openai_poc
from unittest.mock import Mock, patch
from django.test import override_settings
from pathlib import Path
from tempfile import TemporaryDirectory

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
