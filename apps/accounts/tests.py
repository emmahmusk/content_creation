from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .forms import RegistrationForm
from .models import SocialHandle

class CustomerProfileTests(TestCase):
    def test_profile_is_created_with_user(self):
        user = User.objects.create_user("creator", password="safe-test-pass")
        self.assertEqual(user.customer_profile.audience_type, "other")

    def test_registration_can_capture_an_initial_social_handle(self):
        form=RegistrationForm(data={"username":"new-creator","email":"creator@example.com","organization":"Studio","audience_type":"youtube","social_platform":"youtube","social_handle":"@creator","password1":"safe-test-pass-234","password2":"safe-test-pass-234"})
        self.assertTrue(form.is_valid(),form.errors)
        user=form.save()
        self.assertEqual(user.social_handles.get().handle,"@creator")

    def test_social_profile_page_requires_login(self):
        response=self.client.get(reverse("profile"))
        self.assertEqual(response.status_code,302)

    def test_social_handle_api_is_scoped_and_supports_crud(self):
        owner=User.objects.create_user("owner",password="safe-test-pass")
        other=User.objects.create_user("other",password="safe-test-pass")
        SocialHandle.objects.create(user=other,platform="x",handle="@hidden")
        client=APIClient();client.force_authenticate(owner)
        created=client.post("/api/v1/social-handles/",{"platform":"youtube","handle":"@owner"},format="json")
        self.assertEqual(created.status_code,201)
        item_id=created.data["id"]
        self.assertEqual(client.get("/api/v1/social-handles/").data["count"],1)
        updated=client.patch(f"/api/v1/social-handles/{item_id}/",{"handle":"@updated"},format="json")
        self.assertEqual(updated.data["handle"],"@updated")
        self.assertEqual(client.delete(f"/api/v1/social-handles/{item_id}/").status_code,204)
