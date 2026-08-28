import uuid

from django.contrib import messages
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.cache import never_cache

from appointments.permissions import workflow_access, is_patient
from django.core.exceptions import PermissionDenied
from .models import Payment
from .esewa import PaymentError, FORM_URL, checkout_fields, decode_callback
from .services import confirm_payment, expire_holds


def owned_payment(request, pk):
    if not is_patient(request.user):
        raise PermissionDenied
    return get_object_or_404(Payment.objects.select_related("appointment"), appointment_id=pk,
                             appointment__patient__user=request.user)


@never_cache
@workflow_access
@require_POST
def checkout(request, pk):
    expire_holds()
    payment = owned_payment(request, pk)
    if payment.status != Payment.Status.PENDING or payment.appointment.status != "Awaiting payment":
        messages.error(request, "This booking is not awaiting payment. Check its current status.")
        return redirect("appointment_detail", pk=pk)
    try:
        fields = checkout_fields(payment)
    except PaymentError as error:
        messages.error(request, str(error))
        return redirect("appointment_detail", pk=pk)
    return render(request, "billing/checkout.html", {"payment": payment, "fields": fields, "form_url": FORM_URL})


@never_cache
@require_GET
def esewa_success(request):
    try:
        data = decode_callback(request.GET.get("data", ""))
        transaction_uuid = uuid.UUID(str(data["transaction_uuid"]))
        payment = get_object_or_404(Payment, transaction_uuid=transaction_uuid)
        payment = confirm_payment(payment, data)
    except (PaymentError, ValueError) as error:
        return HttpResponseBadRequest(str(error) if isinstance(error, PaymentError) else "Invalid payment reference.")
    messages.info(request, payment.get_status_display())
    return redirect("appointment_detail", pk=payment.appointment_id)


@never_cache
@require_GET
def esewa_failure(request):
    # A browser redirect alone cannot prove payment failed or release a paid slot.
    messages.warning(request, "Payment was not confirmed. Open the appointment and check payment status before trying again.")
    return redirect("appointment_list")


@never_cache
@workflow_access
@require_POST
def check_payment(request, pk):
    payment = owned_payment(request, pk)
    try:
        payment = confirm_payment(payment)
        messages.info(request, payment.get_status_display())
    except PaymentError as error:
        messages.error(request, str(error))
    expire_holds()
    return redirect("appointment_detail", pk=pk)
