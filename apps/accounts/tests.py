from django.contrib.auth.models import User
from django.test import TestCase

class CustomerProfileTests(TestCase):
    def test_profile_is_created_with_user(self):
        user = User.objects.create_user("creator", password="safe-test-pass")
        self.assertEqual(user.customer_profile.audience_type, "other")
