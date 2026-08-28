from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models.deletion import ProtectedError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from .availability_forms import WeeklyAvailabilityForm
from .scheduling import available_slots
from .models import Doctor
from .forms import DoctorForm
from .permissions import can_manage_doctors, doctor_management_required


def doctor_list(request):
    doctors = Doctor.objects.all()

    context = {
        "doctors": doctors,
        "can_manage_doctors": can_manage_doctors(request.user),
    }

    return render(request, "doctors/doctor_list.html", context)


@doctor_management_required
def doctor_delete(request, id):

    doctor = get_object_or_404(Doctor, id=id)

    if request.method == "POST":
        try:
            doctor.delete()
        except ProtectedError:
            messages.error(request, "This doctor has appointment or prescription history and cannot be deleted.")
            return redirect("doctor_detail", id=doctor.id)
        return redirect("doctor_list")

    context = {
        "doctor": doctor
    }

    return render(
        request,
        "doctors/doctor_confirm_delete.html",
        context
    )

def doctor_detail(request, id):
    doctor = get_object_or_404(Doctor, id=id)
    try:
        selected_date = parse_date(request.GET.get("date", "")) or timezone.localdate()
    except ValueError:
        selected_date = timezone.localdate()

    context = {
        "doctor": doctor,
        "can_manage_doctors": can_manage_doctors(request.user),
        "hours": doctor.availability.all(),
        "selected_date": selected_date,
        "slots": available_slots(doctor, selected_date),
    }

    return render(request, "doctors/doctor_detail.html", context)


@doctor_management_required
def doctor_availability(request, id):
    from billing.services import expire_holds
    expire_holds()
    with transaction.atomic():
        doctor = get_object_or_404(Doctor.objects.select_for_update(), id=id)
        form = WeeklyAvailabilityForm(request.POST if request.method == "POST" else None, doctor=doctor)
        if request.method == "POST" and form.is_valid():
            form.save()
            messages.success(request, "Weekly availability saved.")
            return redirect("doctor_detail", id=doctor.pk)
    return render(request, "doctors/availability_form.html", {"doctor": doctor, "form": form})



@doctor_management_required
def doctor_create(request):

    if request.method == "POST":

        form = DoctorForm(request.POST)

        if form.is_valid():
            form.save()
            return redirect("doctor_list")

    else:
        form = DoctorForm()

    context = {
        "form": form
    }

    return render(request, "doctors/doctor_form.html", context)
@doctor_management_required
def doctor_edit(request, id):

    doctor = get_object_or_404(Doctor, id=id)

    if request.method == "POST":

        form = DoctorForm(request.POST, instance=doctor)

        if form.is_valid():
            form.save()
            return redirect("doctor_detail", id=doctor.id)

    else:
        form = DoctorForm(instance=doctor)

    context = {
        "form": form,
        "doctor": doctor
    }

    return render(request, "doctors/doctor_form.html", context)
    path("<int:id>/delete/", views.doctor_delete, name="doctor_delete"),
    
