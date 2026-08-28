from django.db import models

class Prescription(models.Model):
    appointment = models.ForeignKey("appointments.Appointment", on_delete=models.PROTECT,
                                    related_name="prescriptions")
    doctor = models.ForeignKey("doctors.Doctor", on_delete=models.PROTECT)
    medicine = models.ForeignKey("pharmacy.Medicine", on_delete=models.PROTECT)
    dosage = models.CharField(max_length=150)
    frequency = models.CharField(max_length=150)
    duration = models.CharField(max_length=150)
    instructions = models.TextField(blank=True, max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Prescription #{self.pk} - {self.medicine}"
