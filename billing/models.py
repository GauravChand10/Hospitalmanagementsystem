from django.db import models

import uuid


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Awaiting sandbox payment"
        PAID = "PAID", "Sandbox payment verified"
        EXPIRED = "EXPIRED", "Expired or cancelled"
        REVIEW = "REVIEW", "Payment received - manual review/refund required"

    appointment = models.OneToOneField("appointments.Appointment", on_delete=models.PROTECT, related_name="payment")
    transaction_uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    product_code = models.CharField(max_length=50, default="EPAYTEST", editable=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    reference = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="positive_payment_amount")]

    def __str__(self):
        return f"Sandbox payment for appointment #{self.appointment_id}"
