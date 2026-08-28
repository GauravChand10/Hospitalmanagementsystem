from django.contrib import admin
from .models import Doctor


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = (
        "first_name",
        "last_name",
        "department",
        "specialization",
        "phone",
        "email",
    )

    search_fields = (
        "first_name",
        "last_name",
        "specialization",
    )

    list_filter = (
        "department",
    )