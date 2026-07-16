from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient
from apps.orders.models import ContentOrder
from .models import Clip, PipelineRun, StageRun

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
