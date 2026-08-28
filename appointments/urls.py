from django.urls import path
from . import views

urlpatterns = [
    path("", views.appointment_list, name="appointment_list"),
    path("profile/", views.patient_profile, name="patient_profile"),
    path("book/", views.book_appointment, name="book_appointment"),
    path("prescriptions/", views.my_prescriptions, name="my_prescriptions"),
    path("<int:pk>/", views.appointment_detail, name="appointment_detail"),
    path("<int:pk>/cancel/", views.cancel_appointment, name="cancel_appointment"),
    path("<int:pk>/assign/", views.assign_doctor, name="assign_doctor"),
    path("<int:pk>/prescribe/", views.prescribe, name="prescribe"),
    path("<int:pk>/complete/", views.complete_appointment, name="complete_appointment"),
]
