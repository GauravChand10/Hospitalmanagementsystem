from django.test import TestCase, override_settings
from django.test import Client
from django.urls import reverse
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from datetime import timedelta, time

from accounts.models import User
from departments.models import Department
from doctors.models import Doctor, DoctorAvailability
from patients.models import Patient
from pharmacy.models import Medicine
from prescriptions.models import Prescription
from .models import Appointment


@override_settings(APPOINTMENT_FEE_NPR="100.00")
class AppointmentWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        department = Department.objects.create(name="General")
        cls.patient_user = User.objects.create_user(username="patient1")
        cls.other_patient_user = User.objects.create_user(username="patient2")
        cls.doctor_user = User.objects.create_user(username="doctor1", role=User.Role.DOCTOR)
        cls.other_doctor_user = User.objects.create_user(username="doctor2", role=User.Role.DOCTOR)
        cls.receptionist = User.objects.create_user(username="reception", role=User.Role.RECEPTIONIST)
        cls.admin_user = User.objects.create_user(username="administrator", role=User.Role.ADMIN)
        cls.patient = Patient.objects.create(user=cls.patient_user, first_name="Patient", last_name="One",
            gender="Other", date_of_birth="2000-01-01", phone="123", email="patient1@example.com", address="Test")
        cls.other_patient = Patient.objects.create(user=cls.other_patient_user, first_name="Patient", last_name="Two",
            gender="Other", date_of_birth="2000-01-01", phone="456", email="patient2@example.com", address="Test")
        cls.doctor = Doctor.objects.create(user=cls.doctor_user, first_name="Doctor", last_name="One",
            department=department, specialization="General", phone="123", email="doctor1@example.com")
        cls.other_doctor = Doctor.objects.create(user=cls.other_doctor_user, first_name="Doctor", last_name="Two",
            department=department, specialization="General", phone="456", email="doctor2@example.com")
        cls.day = timezone.localdate() + timedelta(days=2)
        for doctor in (cls.doctor, cls.other_doctor):
            DoctorAvailability.objects.create(doctor=doctor, weekday=cls.day.weekday(), start_time=time(9), end_time=time(17))
        cls.appointment = Appointment.objects.create(patient=cls.patient, doctor=cls.doctor,
            appointment_date=cls.day, appointment_time=time(10), reason="Private reason")
        cls.medicine = Medicine.objects.create(name="Test medicine", strength="Test strength")
        cls.prescription_data = {"medicine": cls.medicine.pk, "dosage": "Recorded by clinician",
            "frequency": "Recorded by clinician", "duration": "Recorded by clinician", "instructions": "Test instructions"}

    def url(self, name):
        return reverse(name, args=[self.appointment.pk])

    def book_data(self, **extra):
        return {"doctor": self.doctor.pk, "appointment_date": str(self.day),
                "appointment_time": "11:00", "reason": "Consultation", **extra}

    def test_guests_cannot_access_workflow(self):
        urls = [reverse(name) for name in ("appointment_list", "patient_profile", "book_appointment", "my_prescriptions")]
        urls += [self.url(name) for name in ("appointment_detail", "cancel_appointment", "assign_doctor", "prescribe", "complete_appointment")]
        for url in urls:
            for method in ("get", "post"):
                with self.subTest(url=url, method=method):
                    response = getattr(self.client, method)(url)
                    self.assertEqual(response.status_code, 302)
                    self.assertTrue(response.url.startswith(reverse("login")))

    def test_patient_cannot_read_or_change_another_patient_appointment(self):
        self.client.force_login(self.other_patient_user)
        self.assertNotContains(self.client.get(reverse("appointment_list")), "Private reason")
        for name in ("appointment_detail", "cancel_appointment"):
            self.assertEqual(self.client.post(self.url(name)).status_code, 404)
        self.assertEqual(self.client.get(self.url("appointment_detail")).status_code, 404)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, "Pending")

    def test_booking_ignores_forged_patient_and_status(self):
        self.client.force_login(self.patient_user)
        response = self.client.post(reverse("book_appointment"), self.book_data(
            patient=self.other_patient.pk, status="Completed"))
        self.assertEqual(response.status_code, 302)
        created = Appointment.objects.exclude(pk=self.appointment.pk).get()
        self.assertEqual(created.patient_id, self.patient.pk)
        self.assertEqual(created.status, "Awaiting payment")
        self.assertEqual(self.client.get(response.url).status_code, 200)

    def test_booking_rejects_past_invalid_and_conflicting_slots(self):
        self.client.force_login(self.patient_user)
        cases = [self.book_data(appointment_date="2000-01-01"), self.book_data(appointment_time="11:15"),
                 self.book_data(appointment_time="10:00"), self.book_data(appointment_time="10:00", doctor=self.other_doctor.pk)]
        for data in cases:
            with self.subTest(data=data):
                response = self.client.post(reverse("book_appointment"), data)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
                self.assertEqual(Appointment.objects.count(), 1)

    def test_database_prevents_double_booking(self):
        for patient, doctor in ((self.other_patient, self.doctor), (self.patient, self.other_doctor)):
            with self.assertRaises(IntegrityError), transaction.atomic():
                Appointment.objects.create(patient=patient, doctor=doctor, appointment_date=self.day, appointment_time=time(10))

    def test_cancellation_is_post_only_and_releases_slot(self):
        self.client.force_login(self.patient_user)
        self.assertEqual(self.client.get(self.url("cancel_appointment")).status_code, 405)
        self.client.post(self.url("cancel_appointment"))
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, "Cancelled")
        self.assertEqual(self.client.post(reverse("book_appointment"), self.book_data(appointment_time="10:00")).status_code, 302)

    def test_patients_cannot_assign_prescribe_or_complete(self):
        self.client.force_login(self.patient_user)
        for name in ("assign_doctor", "prescribe", "complete_appointment"):
            self.assertEqual(self.client.post(self.url(name), self.prescription_data).status_code, 403)
        self.assertEqual(Prescription.objects.count(), 0)

    def test_unassigned_doctor_cannot_view_or_prescribe(self):
        self.client.force_login(self.other_doctor_user)
        self.assertEqual(self.client.get(self.url("appointment_detail")).status_code, 404)
        self.assertEqual(self.client.post(self.url("prescribe"), self.prescription_data).status_code, 404)

    def test_receptionist_can_assign_and_doctor_access_changes(self):
        self.client.force_login(self.receptionist)
        self.assertEqual(self.client.get(self.url("assign_doctor")).status_code, 200)
        self.assertEqual(self.client.post(self.url("assign_doctor"), {"doctor": self.other_doctor.pk}).status_code, 302)
        self.client.force_login(self.doctor_user)
        self.assertEqual(self.client.get(self.url("appointment_detail")).status_code, 404)
        self.client.force_login(self.other_doctor_user)
        self.assertEqual(self.client.get(self.url("appointment_detail")).status_code, 200)

    def test_scheduler_cannot_prescribe(self):
        for user in (self.admin_user, self.receptionist):
            self.client.force_login(user)
            self.assertEqual(self.client.post(self.url("prescribe"), self.prescription_data).status_code, 403)

    def test_prescription_is_owned_by_assigned_doctor_and_visible_only_to_patient(self):
        self.client.force_login(self.doctor_user)
        self.assertEqual(self.client.get(self.url("prescribe")).status_code, 200)
        response = self.client.post(self.url("prescribe"), {
            **self.prescription_data, "doctor": self.other_doctor.pk, "appointment": 9999})
        self.assertEqual(response.status_code, 302)
        prescription = Prescription.objects.get()
        self.assertEqual(prescription.doctor_id, self.doctor.pk)
        self.assertEqual(prescription.appointment_id, self.appointment.pk)
        self.client.force_login(self.patient_user)
        self.assertContains(self.client.get(reverse("my_prescriptions")), "Test medicine")
        self.client.force_login(self.other_patient_user)
        self.assertNotContains(self.client.get(reverse("my_prescriptions")), "Test medicine")

    def test_inactive_medicine_is_rejected(self):
        self.medicine.active = False
        self.medicine.save()
        self.client.force_login(self.doctor_user)
        response = self.client.post(self.url("prescribe"), self.prescription_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(Prescription.objects.exists())

    def test_prescription_locks_assignment_and_cancellation(self):
        self.client.force_login(self.doctor_user)
        self.client.post(self.url("prescribe"), self.prescription_data)
        self.client.force_login(self.receptionist)
        response = self.client.post(self.url("assign_doctor"), {"doctor": self.other_doctor.pk})
        self.assertTrue(response.context["form"].errors)
        self.client.post(self.url("cancel_appointment"))
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, "Pending")
        self.assertEqual(self.appointment.doctor_id, self.doctor.pk)

    def test_completed_appointment_cannot_be_changed(self):
        self.client.force_login(self.doctor_user)
        self.assertEqual(self.client.get(self.url("complete_appointment")).status_code, 405)
        self.client.post(self.url("complete_appointment"))
        self.client.post(self.url("prescribe"), self.prescription_data)
        self.assertFalse(Prescription.objects.exists())
        self.client.force_login(self.receptionist)
        self.client.post(self.url("assign_doctor"), {"doctor": self.other_doctor.pk})
        self.client.post(self.url("cancel_appointment"))
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, "Completed")
        self.assertEqual(self.appointment.doctor_id, self.doctor.pk)

    def test_doctor_with_history_cannot_be_deleted(self):
        with self.assertRaises(ProtectedError):
            self.doctor.delete()
        self.client.force_login(self.admin_user)
        self.assertRedirects(self.client.post(reverse("doctor_delete", args=[self.doctor.pk])),
                             reverse("doctor_detail", args=[self.doctor.pk]))
        self.assertTrue(Doctor.objects.filter(pk=self.doctor.pk).exists())

    def test_admin_does_not_bypass_appointment_workflow(self):
        superuser = User.objects.create_user(username="root", is_superuser=True, is_staff=True)
        self.client.force_login(superuser)
        response = self.client.post(reverse("admin:appointments_appointment_change", args=[self.appointment.pk]),
                                    {"status": "Completed"})
        self.assertEqual(response.status_code, 403)

    def test_new_account_must_complete_profile_without_claiming_existing_records(self):
        user = User.objects.create_user(username="new", email=self.patient.email)
        self.client.force_login(user)
        self.assertRedirects(self.client.get(reverse("book_appointment")), reverse("patient_profile"))
        self.assertFalse(Patient.objects.filter(user=user).exists())
        data = {"first_name": "New", "last_name": "Patient", "gender": "Other", "date_of_birth": "2000-01-01",
                "phone": "123", "email": self.patient.email, "address": "Test", "user": self.patient_user.pk}
        response = self.client.post(reverse("patient_profile"), data)
        self.assertTrue(response.context["form"].errors)
        response = self.client.post(reverse("patient_profile"), {**data, "email": "new@example.com"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Patient.objects.get(email="new@example.com").user_id, user.pk)

    def test_profile_rejects_future_birth_date(self):
        self.client.force_login(self.patient_user)
        response = self.client.post(reverse("patient_profile"), {"first_name": "Test", "last_name": "Patient",
            "gender": "Other", "date_of_birth": str(self.day), "phone": "123", "email": self.patient.email, "address": "Test"})
        self.assertIn("date_of_birth", response.context["form"].errors)

    def test_write_requests_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.patient_user)
        self.assertEqual(client.post(reverse("book_appointment"), self.book_data()).status_code, 403)
        self.assertEqual(client.post(self.url("cancel_appointment")).status_code, 403)

    def test_assignment_rejects_a_busy_doctor(self):
        Appointment.objects.create(patient=self.other_patient, doctor=self.other_doctor,
            appointment_date=self.day, appointment_time=time(10))
        self.client.force_login(self.receptionist)
        response = self.client.post(self.url("assign_doctor"), {"doctor": self.other_doctor.pk})
        self.assertTrue(response.context["form"].errors)

    def test_booking_rejects_closed_days_and_outside_hours(self):
        self.client.force_login(self.patient_user)
        for data in (self.book_data(appointment_time="08:30"), self.book_data(appointment_time="17:00"),
                     self.book_data(appointment_date=str(self.day + timedelta(days=1)))):
            response = self.client.post(reverse("book_appointment"), data)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form"].errors)
        self.assertEqual(Appointment.objects.count(), 1)

    def test_assignment_rejects_doctor_without_hours(self):
        self.other_doctor.availability.all().delete()
        self.client.force_login(self.receptionist)
        response = self.client.post(self.url("assign_doctor"), {"doctor": self.other_doctor.pk})
        self.assertTrue(response.context["form"].errors)

    def test_hours_cannot_exclude_existing_future_appointment(self):
        self.client.force_login(self.admin_user)
        url = reverse("doctor_availability", args=[self.doctor.pk])
        response = self.client.post(url, {})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertTrue(self.doctor.availability.exists())

    def test_busy_slots_hidden_and_cancelled_slots_reappear(self):
        from doctors.scheduling import available_slots
        self.assertNotIn("10:00", available_slots(self.doctor, self.day))
        self.appointment.status = "Cancelled"
        self.appointment.save()
        self.assertIn("10:00", available_slots(self.doctor, self.day))

    def test_booking_prefills_selected_slot(self):
        self.client.force_login(self.patient_user)
        response = self.client.get(reverse("book_appointment"), self.book_data())
        self.assertEqual(response.context["form"]["doctor"].value(), str(self.doctor.pk))
        self.assertEqual(response.context["form"]["appointment_time"].value(), "11:00")
