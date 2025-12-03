# core/urls.py
from django.urls import path

from . import views

urlpatterns = [
    # --- Admin Features ---
    # The new Configuration Page for Visa fields
    path(
        "operations/configure-visa/<int:booking_id>/",
        views.configure_visa_form,
        name="admin_configure_visa",
    ),
    # Invoice PDF generation
    path("invoice/<int:booking_id>/", views.invoice_pdf, name="invoice_pdf"),
    # Airport Autocomplete (Required for FlightTicket Inline)
    path(
        "api/airport-autocomplete/",
        views.airport_autocomplete,
        name="airport_autocomplete",
    ),
    # --- Client Features (Public) ---
    # The public form sent via WhatsApp
    path("visa-form/<str:ref>/", views.public_visa_form, name="public_visa_form"),
    # Success page after submission
    path("visa-success/", views.visa_success, name="visa_success"),
]
