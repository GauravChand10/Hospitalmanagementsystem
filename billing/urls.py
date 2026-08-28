from django.urls import path
from . import views

urlpatterns = [
    path("esewa/success/", views.esewa_success, name="esewa_success"),
    path("esewa/failure/", views.esewa_failure, name="esewa_failure"),
    path("appointments/<int:pk>/pay/", views.checkout, name="esewa_checkout"),
    path("appointments/<int:pk>/check/", views.check_payment, name="check_payment"),
]
