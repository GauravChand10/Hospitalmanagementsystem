from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from appointments.models import Appointment
from .models import Payment
from .esewa import verify_status


def create_payment(appointment, amount):
    return Payment.objects.create(appointment=appointment, amount=amount,
                                  expires_at=timezone.now() + timedelta(minutes=15))


def expire_holds():
    """Release expired holds on demand; no background worker is required locally."""
    ids = Payment.objects.filter(status=Payment.Status.PENDING, expires_at__lte=timezone.now()).values_list("appointment_id", flat=True)
    for appointment_id in list(ids):
        with transaction.atomic():
            appointment = Appointment.objects.select_for_update().get(pk=appointment_id)
            payment = Payment.objects.select_for_update().get(appointment_id=appointment_id)
            if payment.status != Payment.Status.PENDING or payment.expires_at > timezone.now():
                continue
            payment.status = Payment.Status.EXPIRED
            payment.save(update_fields=["status"])
            if appointment.status == Appointment.Status.AWAITING_PAYMENT:
                appointment.status = Appointment.Status.CANCELLED
                appointment.save(update_fields=["status"])


def confirm_payment(payment, callback=None):
    # Network verification happens before taking database locks.
    reference = verify_status(payment, callback)
    with transaction.atomic():
        appointment = Appointment.objects.select_for_update().get(pk=payment.appointment_id)
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        if payment.status in (Payment.Status.PAID, Payment.Status.REVIEW):
            return payment  # Repeated callbacks must not confirm/refund twice.
        payment.reference = reference
        payment.verified_at = timezone.now()
        if (appointment.status == Appointment.Status.AWAITING_PAYMENT and payment.expires_at > timezone.now()
                and payment.status == Payment.Status.PENDING):
            payment.status = Payment.Status.PAID
            appointment.status = Appointment.Status.PENDING
            appointment.save(update_fields=["status"])
        else:
            payment.status = Payment.Status.REVIEW
            if appointment.status == Appointment.Status.AWAITING_PAYMENT:
                appointment.status = Appointment.Status.CANCELLED
                appointment.save(update_fields=["status"])
        payment.save(update_fields=["status", "reference", "verified_at"])
        return payment


def cancel_payment(appointment):
    payment = Payment.objects.select_for_update().filter(appointment=appointment).first()
    if payment:
        if payment.status == Payment.Status.PAID:
            payment.status = Payment.Status.REVIEW
        elif payment.status == Payment.Status.PENDING:
            payment.status = Payment.Status.EXPIRED
        payment.save(update_fields=["status"])
