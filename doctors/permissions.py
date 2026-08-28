from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from accounts.models import User


def can_manage_doctors(user):
    return user.is_authenticated and user.is_active and (
        user.is_superuser or user.role == User.Role.ADMIN
    )


def doctor_management_required(view):
    @login_required(login_url="login")
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not can_manage_doctors(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped
