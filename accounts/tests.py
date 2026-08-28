from django.test import TestCase
from django.urls import reverse
from .models import User
from unittest.mock import patch


class PatientNavigationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.patient = User.objects.create_user(username="patient")
        cls.admin = User.objects.create_user(
            username="administrator", role=User.Role.ADMIN, is_staff=True
        )

    def test_guest_navigation_and_login_button(self):
        response = self.client.get(reverse("home"))
        nav = response.content.decode().split("<nav", 1)[1].split("</nav>", 1)[0]
        for label in ("Home", "Doctors", "Admin"):
            self.assertIn(f">{label}</a>", nav)
        for label in ("Patients", "Appointments", "My Dashboard", "Logout"):
            self.assertNotIn(label, nav)
        self.assertContains(response, "Patient Login")
        self.assertContains(response, 'href="/doctors/"')

    def test_guest_dashboard_and_admin_require_login(self):
        for name, login in (("patient_dashboard", "login"), ("admin:index", "admin:login")):
            url = reverse(name)
            self.assertRedirects(self.client.get(url), f"{reverse(login)}?next={url}")

    def test_patient_has_dashboard_options_but_no_admin_link(self):
        self.client.force_login(self.patient)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "My Dashboard")
        self.assertContains(response, "Signed in as patient")
        self.assertContains(response, "Logout")
        self.assertNotContains(response, "Patient Login")
        self.assertNotContains(response, 'href="/admin/"')
        dashboard = self.client.get(reverse("patient_dashboard"))
        for label in ("My Appointments", "My Prescriptions", "Lab Reports", "Support Ticket"):
            self.assertContains(dashboard, label)
        self.assertRedirects(
            self.client.get(reverse("admin:index")),
            f"{reverse('admin:login')}?next={reverse('admin:index')}",
        )

    def test_admin_session_is_visible_and_not_a_patient_dashboard(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Signed in as administrator")
        self.assertNotContains(response, "Patient Login")
        self.assertEqual(self.client.get(reverse("patient_dashboard")).status_code, 403)

    def test_logout_requires_post_and_restores_guest_navigation(self):
        self.client.force_login(self.patient)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("logout")), reverse("home"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.test_guest_navigation_and_login_button()

    def test_superuser_with_default_role_does_not_land_on_patient_dashboard(self):
        superuser = User.objects.create_user(username="root", is_staff=True, is_superuser=True)
        with patch("accounts.views.authenticate", return_value=superuser):
            response = self.client.post(reverse("login"), {"username": "root", "password": "test"})
        self.assertRedirects(response, reverse("admin:index"))

    def test_admin_role_without_staff_access_lands_on_appointments(self):
        self.admin.is_staff = False
        self.admin.save()
        with patch("accounts.views.authenticate", return_value=self.admin):
            response = self.client.post(reverse("login"), {"username": self.admin.username, "password": "test"})
        self.assertRedirects(response, reverse("appointment_list"))
