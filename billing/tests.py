import base64
import json
from datetime import timedelta, time
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings, Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from appointments.models import Appointment
from departments.models import Department
from doctors.models import Doctor, DoctorAvailability
from patients.models import Patient
from .models import Payment
from .services import create_payment, expire_holds
from .esewa import signature, decode_callback, PaymentError, REQUEST_FIELDS, checkout_fields


@override_settings(APPOINTMENT_FEE_NPR="100.00", ESEWA_RETURN_ORIGIN="http://127.0.0.1:8010")
class EsewaPaymentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="patient")
        cls.other = User.objects.create_user(username="other")
        cls.doctor_user = User.objects.create_user(username="doctor", role="DOCTOR")
        cls.patient = Patient.objects.create(user=cls.user, first_name="Test", last_name="Patient", gender="Other",
            date_of_birth="2000-01-01", phone="123", email="patient@example.com", address="Test")
        department = Department.objects.create(name="General")
        cls.doctor = Doctor.objects.create(user=cls.doctor_user, first_name="Test", last_name="Doctor",
            department=department, specialization="General", phone="456", email="doctor@example.com")
        cls.day = timezone.localdate() + timedelta(days=2)
        DoctorAvailability.objects.create(doctor=cls.doctor, weekday=cls.day.weekday(), start_time=time(9), end_time=time(17))
        cls.appointment = Appointment.objects.create(patient=cls.patient, doctor=cls.doctor,
            appointment_date=cls.day, appointment_time=time(10), status=Appointment.Status.AWAITING_PAYMENT)
        cls.payment = create_payment(cls.appointment, Decimal("100.00"))

    def setUp(self):
        self.client.force_login(self.user)

    def callback_data(self, **overrides):
        data = {"transaction_code": "TEST-REF", "status": "COMPLETE", "total_amount": "100.00",
            "transaction_uuid": str(self.payment.transaction_uuid), "product_code": "EPAYTEST",
            "signed_field_names": "transaction_code,status,total_amount,transaction_uuid,product_code,signed_field_names",
            **overrides}
        data["signature"] = signature(data, data["signed_field_names"])
        return data

    def response(self, **overrides):
        return {"status": "COMPLETE", "product_code": "EPAYTEST", "total_amount": 100.0,
                "transaction_uuid": str(self.payment.transaction_uuid), "ref_id": "TEST-REF", **overrides}

    def callback(self, data=None):
        encoded = base64.b64encode(json.dumps(data or self.callback_data()).encode()).decode()
        return self.client.get(reverse("esewa_success"), {"data": encoded})

    def assert_unpaid(self):
        self.payment.refresh_from_db()
        self.appointment.refresh_from_db()
        self.assertNotEqual(self.payment.status, Payment.Status.PAID)
        self.assertNotEqual(self.appointment.status, Appointment.Status.PENDING)

    def test_hmac_against_independently_computed_vector(self):
        data = {"total_amount": "100", "transaction_uuid": "11-201-13", "product_code": "EPAYTEST"}
        # Independently confirmed with .NET HMACSHA256; the docs' sample output
        # is not consistent with their displayed input and sandbox key.
        self.assertEqual(signature(data, REQUEST_FIELDS), "5DZywcrTKD0gia/rsSMcrRHmJl+4Tbol6S+lWgdJ94E=")

    def test_checkout_uses_stored_amount_not_browser_amount(self):
        response = self.client.post(reverse("esewa_checkout", args=[self.appointment.pk]), {"amount": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["fields"]["total_amount"], "100.00")
        self.assertContains(response, "sandbox")
        self.assertNotContains(response, "8gBm/:&amp;EnhH.1/q")
        fields = checkout_fields(self.payment)
        self.assertEqual(fields["signature"], signature(fields, REQUEST_FIELDS))
        self.assertEqual(fields["success_url"], "http://127.0.0.1:8010/billing/esewa/success/")

    def test_checkout_and_status_are_owner_only_post_and_csrf_protected(self):
        for name in ("esewa_checkout", "check_payment"):
            url = reverse(name, args=[self.appointment.pk])
            self.assertEqual(self.client.get(url).status_code, 405)
            protected = Client(enforce_csrf_checks=True)
            protected.force_login(self.user)
            self.assertEqual(protected.post(url).status_code, 403)
            self.client.force_login(self.other)
            self.assertEqual(self.client.post(url).status_code, 404)
            self.client.force_login(self.doctor_user)
            self.assertEqual(self.client.post(url).status_code, 403)
            self.client.logout()
            self.assertEqual(self.client.post(url).status_code, 302)
            self.client.force_login(self.user)

    @patch("billing.esewa.fetch_status")
    def test_verified_callback_confirms_once(self, fetch):
        fetch.return_value = self.response()
        self.assertEqual(self.callback().status_code, 302)
        self.payment.refresh_from_db()
        verified_at = self.payment.verified_at
        self.assertEqual(self.payment.status, Payment.Status.PAID)
        self.assertEqual(self.payment.reference, "TEST-REF")
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.PENDING)
        self.assertEqual(self.callback().status_code, 302)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.verified_at, verified_at)
        self.assertEqual(Payment.objects.count(), 1)

    @patch("billing.esewa.fetch_status")
    def test_tampered_signature_never_calls_verification(self, fetch):
        data = self.callback_data()
        data["total_amount"] = "1.00"
        self.assertEqual(self.callback(data).status_code, 400)
        fetch.assert_not_called()
        self.assert_unpaid()

    @patch("billing.esewa.fetch_status")
    def test_signed_but_wrong_amount_is_rejected(self, fetch):
        fetch.return_value = self.response()
        self.assertEqual(self.callback(self.callback_data(total_amount="1.00")).status_code, 400)
        self.assert_unpaid()

    @patch("billing.esewa.fetch_status")
    def test_status_identity_amount_reference_must_match(self, fetch):
        for overrides in ({"total_amount": 1}, {"product_code": "OTHER"}, {"transaction_uuid": "wrong"},
                          {"ref_id": "different"}, {"ref_id": None}):
            fetch.return_value = self.response(**overrides)
            self.assertEqual(self.callback().status_code, 400)
            self.assert_unpaid()

    @patch("billing.esewa.fetch_status")
    def test_unconfirmed_provider_status_does_not_confirm(self, fetch):
        for status in ("PENDING", "NOT_FOUND", "AMBIGIOUS", "FULL_REFUND", "CANCELED"):
            fetch.return_value = self.response(status=status)
            self.assertEqual(self.callback().status_code, 400)
            self.assert_unpaid()

    @patch("billing.esewa.fetch_status", side_effect=PaymentError("Verification unavailable"))
    def test_verification_failure_preserves_unpaid_booking(self, fetch):
        self.assertEqual(self.callback().status_code, 400)
        self.assertEqual(self.client.post(reverse("check_payment", args=[self.appointment.pk])).status_code, 302)
        self.assert_unpaid()

    @patch("billing.esewa.fetch_status")
    def test_manual_status_check_recovers_missing_callback(self, fetch):
        fetch.return_value = {"pid": str(self.payment.transaction_uuid), "scd": "EPAYTEST",
                              "totalAmount": 100, "status": "COMPLETE", "refId": "TEST-REF"}
        self.client.post(reverse("check_payment", args=[self.appointment.pk]))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PAID)

    def test_expiry_releases_slot(self):
        self.payment.expires_at = timezone.now() - timedelta(seconds=1)
        self.payment.save()
        expire_holds()
        self.payment.refresh_from_db()
        self.appointment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.EXPIRED)
        self.assertEqual(self.appointment.status, Appointment.Status.CANCELLED)
        self.assertEqual(self.client.post(reverse("esewa_checkout", args=[self.appointment.pk])).status_code, 302)

    @patch("billing.esewa.fetch_status")
    def test_late_payment_requires_review_without_reclaiming_slot(self, fetch):
        self.payment.expires_at = timezone.now() - timedelta(seconds=1)
        self.payment.save()
        expire_holds()
        replacement = Appointment.objects.create(patient=self.patient, doctor=self.doctor,
            appointment_date=self.day, appointment_time=time(10))
        fetch.return_value = self.response()
        self.assertEqual(self.callback().status_code, 302)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.REVIEW)
        replacement.refresh_from_db()
        self.assertEqual(replacement.status, Appointment.Status.PENDING)
        self.assert_unpaid()

    @patch("billing.esewa.fetch_status")
    def test_paid_cancellation_is_not_mislabeled_as_refunded(self, fetch):
        fetch.return_value = self.response()
        self.callback()
        self.client.post(reverse("cancel_appointment", args=[self.appointment.pk]))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.REVIEW)
        self.callback()
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.REVIEW)

    def test_failure_redirect_does_not_change_payment(self):
        self.client.get(reverse("esewa_failure"))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)

    def test_unpaid_booking_cannot_be_completed_or_prescribed(self):
        self.client.force_login(self.doctor_user)
        for name in ("complete_appointment", "prescribe"):
            self.client.post(reverse(name, args=[self.appointment.pk]))
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.AWAITING_PAYMENT)

    def test_new_booking_creates_payment_with_server_fee(self):
        response = self.client.post(reverse("book_appointment"), {"doctor": self.doctor.pk,
            "appointment_date": str(self.day), "appointment_time": "11:00", "amount": "1", "status": "Pending"})
        self.assertEqual(response.status_code, 302)
        payment = Payment.objects.exclude(pk=self.payment.pk).get()
        self.assertEqual(payment.amount, Decimal("100.00"))
        self.assertEqual(payment.appointment.status, Appointment.Status.AWAITING_PAYMENT)

    @override_settings(APPOINTMENT_FEE_NPR="500.00")
    def test_approved_fee_is_shown_and_saved(self):
        page = self.client.get(reverse("book_appointment"))
        self.assertContains(page, "NPR 500.00")
        response = self.client.post(reverse("book_appointment"), {"doctor": self.doctor.pk,
            "appointment_date": str(self.day), "appointment_time": "11:00", "amount": "1"})
        self.assertEqual(response.status_code, 302)
        payment = Payment.objects.exclude(pk=self.payment.pk).get()
        self.assertEqual(payment.amount, Decimal("500.00"))

    @override_settings(APPOINTMENT_FEE_NPR="")
    def test_unconfigured_fee_blocks_booking(self):
        response = self.client.post(reverse("book_appointment"), {"doctor": self.doctor.pk,
            "appointment_date": str(self.day), "appointment_time": "11:00"})
        self.assertContains(response, "fee has not been configured")
        self.assertEqual(Appointment.objects.count(), 1)

    def test_malformed_callbacks_rejected(self):
        for value in ("garbage", "", base64.b64encode(b'[]').decode()):
            self.assertEqual(self.client.get(reverse("esewa_success"), {"data": value}).status_code, 400)
        data = self.callback_data(signed_field_names="status")
        with self.assertRaises(PaymentError):
            decode_callback(base64.b64encode(json.dumps(data).encode()).decode())

    @patch("billing.esewa.build_opener")
    def test_status_uses_working_sandbox_host_and_stored_details(self, opener):
        from .esewa import fetch_status
        from urllib.parse import urlsplit, parse_qs
        opener.return_value.open.return_value.__enter__.return_value.read.return_value = json.dumps(self.response()).encode()
        self.assertEqual(fetch_status(self.payment)["status"], "COMPLETE")
        url = opener.return_value.open.call_args.args[0]
        self.assertEqual(urlsplit(url).netloc, "rc.esewa.com.np")
        self.assertEqual(parse_qs(urlsplit(url).query), {
            "product_code": ["EPAYTEST"], "total_amount": ["100.00"],
            "transaction_uuid": [str(self.payment.transaction_uuid)],
        })
        self.assertEqual(opener.return_value.open.call_args.kwargs["timeout"], 10)

    @patch("billing.esewa.build_opener")
    def test_status_network_failure_is_safe(self, opener):
        from .esewa import fetch_status
        opener.return_value.open.side_effect = TimeoutError()
        with self.assertRaises(PaymentError):
            fetch_status(self.payment)
