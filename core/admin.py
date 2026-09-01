from django.contrib import admin

from .models import AmbulanceRequest


@admin.register(AmbulanceRequest)
class AmbulanceRequestAdmin(admin.ModelAdmin):
    list_display = ("reference", "service_type", "patient_name", "phone", "status", "created_at")
    list_filter = ("service_type", "status", "created_at")
    search_fields = ("patient_name", "phone", "pickup_location", "reference")
    readonly_fields = ("reference", "created_at")

# Register your models here.
