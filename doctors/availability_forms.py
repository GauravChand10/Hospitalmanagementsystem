from datetime import datetime

from django import forms
from django.utils import timezone

from .models import DoctorAvailability
from .scheduling import SLOT_LENGTH


class WeeklyAvailabilityForm(forms.Form):
    """One optional working window per weekday; unchecked days are closed."""
    def __init__(self, *args, doctor, **kwargs):
        super().__init__(*args, **kwargs)
        self.doctor = doctor
        existing = {item.weekday: item for item in doctor.availability.all()}
        for day, label in DoctorAvailability.DAYS:
            item = existing.get(day)
            self.fields[f"enabled_{day}"] = forms.BooleanField(required=False, label=f"{label}: available", initial=item is not None)
            for part, title in (("start", "Opening time"), ("end", "Closing time")):
                self.fields[f"{part}_{day}"] = forms.TimeField(required=False, label=title,
                    initial=getattr(item, f"{part}_time", None),
                    widget=forms.TimeInput(format="%H:%M", attrs={"type": "time", "step": "1800"}))

    def clean(self):
        data = super().clean()
        windows = {}
        for day, label in DoctorAvailability.DAYS:
            if not data.get(f"enabled_{day}"):
                continue
            start, end = data.get(f"start_{day}"), data.get(f"end_{day}")
            if start is None or end is None:
                raise forms.ValidationError(f"Enter both opening and closing times for {label}.")
            record = DoctorAvailability(doctor=self.doctor, weekday=day, start_time=start, end_time=end)
            record.clean()
            windows[day] = (start, end)
        from appointments.models import Appointment
        future = Appointment.objects.filter(doctor=self.doctor, status__in=[Appointment.Status.PENDING, Appointment.Status.AWAITING_PAYMENT],
                                            appointment_date__gte=timezone.localdate())
        for appointment in future:
            begins = datetime.combine(appointment.appointment_date, appointment.appointment_time)
            if timezone.make_aware(begins) <= timezone.now():
                continue
            hours = windows.get(appointment.appointment_date.weekday())
            if hours is None or not (datetime.combine(appointment.appointment_date, hours[0]) <= begins
                    and begins + SLOT_LENGTH <= datetime.combine(appointment.appointment_date, hours[1])):
                raise forms.ValidationError(
                    "These hours would exclude an existing future appointment. Reassign or cancel that appointment first.")
        self.windows = windows
        return data

    def save(self):
        for day, _ in DoctorAvailability.DAYS:
            if day in self.windows:
                start, end = self.windows[day]
                DoctorAvailability.objects.update_or_create(doctor=self.doctor, weekday=day,
                    defaults={"start_time": start, "end_time": end})
            else:
                DoctorAvailability.objects.filter(doctor=self.doctor, weekday=day).delete()

    def rows(self):
        return [{"label": label, "enabled": self[f"enabled_{day}"],
                 "start": self[f"start_{day}"], "end": self[f"end_{day}"]}
                for day, label in DoctorAvailability.DAYS]
