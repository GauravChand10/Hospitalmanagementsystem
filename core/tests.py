from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from datetime import time
from departments.models import Department
from doctors.models import Doctor, DoctorAvailability
from unittest.mock import patch
from core.templatetags.assets import versioned_static
from core.models import AmbulanceRequest


class HomePageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department = Department.objects.create(name="General Medicine")
        cls.doctor = Doctor.objects.create(first_name="Demo", last_name="Doctor", department=cls.department,
            specialization="General practice", phone="123", email="demo@example.com")
        DoctorAvailability.objects.create(doctor=cls.doctor, weekday=0, start_time=time(9), end_time=time(17))

    @override_settings(APPOINTMENT_FEE_NPR="500.00")
    def test_home_shows_real_doctors_hours_and_sandbox_fee(self):
        response = self.client.get(reverse("home"))
        for text in ("Dr. Demo Doctor", "General Medicine", "General practice", "Monday", "09:00", "17:00", "NPR 500.00", "sandbox only"):
            self.assertContains(response, text)
        self.assertContains(response, f'href="{reverse("doctor_detail", args=[self.doctor.pk])}"')
        self.assertNotContains(response, "No doctors available")

    def test_public_home_omits_internal_record_totals_and_edit_controls(self):
        response = self.client.get(reverse("home"))
        self.assertNotIn("patient_count", response.context)
        self.assertNotIn("appointment_count", response.context)
        for name in ("doctor_edit", "doctor_delete", "doctor_availability"):
            self.assertNotContains(response, f'href="{reverse(name, args=[self.doctor.pk])}"')
        self.assertContains(response, 'href="#main-content"')
        self.assertContains(response, 'aria-label="Toggle navigation"')
        self.assertContains(response, 'href="/#ambulance"')
        self.assertContains(response, "Request ambulance support")
        self.assertContains(response, f'href="{reverse("ambulance_request")}?service=EMERGENCY"')
        self.assertContains(response, 'css/style.css', count=1)
        self.assertNotContains(response, 'images/hospital-care-hero-v1.png')
        self.assertContains(response, "Doctor schedules are shown before booking")
        for filler in ("Doctors in our directory", "Departments to explore", "Appointment slots"):
            self.assertNotContains(response, filler)

    def test_empty_directory_has_honest_empty_state(self):
        self.doctor.delete()
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Our directory is being prepared")

    @override_settings(APPOINTMENT_FEE_NPR="")
    def test_unconfigured_fee_is_not_advertised(self):
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "Appointment fee: NPR")
        self.assertContains(response, "sandbox only")

    def test_stylesheet_url_changes_with_its_content(self):
        with patch("core.templatetags.assets.Path.read_bytes", return_value=b"old stylesheet"):
            old_url = versioned_static("css/style.css")
        with patch("core.templatetags.assets.Path.read_bytes", return_value=b"new stylesheet"):
            new_url = versioned_static("css/style.css")
        self.assertNotEqual(old_url, new_url)
        self.assertRegex(new_url, r"/static/css/style\.css\?v=[a-f0-9]{12}$")
        response = self.client.get(reverse("home"))
        self.assertContains(response, versioned_static("css/style.css"))

    def test_public_can_submit_ambulance_request_without_login(self):
        response = self.client.post(reverse("ambulance_request"), {
            "service_type": AmbulanceRequest.ServiceType.EMERGENCY,
            "patient_name": "Emergency Caller",
            "phone": "9800000000",
            "pickup_location": "Main gate",
            "destination": "",
            "details": "Needs assistance",
            "website": "",
        }, follow=True)
        self.assertRedirects(response, reverse("ambulance_request"))
        self.assertContains(response, "Request received")
        self.assertEqual(AmbulanceRequest.objects.count(), 1)

    def test_ambulance_service_query_preselects_request_type(self):
        response = self.client.get(reverse("ambulance_request") + "?service=SCHEDULED")
        self.assertContains(response, "No account required")
        self.assertEqual(response.context["form"].initial["service_type"], "SCHEDULED")
