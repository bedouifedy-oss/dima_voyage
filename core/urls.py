from django.urls import path

from . import views

urlpatterns = [
    # Linked from: Admin > "Send WhatsApp" button
    path("visa-form/<str:ref>/", views.public_visa_form, name="public_visa_form"),
    # Linked from: Admin > "Print Invoice" button
    path("invoice/<int:booking_id>/", views.invoice_pdf, name="invoice_pdf"),
    # Success Page
    path("visa-success/", views.visa_success, name="visa_success"),
]
