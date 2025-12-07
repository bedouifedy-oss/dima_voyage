# core/views.py
from decimal import Decimal

import weasyprint
from django.contrib import admin, messages  # <--- Added 'admin' here
from django.contrib.admin.views.decorators import staff_member_required
from django.db import IntegrityError
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string

from .finance import FinanceStats
from .forms import VisaFieldConfigurationForm, VisaForm
from .models import Booking, VisaApplication
from .utils import search_airports, send_visa_whatsapp


# --- FINANCIAL DASHBOARD VIEW ---
@staff_member_required
def financial_dashboard(request):
    # 1. Get Admin Context
    context = admin.site.each_context(request)

    # 2. Fetch Raw Numbers
    # CHANGE: We now use 'get_gross_client_cash_in' for the Revenue Card
    raw_cash_in = FinanceStats.get_gross_client_cash_in()

    supplier_costs = FinanceStats.get_net_supplier_cost_paid()
    balance = FinanceStats.get_net_cash_balance()
    unpaid_debt = FinanceStats.get_unpaid_liabilities()

    # 3. Profit (Optional calculation for context)
    # If you want Profit to be (Cash In - Costs), use this:
    cash_profit = raw_cash_in - supplier_costs

    context.update(
        {
            "title": "Financial Dashboard",
            "total_revenue": raw_cash_in,  # <--- Shows Total Cash In
            "total_paid_to_suppliers": supplier_costs,
            "current_balance": balance,
            "unpaid_debt": unpaid_debt,
            "profit": cash_profit,
        }
    )

    return render(request, "core/dashboard.html", context)


# --- VISA CONFIGURATION VIEW ---
def configure_visa_form(request, booking_id):
    """
    Admin View: Allows staff to select fields AND send the message in one go.
    """
    booking = get_object_or_404(Booking, pk=booking_id)

    if request.method == "POST":
        form = VisaFieldConfigurationForm(request.POST)
        if form.is_valid():
            # 1. ALWAYS SAVE CONFIGURATION (Even if cancelling send)
            selection = form.cleaned_data["selected_fields"] + [
                "passport_number",
                "photo",
            ]
            booking.visa_form_config = selection

            # --- FIX: Self-Healing Data for Legacy Records ---
            if not booking.status:
                booking.status = "quote"
            # -------------------------------------------------

            booking.save()

            # 2. CHECK WHICH BUTTON WAS CLICKED

            # Case A: Send Tunisian
            if "_send_tn" in request.POST:
                success, msg = send_visa_whatsapp(request, booking, "tn")
                if success:
                    messages.success(
                        request, "✅ Configuration Saved & 🇹🇳 Message Sent!"
                    )
                else:
                    messages.error(request, msg)

            # Case B: Send French
            elif "_send_fr" in request.POST:
                success, msg = send_visa_whatsapp(request, booking, "fr")
                if success:
                    messages.success(
                        request, "✅ Configuration Saved & 🇫🇷 Message Sent!"
                    )
                else:
                    messages.error(request, msg)

            # Case C: Cancel / Save Only
            else:
                messages.info(request, "💾 Configuration saved (No message sent).")

            return redirect(f"/admin/core/booking/{booking.id}/change/")
    else:
        # Pre-fill
        initial_data = [
            f for f in booking.visa_form_config if f not in ["passport_number", "photo"]
        ]
        form = VisaFieldConfigurationForm(initial={"selected_fields": initial_data})

    return render(
        request,
        "admin/core/booking/configure_form.html",
        {"form": form, "booking": booking},
    )


# --- INVOICE GENERATION ---
def invoice_pdf(request, booking_id):
    # 1. Get the booking
    booking = get_object_or_404(Booking, id=booking_id)

    # --- NEW CALCULATION LOGIC ---
    # A. Sum Positive Payments
    total_paid = booking.payments.filter(transaction_type="payment").aggregate(
        total=Coalesce(Sum("amount"), Value(Decimal("0.00")))
    )["total"]

    # B. Sum Refunds
    total_refunded = booking.payments.filter(transaction_type="refund").aggregate(
        total=Coalesce(Sum("amount"), Value(Decimal("0.00")))
    )["total"]

    # C. Calculate Net (The true amount currently with us)
    net_paid = total_paid - total_refunded

    # D. Calculate Balance Due
    balance_due = booking.total_amount - net_paid

    # 3. Context data (Now includes the calculated math)
    context = {
        "booking": booking,
        "user": request.user,
        "base_url": request.build_absolute_uri("/")[:-1],
        # Pass these explicit numbers to the template
        "invoice_net_paid": net_paid,
        "invoice_refunds": total_refunded,
        "invoice_balance": balance_due,
    }

    # 4. Render HTML to string
    html_string = render_to_string("core/invoice.html", context)

    # 5. Convert to PDF
    pdf_file = weasyprint.HTML(
        string=html_string, base_url=request.build_absolute_uri()
    ).write_pdf()

    # 6. Return Response
    response = HttpResponse(pdf_file, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="invoice_{booking.ref}.pdf"'
    return response


# --- UTILITIES ---
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


# --- PUBLIC VISA FORM ---
def public_visa_form(request, ref):
    booking = get_object_or_404(Booking, ref=ref)
    visa_instance = VisaApplication.objects.filter(booking=booking).first()

    # Get language from URL (default 'tn')
    lang = request.GET.get("lang", "tn")

    # Template setup
    if lang == "fr":
        success_msg = "Votre dossier a été transmis avec succès"
        form_template = "core/visa_form_fr.html"
    else:
        success_msg = "دوسيك وصلنا وباش نركحوه. تو نكلموك"
        form_template = "core/visa_form_tn.html"

    if request.method == "POST":
        form = VisaForm(
            request.POST,
            request.FILES,
            instance=visa_instance,
            visible_fields=booking.visa_form_config,
            lang=lang,
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
                form = VisaForm(
                    request.POST,
                    request.FILES,
                    instance=existing,
                    visible_fields=booking.visa_form_config,
                    lang=lang,
                )
                if form.is_valid():
                    form.save()
                    return render(request, "core/success.html", {"msg": success_msg})
    else:
        form = VisaForm(
            instance=visa_instance,
            visible_fields=booking.visa_form_config,
            lang=lang,
        )

    return render(
        request, form_template, {"form": form, "booking": booking, "lang": lang}
    )


def visa_success(request):
    """Fallback success view"""
    return render(request, "core/success.html", {"msg": "Operation Successful"})
