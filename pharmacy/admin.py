from django.contrib import admin

from .models import Medicine

@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = ("name", "strength", "active")
    search_fields = ("name", "strength")
