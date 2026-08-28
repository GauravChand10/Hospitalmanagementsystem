from django.shortcuts import render
from departments.models import Department
from doctors.models import Doctor
from patients.models import Patient
from appointments.models import Appointment


def home(request):
    context = {
        "department_count": Department.objects.count(),
        "doctor_count": Doctor.objects.count(),
        "patient_count": Patient.objects.count(),
        "appointment_count": Appointment.objects.count(),
    }

    return render(request, "home.html", context)