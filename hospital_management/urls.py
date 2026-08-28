from django.contrib import admin
from django.urls import path, include
from core import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.home, name="home"),
    path("doctors/", include("doctors.urls")),
    path("accounts/", include("accounts.urls")),
    path("appointments/", include("appointments.urls")),
    path("billing/", include("billing.urls")),
]
