from datetime import datetime

from django import forms
from django.utils import timezone

from .models import DoctorAvailability
from .scheduling import SLOT_LENGTH


class WeeklyAvailabilityForm(forms.Form):
    """Up to two non-overlapping working windows per weekday."""
    def __init__(self, *args, doctor, **kwargs):
        super().__init__(*args, **kwargs)
        self.doctor = doctor
        existing = {}
        for item in doctor.availability.all():
            existing.setdefault(item.weekday, []).append(item)
        for day, label in DoctorAvailability.DAYS:
            items = existing.get(day, [])
            item = items[0] if items else None
            second = items[1] if len(items) > 1 else None
            self.fields[f"enabled_{day}"] = forms.BooleanField(required=False, label=f"{label}: available", initial=bool(items))
            for part, title in (("start", "Opening time"), ("end", "Closing time")):
                self.fields[f"{part}_{day}"] = forms.TimeField(required=False, label=title,
                    initial=getattr(item, f"{part}_time", None),
                    widget=forms.TimeInput(format="%H:%M", attrs={"type": "time", "step": "1800"}))
            self.fields[f"split_{day}"] = forms.BooleanField(required=False, label="Add second shift", initial=second is not None)
            for part, title in (("start_2", "Second opening"), ("end_2", "Second closing")):
                source = "start_time" if part == "start_2" else "end_time"
                self.fields[f"{part}_{day}"] = forms.TimeField(required=False, label=title,
                    initial=getattr(second, source, None),
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
            day_windows = [(start, end)]
            if data.get(f"split_{day}"):
                second_start, second_end = data.get(f"start_2_{day}"), data.get(f"end_2_{day}")
                if second_start is None or second_end is None:
                    raise forms.ValidationError(f"Enter both second-shift times for {label}.")
                day_windows.append((second_start, second_end))
            day_windows.sort()
            for window_start, window_end in day_windows:
                DoctorAvailability(doctor=self.doctor, weekday=day, start_time=window_start,
                                   end_time=window_end).clean(validate_overlap=False)
            if len(day_windows) == 2 and day_windows[1][0] < day_windows[0][1]:
                raise forms.ValidationError(f"The two shifts for {label} cannot overlap.")
            windows[day] = day_windows
        from appointments.models import Appointment
        future = Appointment.objects.filter(doctor=self.doctor, status__in=[Appointment.Status.PENDING, Appointment.Status.AWAITING_PAYMENT],
                                            appointment_date__gte=timezone.localdate())
        for appointment in future:
            begins = datetime.combine(appointment.appointment_date, appointment.appointment_time)
            if timezone.make_aware(begins) <= timezone.now():
                continue
            hours = windows.get(appointment.appointment_date.weekday(), [])
            if not any(datetime.combine(appointment.appointment_date, item[0]) <= begins
                    and begins + SLOT_LENGTH <= datetime.combine(appointment.appointment_date, item[1]) for item in hours):
                raise forms.ValidationError(
                    "These hours would exclude an existing future appointment. Reassign or cancel that appointment first.")
        self.windows = windows
        return data

    def save(self):
        for day, _ in DoctorAvailability.DAYS:
            DoctorAvailability.objects.filter(doctor=self.doctor, weekday=day).delete()
            if day in self.windows:
                DoctorAvailability.objects.bulk_create([
                    DoctorAvailability(doctor=self.doctor, weekday=day, start_time=start, end_time=end)
                    for start, end in self.windows[day]
                ])

    def rows(self):
        return [{"label": label, "enabled": self[f"enabled_{day}"],
                 "start": self[f"start_{day}"], "end": self[f"end_{day}"],
                 "split": self[f"split_{day}"], "start_2": self[f"start_2_{day}"], "end_2": self[f"end_2_{day}"]}
                for day, label in DoctorAvailability.DAYS]
