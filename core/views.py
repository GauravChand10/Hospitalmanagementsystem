from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from departments.models import Department
from doctors.models import Doctor
from billing.esewa import configured_fee, PaymentError
from .forms import AmbulanceRequestForm


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


def ambulance_request(request):
    initial = {}
    requested_service = request.GET.get("service")
    if requested_service in {choice for choice, _ in AmbulanceRequestForm.base_fields["service_type"].choices}:
        initial["service_type"] = requested_service

    if request.method == "POST":
        form = AmbulanceRequestForm(request.POST)
        last_request = request.session.get("ambulance_request_at")
        too_soon = last_request and timezone.now().timestamp() - last_request < 60
        if too_soon:
            form.add_error(None, "Please wait one minute before sending another ambulance request.")
        elif form.is_valid():
            ambulance = form.save()
            request.session["ambulance_request_at"] = timezone.now().timestamp()
            messages.success(
                request,
                f"Request received. Reference {str(ambulance.reference)[:8].upper()}. Hospital staff must confirm availability by phone.",
            )
            return redirect("ambulance_request")
    else:
        form = AmbulanceRequestForm(initial=initial)

    return render(request, "ambulance_request.html", {"form": form})
