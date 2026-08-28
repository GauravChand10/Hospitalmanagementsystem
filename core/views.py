from django.shortcuts import render
from departments.models import Department
from doctors.models import Doctor
from billing.esewa import configured_fee, PaymentError


def home(request):
    try:
        fee = configured_fee()
    except PaymentError:
        fee = None
    context = {
        "department_count": Department.objects.count(),
        "doctor_count": Doctor.objects.count(),
        "doctors": Doctor.objects.select_related("department").prefetch_related("availability").order_by("first_name", "pk")[:6],
        "departments": Department.objects.order_by("name")[:8],
        "appointment_fee": fee,
    }

    return render(request, "home.html", context)
