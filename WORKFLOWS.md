# Appointment and prescription workflow

## Included in this phase

- Patients complete their own profile, book a doctor in a future 30-minute slot,
  list their appointments, cancel pending appointments without prescriptions,
  and read their prescriptions.
- Receptionists and Admin-role users can view appointments and reassign pending
  appointments, provided the new doctor is free and no prescription exists yet.
- A Doctor-role account can view only appointments assigned to its linked Doctor
  record, add prescriptions, and mark a consultation completed.
- Only the assigned doctor can prescribe, not an administrator or receptionist.
- Medicines are a manually maintained catalog, not generated treatment advice.
- Appointment histories are protected from patient/doctor deletion. Cancelled
  appointments release their slots; completed appointments remain in history.
- The Django admin appointment screen is read-only to preserve workflow checks.

## One-time setup by an administrator

1. Sign in to `/admin/` with an active staff/superuser account.
2. Under Accounts / Users, create accounts and choose their hospital roles.
   `is_staff` separately controls access to Django admin; the hospital Admin role
   alone does not grant Django admin access. Clinical users do not need `is_staff`.
3. Edit each Doctor record and choose its corresponding Doctor-role user.
   Each account can be linked to only one doctor. Unlinked doctor accounts see
   no appointments until linked.
4. Under Pharmacy / Medicines, enter medicine names and strengths. Use the
   Active flag to stop offering a medicine for new prescriptions.
5. Link existing Patient records to the correct patient accounts after verifying
   identity. Email matching never automatically claims an existing medical record.
   New patients can create their own profile from My Dashboard / My Profile.

## Try the flow

1. Patient: sign in, complete My Profile, and select Book Appointment.
2. Choose a doctor, future date, and a time ending in `:00` or `:30`.
3. Receptionist/Admin: open Appointments, choose a booking, and optionally Assign Doctor.
4. Assigned doctor: open Appointments, record each medicine with clinician-entered
   dosage, frequency, duration, and instructions, then Mark Completed.
5. Patient: open My Prescriptions to read those instructions.

Appointment times currently use the existing `UTC` setting in
`hospital_management/settings.py`. Admin-role users and superusers can open
Doctors / View Details / Manage Availability to set one working window per weekday.
No configured hours means unavailable; existing doctors are not assigned guessed
hours. Set hours covering existing future appointments before saving a schedule.
Visitors can check a date on a doctor's detail page and choose a free 30-minute
slot. Booking and reassignment both validate the full slot against weekly hours.
Hours cannot be changed to exclude an existing pending future appointment.
Split shifts, leave, and holidays are not implemented.
Do not treat this as production-ready clinical software.

## How availability works in the code

- `doctors/models.py`: `DoctorAvailability` stores a doctor, weekday, opening time,
  and closing time. A foreign key connects each window to its doctor; a unique
  constraint prevents two conflicting windows for the same weekday.
- `doctors/availability_forms.py`: `WeeklyAvailabilityForm` validates admin input,
  rejects invalid hours, and checks that existing bookings remain covered.
- `doctors/scheduling.py`: `within_hours()` checks that the full 30-minute visit
  fits a window; `available_slots()` generates slots and removes booked/past ones.
- `appointments/forms.py`: booking and assignment call the same validator so
  changing a URL or submitting a custom form cannot bypass availability checks.
- `doctors/views.py`: the admin-protected editor saves hours. The public detail
  view displays hours and free slots without exposing patient information.
- Templates display those results. They are not trusted to enforce permissions.
- Database migrations create the new table without deleting existing appointments.

## eSewa sandbox payments

The sandbox integration uses a default appointment fee of NPR 500.00.
An explicitly empty or invalid `APPOINTMENT_FEE_NPR` blocks new booking.
Existing bookings are preserved and are not retroactively charged.

To override the default, set `APPOINTMENT_FEE_NPR` in the environment before starting
Django. This project does not automatically load `.env` files. Also set
`ESEWA_RETURN_ORIGIN` if the browser is not using `http://127.0.0.1:8010`.
The return origin is trusted server configuration, not taken from a submitted form
or arbitrary Host header. Restart the server after changing settings.

This implementation is **sandbox-only**: it uses eSewa's published EPAYTEST merchant,
public test signing key, test checkout, and test verification endpoints. Never
enter a real wallet login. There is no switch to enable real-money payments.
The official test accounts are documented at:
https://developer.esewa.com.np/pages/Test-credentials
The ePay v2 protocol is documented at:
https://developer.esewa.com.np/pages/Epay-V2

### Booking/payment lifecycle

1. The server validates doctor availability, snapshots the configured fee, and
   creates an appointment marked `Awaiting payment` plus its own unique payment UUID.
2. The slot is held for 15 minutes. The patient opens Pay with eSewa (Sandbox).
3. The server signs the stored amount, UUID, and merchant code with HMAC-SHA256.
   The resulting signature is sent to eSewa; the signing key never goes to the browser.
4. eSewa returns a base64 response. Base64 is encoding, **not** security. The server
   verifies the response signature, then separately asks eSewa's status API whether
   the transaction completed. Amount, UUID, merchant, and reference must match.
5. Only then does the appointment become `Pending` (confirmed, awaiting consultation)
   and the payment become `PAID` (sandbox). Duplicate callbacks leave it unchanged.
6. A failed redirect or network timeout cannot claim success. The patient can use
   Check Payment Status if payment was submitted but the callback was lost.
7. Expired holds are released when availability, booking, appointments, or payment
   pages trigger cleanup. A late verified payment becomes `REVIEW`; it cannot reclaim
   a cancelled/reallocated slot. Paid cancellations also become `REVIEW`.

### Code concepts

- `billing/models.py`: a OneToOneField gives each booking one payment record.
  DecimalField stores money without floating-point rounding errors. The UUID
  identifies the transaction without sending patient details to eSewa.
- `billing/esewa.py`: signing, strict response validation, and server-to-server
  status checking. Browser-supplied prices are ignored.
- `billing/services.py`: transaction-safe payment confirmation and hold expiry.
  Idempotency means processing the same successful response twice does not book twice.
- `billing/views.py`: owner-only checkout/status controls and the eSewa return routes.
- `appointments/views.py`: creates the payment and booking atomically, so a failure
  cannot leave a new booking without its payment record.
- `billing/tests.py`: mocked provider responses test tampering, replay, expiry,
  ownership, timeouts, and late payment without moving money.

Automated tests mock the provider; they do not transfer money. A user-initiated
NPR 500 sandbox payment was independently verified as COMPLETE on 2026-08-28.
Verification uses `https://rc.esewa.com.np/api/epay/transaction/status/`, documented
on eSewa's `/pages/Epay`; the `uat` alternative failed DNS resolution locally.
The Django process needs outbound HTTPS access for verification. A server launched
in a network-restricted sandbox cannot perform the check, even if browser checkout works.
Refunds and periodic provider reconciliation are not automated. `REVIEW` does not
mean money was refunded. Real payments require a separate production integration,
merchant onboarding, HTTPS, secure deployment settings, reconciliation/refund
procedures, and production-capable concurrency/abuse controls.

## Not included yet

Billing, lab reports, support tickets, medicine inventory/dispensing, notifications,
clinical audit logs, prescription revisions, and staff booking on behalf of a
patient are subsequent phases. Existing deployment security issues still need
to be addressed before exposing the app or using real patient data.

## Checks

Run `.venv\Scripts\python.exe manage.py test` for authorization, ownership,
booking conflict, profile, prescription, and navigation tests.
