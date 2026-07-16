from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient
from apps.orders.models import ContentOrder
from .models import Deliverable

class DeliverableAccessTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="safe-test-pass")
        self.other = User.objects.create_user("viewer", password="safe-test-pass")
        order = ContentOrder.objects.create(customer=self.owner, title="Interview", content_brief="Repurpose it")
        Deliverable.objects.create(order=order, kind="newsletter", title="Article", content="Draft", created_by=self.owner)

    def test_customer_only_sees_own_deliverables(self):
        client = APIClient(); client.force_authenticate(self.other)
        response = client.get("/api/v1/deliverables/")
        self.assertEqual(response.data["count"], 0)

    def test_customer_cannot_create_deliverable(self):
        client = APIClient(); client.force_authenticate(self.owner)
        response = client.post("/api/v1/deliverables/", {})
        self.assertEqual(response.status_code, 403)
