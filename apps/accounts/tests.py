from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .models import SocialHandle

class CustomerProfileTests(TestCase):
    def test_profile_is_created_with_user(self):
        user = User.objects.create_user("creator", password="safe-test-pass")
        self.assertEqual(user.customer_profile.audience_type, "other")

    def registration_payload(self, username="new-creator"):
        return {
            "username":username,"email":"creator@example.com","organization":"Studio","audience_type":"clipping_agency",
            "password1":"safe-test-pass-234","password2":"safe-test-pass-234",
            "social-TOTAL_FORMS":"2","social-INITIAL_FORMS":"0","social-MIN_NUM_FORMS":"0","social-MAX_NUM_FORMS":"7",
            "social-0-platform":"youtube","social-0-handle":"@creator",
            "social-1-platform":"instagram","social-1-handle":"@creator.ig",
        }

    def test_registration_captures_multiple_social_profiles_end_to_end(self):
        response=self.client.post(reverse("register"),self.registration_payload())
        self.assertEqual(response.status_code,302)
        user=User.objects.get(username="new-creator")
        self.assertEqual(list(user.social_handles.values_list("platform","handle")),[("instagram","@creator.ig"),("youtube","@creator")])
        self.assertEqual(str(self.client.session.get("_auth_user_id")),str(user.pk))

    def test_registration_rejects_duplicate_social_platforms_atomically(self):
        payload=self.registration_payload("duplicate-platform")
        payload["social-1-platform"]="youtube"
        response=self.client.post(reverse("register"),payload)
        self.assertEqual(response.status_code,200)
        self.assertContains(response,"Choose each social platform only once.")
        self.assertFalse(User.objects.filter(username="duplicate-platform").exists())

    def test_registration_requires_a_handle_for_each_selected_platform(self):
        payload=self.registration_payload("missing-handle")
        payload["social-1-handle"]=""
        response=self.client.post(reverse("register"),payload)
        self.assertEqual(response.status_code,200)
        self.assertContains(response,"This field is required.")
        self.assertFalse(User.objects.filter(username="missing-handle").exists())

    def test_registration_allows_social_profiles_to_be_skipped(self):
        payload=self.registration_payload("no-socials")
        payload.update({"social-TOTAL_FORMS":"1","social-0-platform":"","social-0-handle":""})
        payload.pop("social-1-platform");payload.pop("social-1-handle")
        response=self.client.post(reverse("register"),payload)
        self.assertEqual(response.status_code,302)
        self.assertFalse(User.objects.get(username="no-socials").social_handles.exists())

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
