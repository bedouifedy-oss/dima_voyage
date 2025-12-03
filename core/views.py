# core/views.py
import weasyprint
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.template.loader import render_to_string

from .forms import VisaForm, VisaFieldConfigurationForm
from .models import Booking, VisaApplication
from .utils import search_airports
from .utils import send_visa_whatsapp


@staff_member_required
def configure_visa_form(request, booking_id):
    """
    Admin View: Allows staff to select fields AND send the message in one go.
    """
    booking = get_object_or_404(Booking, pk=booking_id)
    
    if request.method == 'POST':
        form = VisaFieldConfigurationForm(request.POST)
        if form.is_valid():
            # 1. ALWAYS SAVE CONFIGURATION (Even if cancelling send)
            selection = form.cleaned_data['selected_fields'] + ['passport_number', 'photo']
            booking.visa_form_config = selection
            booking.save()
            
            # 2. CHECK WHICH BUTTON WAS CLICKED
            
            # Case A: Send Tunisian
            if "_send_tn" in request.POST:
                success, msg = send_visa_whatsapp(request, booking, 'tn')
                if success:
                    messages.success(request, f"✅ Configuration Saved & 🇹🇳 Message Sent!")
                else:
                    messages.error(request, msg)
                    
            # Case B: Send French
            elif "_send_fr" in request.POST:
                success, msg = send_visa_whatsapp(request, booking, 'fr')
                if success:
                    messages.success(request, f"✅ Configuration Saved & 🇫🇷 Message Sent!")
                else:
                    messages.error(request, msg)
            
            # Case C: Cancel / Save Only
            else:
                messages.info(request, "💾 Configuration saved (No message sent).")

            return redirect(f'/admin/core/booking/{booking.id}/change/')
    else:
        # Pre-fill
        initial_data = [f for f in booking.visa_form_config if f not in ['passport_number', 'photo']]
        form = VisaFieldConfigurationForm(initial={'selected_fields': initial_data})

    return render(request, 'admin/core/booking/configure_form.html', {
        'form': form,
        'booking': booking
    })

def invoice_pdf(request, booking_id):
    # 1. Get the booking
    booking = get_object_or_404(Booking, id=booking_id)

    # 2. Context data for the template
    context = {
        "booking": booking,
        "user": request.user,
        "base_url": request.build_absolute_uri("/")[:-1],  # Helps images load in PDF
    }

    # 3. Render HTML to string
    html_string = render_to_string("core/invoice.html", context)

    # 4. Convert to PDF using WeasyPrint
    pdf_file = weasyprint.HTML(
        string=html_string, base_url=request.build_absolute_uri()
    ).write_pdf()

    # 5. Return PDF Response
    response = HttpResponse(pdf_file, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="invoice_{booking.ref}.pdf"'
    return response


@staff_member_required
def airport_autocomplete(request):
    """
    Used by the FlightTicket admin widget to search for airports.
    """
    term = request.GET.get("term", "")

    if len(term) < 2:
        return JsonResponse([], safe=False)

    # Uses the utility function you already have
    results = search_airports(term)
    return JsonResponse(results, safe=False)


def public_visa_form(request, ref):
    booking = get_object_or_404(Booking, ref=ref)
    visa_instance = VisaApplication.objects.filter(booking=booking).first()

    # Get language from URL (default 'tn')
    lang = request.GET.get("lang", "tn")

    # Template setup
    if lang == "fr":
        success_msg = "Votre dossier a été transmis avec succès."
        form_template = "core/visa_form_fr.html" # Ensure you have this template (we made it earlier)
    else:
        success_msg = "دوسيك وصلنا وباش نركحوه. تو نكلموك."
        form_template = "core/visa_form_tn.html" # Ensure you have this template

    if request.method == "POST":
        form = VisaForm(
            request.POST, 
            request.FILES, 
            instance=visa_instance,
            visible_fields=booking.visa_form_config,
            lang=lang  # <--- CRITICAL: Pass language to form
        )

        if form.is_valid():
            try:
                visa_app = form.save(commit=False)
                visa_app.booking = booking
                visa_app.save()
                return render(request, "core/success.html", {"msg": success_msg})
            except IntegrityError:
                # Handle race condition
                existing = VisaApplication.objects.get(booking=booking)
                form = VisaForm(request.POST, request.FILES, instance=existing, visible_fields=booking.visa_form_config, lang=lang)
                if form.is_valid():
                    form.save()
                    return render(request, "core/success.html", {"msg": success_msg})
    else:
        form = VisaForm(
            instance=visa_instance,
            visible_fields=booking.visa_form_config,
            lang=lang  # <--- CRITICAL: Pass language to form
        )

    return render(request, form_template, {"form": form, "booking": booking, "lang": lang})

def visa_success(request):
    """Fallback success view"""
    return render(request, "core/success.html", {"msg": "Operation Successful"})
