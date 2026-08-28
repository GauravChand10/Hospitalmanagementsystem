from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from departments.models import Department


class Doctor(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="doctor_profile",
                               limit_choices_to={"role": "DOCTOR"})
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE
    )
    specialization = models.CharField(max_length=150)
    phone = models.CharField(max_length=15)
    email = models.EmailField(unique=True)

    def __str__(self):
        return f"Dr. {self.first_name} {self.last_name}"


class DoctorAvailability(models.Model):
    DAYS = [(0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"),
            (4, "Friday"), (5, "Saturday"), (6, "Sunday")]
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="availability")
    weekday = models.PositiveSmallIntegerField(choices=DAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ["weekday"]
        constraints = [
            models.UniqueConstraint(fields=["doctor", "weekday"], name="one_schedule_per_doctor_day"),
            models.CheckConstraint(condition=models.Q(end_time__gt=models.F("start_time")), name="availability_end_after_start"),
            models.CheckConstraint(condition=models.Q(weekday__lte=6), name="availability_valid_weekday"),
        ]

    def clean(self):
        super().clean()
        if self.start_time and self.end_time:
            if self.end_time <= self.start_time:
                raise ValidationError("Closing time must be later than opening time (same day).")
            for value in (self.start_time, self.end_time):
                if value.minute not in (0, 30) or value.second or value.microsecond:
                    raise ValidationError("Hours must start/end on the hour or half hour.")

    def __str__(self):
        return f"{self.doctor}: {self.get_weekday_display()} {self.start_time:%H:%M}-{self.end_time:%H:%M}"
