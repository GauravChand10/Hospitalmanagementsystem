from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_POST
from .models import User


def login_view(request):

    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        # Check if user exists
        if not User.objects.filter(username=username).exists():

            return render(
                request,
                "accounts/login.html",
                {"error": "User does not exist."}
            )

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:

            login(request, user)

            if user.is_superuser:
                return redirect("/admin/")

            if user.role == User.Role.PATIENT:
                return redirect("patient_dashboard")

            elif user.role == User.Role.DOCTOR:
                return redirect("appointment_list")

            elif user.role == User.Role.RECEPTIONIST:
                return redirect("appointment_list")

            elif user.role == User.Role.ADMIN:
                return redirect("appointment_list")

            else:
                return redirect("home")

        else:

            return render(
                request,
                "accounts/login.html",
                {"error": "Incorrect password."}
            )

    return render(request, "accounts/login.html")

def register_view(request):

    if request.method == "POST":

        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")

        if User.objects.filter(username=username).exists():

            return render(
                request,
                "accounts/register.html",
                {"error": "Username already exists"}
            )

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            role=User.Role.PATIENT
        )

        login(request, user)

        return redirect("patient_dashboard")

    return render(request, "accounts/register.html")
   



@login_required(login_url="login")
def patient_dashboard(request):
    if request.user.role != User.Role.PATIENT or request.user.is_superuser:
        raise PermissionDenied
    return render(request, "accounts/patient_dashboard.html")


@require_POST
def logout_view(request):

    logout(request)

    return redirect("home")
