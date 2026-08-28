from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from patients.models import Patient
from doctors.models import Doctor
from .forms import AssignmentForm, BookingForm, PatientProfileForm, PrescriptionForm
from .models import Appointment
from .permissions import is_patient, is_scheduler, visible_appointments, workflow_access
from billing.esewa import configured_fee, PaymentError
from billing.models import Payment
from billing.services import create_payment, expire_holds, cancel_payment


@workflow_access
def patient_profile(request):
    if not is_patient(request.user):
        raise PermissionDenied
    profile = Patient.objects.filter(user=request.user).first()
    form = PatientProfileForm(request.POST if request.method == "POST" else None, instance=profile)
    if request.method == "POST" and form.is_valid():
        profile = form.save(commit=False)
        profile.user = request.user
        try:
            with transaction.atomic():
                profile.save()
        except IntegrityError:
            form.add_error(None, "A profile with these details already exists. Contact reception to link an existing record.")
        else:
            messages.success(request, "Your patient profile has been saved.")
            return redirect("appointment_list")
    return render(request, "appointments/form.html", {"form": form, "title": "My Patient Profile"})


@workflow_access
def appointment_list(request):
    expire_holds()
    return render(request, "appointments/list.html", {
        "appointments": visible_appointments(request.user),
        "is_patient": is_patient(request.user),
    })


@workflow_access
def book_appointment(request):
    if not is_patient(request.user):
        raise PermissionDenied
    expire_holds()
    patient = Patient.objects.filter(user=request.user).first()
    if patient is None:
        messages.info(request, "Complete your patient profile before booking.")
        return redirect("patient_profile")
    form = BookingForm(request.POST if request.method == "POST" else None,
                       initial={key: request.GET.get(key, "") for key in ("doctor", "appointment_date", "appointment_time")},
                       instance=Appointment(patient=patient))
    try:
        fee = configured_fee()
    except PaymentError as error:
        return render(request, "appointments/form.html", {
            "form": form, "title": "Book an Appointment", "blocked": True,
            "help_text": str(error),
        })
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                # Serialize with availability edits, then recheck hours before saving.
                Doctor.objects.select_for_update().get(pk=form.cleaned_data["doctor"].pk)
                form.full_clean()
                appointment = None
                if form.is_valid():
                    appointment = form.save(commit=False)
                    appointment.status = Appointment.Status.AWAITING_PAYMENT
                    appointment.save()
                    create_payment(appointment, fee)
        except IntegrityError:
            form.add_error(None, "This time slot was just booked. Please choose another time.")
        else:
            if appointment is not None:
                messages.info(request, "Slot held for 15 minutes. Complete sandbox eSewa payment to confirm your appointment.")
                return redirect("appointment_detail", pk=appointment.pk)
    return render(request, "appointments/form.html", {
        "form": form, "title": "Book an Appointment",
        "help_text": f"Fee: NPR {fee:.2f} (eSewa sandbox only). Choose a future 30-minute slot; complete payment within 15 minutes to confirm. Times use the hospital timezone.",
    })


@workflow_access
def appointment_detail(request, pk):
    expire_holds()
    appointment = get_object_or_404(visible_appointments(request.user), pk=pk)
    pending = appointment.status == Appointment.Status.PENDING
    assigned = (request.user.role == "DOCTOR" and appointment.doctor.user_id == request.user.pk)
    payment = Payment.objects.filter(appointment=appointment).first()
    return render(request, "appointments/detail.html", {
        "appointment": appointment,
        "prescriptions": appointment.prescriptions.select_related("medicine", "doctor"),
        "payment": payment,
        "can_pay": is_patient(request.user) and payment is not None and payment.status == Payment.Status.PENDING
                   and appointment.status == Appointment.Status.AWAITING_PAYMENT,
        "can_check_payment": is_patient(request.user) and payment is not None,
        "can_cancel": appointment.status in (Appointment.Status.PENDING, Appointment.Status.AWAITING_PAYMENT) and not appointment.prescriptions.exists() and (
            is_patient(request.user) or is_scheduler(request.user)),
        "can_assign": pending and is_scheduler(request.user) and not appointment.prescriptions.exists(),
        "can_prescribe": pending and assigned,
        "can_complete": pending and assigned,
    })


@workflow_access
@require_POST
def cancel_appointment(request, pk):
    with transaction.atomic():
        appointment = get_object_or_404(visible_appointments(request.user).select_for_update(), pk=pk)
        if not (is_patient(request.user) or is_scheduler(request.user)):
            raise PermissionDenied
        if appointment.status not in (Appointment.Status.PENDING, Appointment.Status.AWAITING_PAYMENT) or appointment.prescriptions.exists():
            messages.error(request, "Only pending appointments without prescriptions can be cancelled.")
        else:
            cancel_payment(appointment)
            appointment.status = Appointment.Status.CANCELLED
            appointment.save(update_fields=["status"])
            messages.success(request, "Appointment cancelled. Any verified payment requires manual refund review; no automatic refund has been issued.")
    return redirect("appointment_detail", pk=pk)


@workflow_access
def assign_doctor(request, pk):
    if not is_scheduler(request.user):
        raise PermissionDenied
    with transaction.atomic():
        appointment = get_object_or_404(visible_appointments(request.user).select_for_update(), pk=pk)
        if appointment.status != Appointment.Status.PENDING:
            messages.error(request, "Only pending appointments can be reassigned.")
            return redirect("appointment_detail", pk=pk)
        form = AssignmentForm(request.POST if request.method == "POST" else None, instance=appointment)
        if request.method == "POST" and form.is_valid():
            try:
                with transaction.atomic():
                    Doctor.objects.select_for_update().get(pk=form.cleaned_data["doctor"].pk)
                    form.full_clean()
                    saved = form.is_valid()
                    if saved:
                        form.save()
            except IntegrityError:
                form.add_error(None, "That doctor is already booked. Choose another doctor.")
            else:
                if saved:
                    messages.success(request, "Doctor assigned.")
                    return redirect("appointment_detail", pk=pk)
    return render(request, "appointments/form.html", {"form": form, "title": "Assign Doctor"})


@workflow_access
def prescribe(request, pk):
    with transaction.atomic():
        appointment = get_object_or_404(visible_appointments(request.user).select_for_update(), pk=pk)
        if request.user.role != "DOCTOR" or appointment.doctor.user_id != request.user.pk:
            raise PermissionDenied
        if appointment.status != Appointment.Status.PENDING:
            messages.error(request, "Prescriptions can only be added to pending appointments.")
            return redirect("appointment_detail", pk=pk)
        form = PrescriptionForm(request.POST if request.method == "POST" else None)
        if request.method == "POST" and form.is_valid():
            prescription = form.save(commit=False)
            prescription.appointment = appointment
            prescription.doctor = appointment.doctor
            prescription.save()
            messages.success(request, "Prescription recorded.")
            return redirect("appointment_detail", pk=pk)
    return render(request, "appointments/form.html", {
        "form": form, "title": "Record Prescription",
        "help_text": "Enter the prescribing doctor's instructions. Add each medicine separately. If the catalog is empty, ask an administrator to add medicines.",
    })


@workflow_access
@require_POST
def complete_appointment(request, pk):
    with transaction.atomic():
        appointment = get_object_or_404(visible_appointments(request.user).select_for_update(), pk=pk)
        if request.user.role != "DOCTOR" or appointment.doctor.user_id != request.user.pk:
            raise PermissionDenied
        if appointment.status == Appointment.Status.PENDING:
            appointment.status = Appointment.Status.COMPLETED
            appointment.save(update_fields=["status"])
            messages.success(request, "Appointment completed.")
        else:
            messages.error(request, "Only pending appointments can be completed.")
    return redirect("appointment_detail", pk=pk)


@workflow_access
def my_prescriptions(request):
    if not is_patient(request.user):
        raise PermissionDenied
    from prescriptions.models import Prescription
    prescriptions = Prescription.objects.filter(appointment__patient__user=request.user).select_related(
        "appointment", "medicine", "doctor").order_by("-created_at")
    return render(request, "appointments/prescriptions.html", {"prescriptions": prescriptions})
