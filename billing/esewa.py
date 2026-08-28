"""eSewa ePay v2 sandbox protocol. Never send production credentials here."""
import base64
import hashlib
import hmac
import json
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, urlsplit
from urllib.request import build_opener, HTTPRedirectHandler
from urllib.error import URLError

from django.conf import settings
from django.urls import reverse

FORM_URL = "https://rc-epay.esewa.com.np/api/epay/main/v2/form"
# eSewa's /pages/Epay documents this working sandbox verification host.
# The alternative uat host in /pages/Epay-V2 currently fails DNS resolution.
STATUS_URL = "https://rc.esewa.com.np/api/epay/transaction/status/"
# Public sandbox credential published by eSewa, not a production secret.
SANDBOX_KEY = "8gBm/:&EnhH.1/q"
REQUEST_FIELDS = "total_amount,transaction_uuid,product_code"
RESPONSE_FIELDS = {"transaction_code", "status", "total_amount", "transaction_uuid", "product_code", "signed_field_names"}


class PaymentError(Exception):
    pass


def money(value):
    try:
        amount = Decimal(str(value).replace(",", ""))
        if not amount.is_finite() or amount <= 0 or amount > Decimal("99999999.99"):
            raise PaymentError("Invalid payment amount.")
        if amount != amount.quantize(Decimal("0.01")):
            raise PaymentError("Amounts must have at most two decimal places.")
        return amount
    except (InvalidOperation, ValueError, TypeError):
        raise PaymentError("Invalid payment amount.") from None


def configured_fee():
    try:
        return money(settings.APPOINTMENT_FEE_NPR)
    except PaymentError:
        raise PaymentError("Online booking is not ready: the appointment fee has not been configured. Contact reception.") from None


def signature(data, field_names):
    message = ",".join(f"{name}={data[name]}" for name in field_names.split(","))
    digest = hmac.new(SANDBOX_KEY.encode(), message.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def checkout_fields(payment):
    origin = settings.ESEWA_RETURN_ORIGIN.rstrip("/")
    parts = urlsplit(origin)
    if (parts.scheme not in ("http", "https") or not parts.netloc or parts.path or
            parts.query or parts.fragment or parts.username or parts.password):
        raise PaymentError("Configure a valid payment return origin.")
    if payment.product_code != "EPAYTEST":
        raise PaymentError("Only sandbox payments are supported.")
    amount = format(payment.amount, ".2f")
    data = {"amount": amount, "total_amount": amount, "tax_amount": "0",
            "product_service_charge": "0", "product_delivery_charge": "0",
            "transaction_uuid": str(payment.transaction_uuid), "product_code": payment.product_code,
            "success_url": origin + reverse("esewa_success"),
            "failure_url": origin + reverse("esewa_failure"), "signed_field_names": REQUEST_FIELDS}
    data["signature"] = signature(data, REQUEST_FIELDS)
    return data


def decode_callback(encoded):
    try:
        if not encoded or len(encoded) > 16000:
            raise ValueError
        data = json.loads(base64.b64decode(encoded, validate=True), parse_float=str)
        if not isinstance(data, dict):
            raise ValueError
        names = data["signed_field_names"]
        if not isinstance(names, str) or set(names.split(",")) != RESPONSE_FIELDS or len(names.split(",")) != 6:
            raise ValueError
        if any(not isinstance(data[name], (str, int)) for name in RESPONSE_FIELDS):
            raise ValueError
        if not hmac.compare_digest(str(data["signature"]).encode(), signature(data, names).encode()):
            raise ValueError
        if data["status"] != "COMPLETE" or data["product_code"] != "EPAYTEST":
            raise ValueError
        money(data["total_amount"])
        return data
    except (ValueError, KeyError, TypeError, UnicodeError, PaymentError):
        raise PaymentError("The payment response could not be authenticated.") from None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PaymentError("Unexpected redirect from payment verification service.")


def fetch_status(payment):
    query = urlencode({"product_code": payment.product_code, "total_amount": format(payment.amount, ".2f"),
                       "transaction_uuid": str(payment.transaction_uuid)})
    try:
        with build_opener(NoRedirect).open(STATUS_URL + "?" + query, timeout=10) as response:
            data = json.loads(response.read(65537))
        if not isinstance(data, dict):
            raise ValueError
        return data
    except (URLError, OSError, ValueError):
        raise PaymentError("eSewa verification is unavailable. Do not pay again; use Check Payment Status later.") from None


def verify_status(payment, callback=None):
    result = fetch_status(payment)
    # eSewa documentation shows both naming conventions for this response.
    uuid = result.get("transaction_uuid", result.get("pid"))
    product = result.get("product_code", result.get("scd"))
    amount = result.get("total_amount", result.get("totalAmount"))
    reference = result.get("ref_id", result.get("refId"))
    if result.get("status") != "COMPLETE":
        raise PaymentError("eSewa has not verified a completed payment. Do not pay again if your wallet was debited; check the status later.")
    if (str(uuid) != str(payment.transaction_uuid) or product != payment.product_code or
            money(amount) != payment.amount or not isinstance(reference, str) or not reference or len(reference) > 100):
        raise PaymentError("The payment details did not match this booking.")
    if callback and (str(callback["transaction_uuid"]) != str(payment.transaction_uuid) or
                     callback["product_code"] != payment.product_code or money(callback["total_amount"]) != payment.amount or
                     callback["transaction_code"] != reference):
        raise PaymentError("The payment response did not match eSewa verification.")
    return reference
