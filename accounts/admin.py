from django.contrib import admin

from django.contrib.auth.admin import UserAdmin
from .models import User

@admin.register(User)
class HospitalUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Hospital role", {"fields": ("role",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Hospital role", {"fields": ("role",)}),)
    list_display = UserAdmin.list_display + ("role",)
