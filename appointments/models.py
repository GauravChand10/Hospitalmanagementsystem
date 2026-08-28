from django.db import models
from patients.models import Patient
from doctors.models import Doctor


class Appointment(models.Model):

    class Status(models.TextChoices):
        AWAITING_PAYMENT = "Awaiting payment", "Awaiting payment"
        PENDING = "Pending", "Pending"
        COMPLETED = "Completed", "Completed"
        CANCELLED = "Cancelled", "Cancelled"

    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT
    )

    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.PROTECT
    )

    appointment_date = models.DateField()
    appointment_time = models.TimeField()
    reason = models.TextField(blank=True, max_length=2000)

    class Meta:
        ordering = ["-appointment_date", "-appointment_time"]
        constraints = [
            models.UniqueConstraint(fields=["doctor", "appointment_date", "appointment_time"],
                                    condition=~models.Q(status="Cancelled"), name="unique_doctor_slot"),
            models.UniqueConstraint(fields=["patient", "appointment_date", "appointment_time"],
                                    condition=~models.Q(status="Cancelled"), name="unique_patient_slot"),
        ]

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    def __str__(self):
        return f"{self.patient} - {self.doctor}"
