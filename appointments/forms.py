from datetime import datetime

from django import forms
from django.utils import timezone

from doctors.models import Doctor
from doctors.scheduling import within_hours
from patients.models import Patient
from pharmacy.models import Medicine
from prescriptions.models import Prescription
from .models import Appointment


class PatientProfileForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = ["first_name", "last_name", "gender", "date_of_birth", "phone", "email", "address"]
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"})}

    def clean_date_of_birth(self):
        value = self.cleaned_data["date_of_birth"]
        if value > timezone.localdate():
            raise forms.ValidationError("Date of birth cannot be in the future.")
        return value


class BookingForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ["doctor", "appointment_date", "appointment_time", "reason"]
        widgets = {"appointment_date": forms.DateInput(attrs={"type": "date"}),
                   "appointment_time": forms.TimeInput(attrs={"type": "time"}),
                   "reason": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["doctor"].queryset = Doctor.objects.select_related("department").order_by("first_name")

    def clean(self):
        data = super().clean()
        day, clock = data.get("appointment_date"), data.get("appointment_time")
        if day and clock:
            when = timezone.make_aware(datetime.combine(day, clock))
            if when <= timezone.now():
                raise forms.ValidationError("Choose a future appointment date and time.")
            if clock.second or clock.microsecond or clock.minute not in (0, 30):
                raise forms.ValidationError("Appointments start on the hour or half hour (30-minute slots).")
            if data.get("doctor") and not within_hours(data["doctor"], day, clock):
                raise forms.ValidationError("This appointment is outside the doctor's availability. Check their listed hours.")
            slots = Appointment.objects.filter(appointment_date=day, appointment_time=clock).exclude(
                status=Appointment.Status.CANCELLED).exclude(pk=self.instance.pk)
            if data.get("doctor") and slots.filter(doctor=data["doctor"]).exists():
                raise forms.ValidationError("That doctor already has an appointment at this time.")
            if self.instance.patient_id and slots.filter(patient_id=self.instance.patient_id).exists():
                raise forms.ValidationError("You already have an appointment at this time.")
        return data


class AssignmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ["doctor"]

    def clean_doctor(self):
        doctor = self.cleaned_data["doctor"]
        if self.instance.prescriptions.exists():
            raise forms.ValidationError("Cannot reassign an appointment after a prescription has been recorded.")
        if not within_hours(doctor, self.instance.appointment_date, self.instance.appointment_time):
            raise forms.ValidationError("That doctor is not available during this appointment.")
        if Appointment.objects.filter(doctor=doctor, appointment_date=self.instance.appointment_date,
                                      appointment_time=self.instance.appointment_time).exclude(
                status=Appointment.Status.CANCELLED).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("That doctor is already booked at this time.")
        return doctor


class PrescriptionForm(forms.ModelForm):
    class Meta:
        model = Prescription
        fields = ["medicine", "dosage", "frequency", "duration", "instructions"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["medicine"].queryset = Medicine.objects.filter(active=True)
