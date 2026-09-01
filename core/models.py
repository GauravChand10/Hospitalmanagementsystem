import uuid

from django.db import models


class AmbulanceRequest(models.Model):
    class ServiceType(models.TextChoices):
        EMERGENCY = "EMERGENCY", "Emergency SOS"
        TRANSFER = "TRANSFER", "Hospital transfer"
        SCHEDULED = "SCHEDULED", "Scheduled transport"

    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Received"
        CONTACTED = "CONTACTED", "Caller contacted"
        DISPATCHED = "DISPATCHED", "Dispatched"
        CLOSED = "CLOSED", "Closed"

    reference = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    service_type = models.CharField(max_length=20, choices=ServiceType.choices)
    patient_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30)
    pickup_location = models.CharField(max_length=255)
    destination = models.CharField(max_length=255, blank=True)
    details = models.TextField(max_length=500, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_service_type_display()} - {self.patient_name}"

# Create your models here.
