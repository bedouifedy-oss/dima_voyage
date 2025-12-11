# core/urls.py
from django.urls import path

from . import views

urlpatterns = [
    # --- Healthcheck ---
    path("healthz/", views.healthz, name="healthz"),
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
    path("dashboard/", views.financial_dashboard, name="financial_dashboard"),
    path("productivity/", views.productivity_dashboard, name="productivity_dashboard"),
    # --- Client Features (Public) ---
    # The public form sent via WhatsApp
    path("visa-form/<str:ref>/", views.public_visa_form, name="public_visa_form"),
    # Success page after submission
    path("visa-success/", views.visa_success, name="visa_success"),
    # --- Tools Hub & Dynamic Document Engine ---
    path("tools/", views.tools_hub, name="tools_hub"),
    path(
        "tools/generate/<str:slug>/",
        views.document_tool_view,
        name="document_tool",
    ),
    path(
        "tools/print/<int:doc_id>/",
        views.print_document_view,
        name="print_document",
    ),
    path(
        "tools/upload-image/",
        views.tool_image_upload,
        name="tool_image_upload",
    ),
]
