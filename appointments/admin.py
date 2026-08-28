from django.contrib import admin
from .models import Appointment


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    # Use the workflow pages so admin edits cannot bypass assignment/status rules.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    list_display = (
        "patient",
        "doctor",
        "appointment_date",
        "appointment_time",
        "status",
    )

    search_fields = (
        "patient__first_name",
        "patient__last_name",
        "doctor__first_name",
        "doctor__last_name",
    )

    list_filter = (
        "status",
        "appointment_date",
        "doctor",
    )
