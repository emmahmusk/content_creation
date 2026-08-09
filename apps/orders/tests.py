from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from .models import ContentOrder, SourceAsset
from .forms import SourceAssetForm

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
