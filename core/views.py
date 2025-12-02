# core/views.py
import weasyprint
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string

from .forms import VisaForm
from .models import Booking, VisaApplication
from .utils import search_airports


@login_required
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
    # Ensure your template is at: core/templates/core/invoice.html
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

    # 1. Try to find the existing application
    visa_instance = VisaApplication.objects.filter(booking=booking).first()

    # 2. Get language
    lang = request.GET.get("lang", "tn")

    # 3. Define Messages
    if lang == "fr":
        success_msg = "Votre dossier a été transmis à notre équipe avec succès."
        form_template = "core/public_visa_form.html"
    else:
        success_msg = "دوسيك وصلنا وباش نركحوه. تو نكلموك."
        form_template = "core/public_visa_form.html"

    # 4. Handle Submission
    if request.method == "POST":
        # Pass instance to enable UPDATE mode
        form = VisaForm(request.POST, request.FILES, instance=visa_instance)

        if form.is_valid():
            try:
                visa_app = form.save(commit=False)
                visa_app.booking = booking
                visa_app.save()
                return render(request, "core/success.html", {"msg": success_msg})

            except IntegrityError:
                # SAFETY NET: If we crash here, it means the record existed but we missed it.
                # Force-fetch the existing record and update it manually.
                existing_app = VisaApplication.objects.get(booking=booking)
                form = VisaForm(request.POST, request.FILES, instance=existing_app)
                if form.is_valid():
                    visa_app = form.save(commit=False)
                    visa_app.booking = booking
                    visa_app.save()
                    return render(request, "core/success.html", {"msg": success_msg})

    else:
        form = VisaForm(instance=visa_instance)

    return render(
        request, form_template, {"form": form, "booking": booking, "lang": lang}
    )


def visa_success(request):
    """Fallback success view"""
    return render(request, "core/success.html", {"msg": "Operation Successful"})
