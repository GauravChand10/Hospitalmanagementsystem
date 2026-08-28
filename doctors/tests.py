from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from departments.models import Department
from .models import Doctor
from .permissions import can_manage_doctors
from .models import DoctorAvailability
from .availability_forms import WeeklyAvailabilityForm
from .scheduling import available_slots, within_hours
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import time, timedelta


class DoctorAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department = Department.objects.create(name="Cardiology")
        cls.data = {
            "first_name": "Test",
            "last_name": "Doctor",
            "department": cls.department.pk,
            "specialization": "Cardiology",
            "phone": "1234567890",
            "email": "doctor@example.com",
        }
        cls.doctor = Doctor.objects.create(
            **{**cls.data, "department": cls.department}
        )
        cls.users = {
            role: User.objects.create_user(username=role, role=role)
            for role in User.Role.values
        }
        cls.superuser = User.objects.create_user(
            username="superuser", is_superuser=True, is_staff=True
        )

    def management_urls(self):
        return [
            reverse("doctor_create"),
            reverse("doctor_edit", args=[self.doctor.pk]),
            reverse("doctor_delete", args=[self.doctor.pk]),
        ]

    def assert_records_unchanged(self):
        self.assertEqual(Doctor.objects.count(), 1)
        self.doctor.refresh_from_db()
        self.assertEqual(self.doctor.first_name, "Test")

    def test_anonymous_requests_redirect_to_login_without_changes(self):
        for url in self.management_urls():
            for method in ("get", "post"):
                with self.subTest(url=url, method=method):
                    response = getattr(self.client, method)(
                        url, data={**self.data, "first_name": "Changed"}
                        if method == "post" else {}
                    )
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(
                        response.url, f"{reverse('login')}?next={url}"
                    )
                    self.assert_records_unchanged()

    def test_non_admin_roles_are_forbidden_without_changes(self):
        for role in (User.Role.PATIENT, User.Role.DOCTOR, User.Role.RECEPTIONIST):
            self.client.force_login(self.users[role])
            for url in self.management_urls():
                for method in ("get", "post"):
                    with self.subTest(role=role, url=url, method=method):
                        response = getattr(self.client, method)(
                            url, data={**self.data, "first_name": "Changed"}
                            if method == "post" else {}
                        )
                        self.assertEqual(response.status_code, 403)
                        self.assert_records_unchanged()

    def test_admin_and_superuser_can_manage_doctors(self):
        for user in (self.users[User.Role.ADMIN], self.superuser):
            self.client.force_login(user)
            for url in self.management_urls():
                self.assertEqual(self.client.get(url).status_code, 200)
            self.assert_records_unchanged()
            response = self.client.post(
                reverse("doctor_create"),
                {**self.data, "email": "new@example.com"},
            )
            self.assertRedirects(response, reverse("doctor_list"))
            created = Doctor.objects.get(email="new@example.com")
            response = self.client.post(
                reverse("doctor_edit", args=[created.pk]),
                {**self.data, "email": "new@example.com", "first_name": "Updated"},
            )
            self.assertRedirects(response, reverse("doctor_detail", args=[created.pk]))
            created.refresh_from_db()
            self.assertEqual(created.first_name, "Updated")
            response = self.client.post(reverse("doctor_delete", args=[created.pk]))
            self.assertRedirects(response, reverse("doctor_list"))
            self.assertFalse(Doctor.objects.filter(pk=created.pk).exists())

    def test_public_pages_hide_management_links_for_unauthorized_users(self):
        for user in (None, *self.users.values(), self.superuser):
            self.client.logout()
            if user is not None:
                self.client.force_login(user)
            listing = self.client.get(reverse("doctor_list"))
            detail = self.client.get(reverse("doctor_detail", args=[self.doctor.pk]))
            assertion = self.assertContains if user and can_manage_doctors(user) else self.assertNotContains
            assertion(listing, f'href="{reverse("doctor_create")}"')
            for name in ("doctor_edit", "doctor_delete"):
                assertion(detail, f'href="{reverse(name, args=[self.doctor.pk])}"')

    def test_inactive_admin_and_staff_patient_are_not_authorized(self):
        admin = self.users[User.Role.ADMIN]
        admin.is_active = False
        self.assertFalse(can_manage_doctors(admin))
        patient = self.users[User.Role.PATIENT]
        patient.is_staff = True
        self.assertFalse(can_manage_doctors(patient))


class AvailabilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        department = Department.objects.create(name="General")
        cls.doctor = Doctor.objects.create(first_name="Test", last_name="Doctor", department=department,
            specialization="General", phone="123", email="doctor@example.com")
        cls.users = {role: User.objects.create_user(username=role, role=role) for role in User.Role.values}

    def setUp(self):
        self.day = timezone.localdate() + timedelta(days=3)
        self.url = reverse("doctor_availability", args=[self.doctor.pk])

    def payload(self, start="09:00", end="17:00"):
        day = self.day.weekday()
        return {f"enabled_{day}": "on", f"start_{day}": start, f"end_{day}": end}

    def test_only_admin_can_set_hours(self):
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 302)
        self.assertFalse(DoctorAvailability.objects.exists())
        for role in (User.Role.PATIENT, User.Role.DOCTOR, User.Role.RECEPTIONIST):
            self.client.force_login(self.users[role])
            self.assertEqual(self.client.post(self.url, self.payload()).status_code, 403)
        self.client.force_login(self.users[User.Role.ADMIN])
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertRedirects(self.client.post(self.url, self.payload()), reverse("doctor_detail", args=[self.doctor.pk]))
        self.assertEqual(DoctorAvailability.objects.count(), 1)

    def test_invalid_hours_are_rejected(self):
        for start, end in (("17:00", "09:00"), ("09:00", "09:00"), ("09:15", "17:00"), ("", "17:00")):
            form = WeeklyAvailabilityForm(self.payload(start, end), doctor=self.doctor)
            self.assertFalse(form.is_valid())
        window = DoctorAvailability(doctor=self.doctor, weekday=0, start_time=time(12), end_time=time(11))
        with self.assertRaises(ValidationError):
            window.full_clean()

    def test_entire_slot_must_fit_hours(self):
        self.assertFalse(within_hours(self.doctor, self.day, time(9)))
        DoctorAvailability.objects.create(doctor=self.doctor, weekday=self.day.weekday(), start_time=time(9), end_time=time(10))
        self.assertTrue(within_hours(self.doctor, self.day, time(9, 30)))
        self.assertFalse(within_hours(self.doctor, self.day, time(10)))
        self.assertFalse(within_hours(self.doctor, self.day, time(8, 30)))
        self.assertFalse(within_hours(self.doctor, self.day + timedelta(days=1), time(9)))
        self.assertEqual(available_slots(self.doctor, self.day), ["09:00", "09:30"])

    def test_hours_visible_without_login(self):
        DoctorAvailability.objects.create(doctor=self.doctor, weekday=self.day.weekday(), start_time=time(9), end_time=time(10))
        response = self.client.get(reverse("doctor_detail", args=[self.doctor.pk]), {"date": str(self.day)})
        self.assertContains(response, "Weekly Availability")
        self.assertContains(response, "09:30")
        self.assertNotContains(response, "Manage Availability")
        self.assertEqual(self.client.get(reverse("doctor_detail", args=[self.doctor.pk]), {"date": "2026-99-99"}).status_code, 200)
