from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from accounts.models import User


def is_patient(user):
    return user.is_authenticated and user.is_active and user.role == User.Role.PATIENT and not user.is_superuser


def is_scheduler(user):
    return user.is_authenticated and user.is_active and (
        user.is_superuser or user.role in (User.Role.ADMIN, User.Role.RECEPTIONIST))


def workflow_access(view):
    @login_required(login_url="login")
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_active or not (
            is_patient(request.user) or is_scheduler(request.user) or request.user.role == User.Role.DOCTOR
        ):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped


def visible_appointments(user):
    from .models import Appointment
    appointments = Appointment.objects.select_related("patient", "doctor", "doctor__department")
    if is_scheduler(user):
        return appointments
    if is_patient(user):
        return appointments.filter(patient__user=user)
    if user.role == User.Role.DOCTOR:
        return appointments.filter(doctor__user=user)
    return appointments.none()
