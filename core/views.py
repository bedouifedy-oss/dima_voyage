# core/views.py
from datetime import datetime, timedelta
from decimal import Decimal

import weasyprint
from django.contrib import admin, messages  # <--- Added 'admin' here
from django.contrib.admin.views.decorators import staff_member_required
from django.core.files.storage import default_storage
from django.db import IntegrityError
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template import Context, Template
from django.template.loader import render_to_string
from django.utils import timezone

from .finance import FinanceStats
from .forms import VisaFieldConfigurationForm, VisaForm
from .models import (
    Booking,
    DocumentTemplate,
    EditorSettings,
    GeneratedDocument,
    VisaApplication,
)
from .permissions import can_view_financial_dashboard, is_manager
from .utils import search_airports, send_visa_whatsapp


# healthcheck for load balancers
def healthz(request):
    """Simple healthcheck for load balancers."""
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return HttpResponse("OK", status=200)
    except Exception:
        return HttpResponse("DB Error", status=503)


# --- FINANCIAL DASHBOARD VIEW ---
@staff_member_required
def financial_dashboard(request):
    # Check permission
    if not can_view_financial_dashboard(request.user):
        messages.error(
            request, "You don't have permission to view the financial dashboard."
        )
        return redirect("/admin/")

    # 1. Get Admin Context
    context = admin.site.each_context(request)

    # 2. Date Filtering Logic
    today = timezone.now().date()
    start_of_month = today.replace(day=1)

    # Get parameters from URL (Default to 'this_month')
    period = request.GET.get("period", "this_month")
    date_from_str = request.GET.get("date_from")
    date_to_str = request.GET.get("date_to")

    # Calculate Range
    if period == "today":
        date_from = today
        date_to = today
    elif period == "yesterday":
        date_from = today - timedelta(days=1)
        date_to = date_from
    elif period == "this_week":
        date_from = today - timedelta(days=today.weekday())  # Monday
        date_to = today
    elif period == "this_month":
        date_from = start_of_month
        date_to = today
    elif period == "last_month":
        last_month_end = start_of_month - timedelta(days=1)
        date_from = last_month_end.replace(day=1)
        date_to = last_month_end
    elif period == "custom" and date_from_str and date_to_str:
        try:
            date_from = datetime.strptime(date_from_str, "%Y-%m-%d").date()
            date_to = datetime.strptime(date_to_str, "%Y-%m-%d").date()
        except ValueError:
            date_from, date_to = start_of_month, today
    else:
        date_from, date_to = start_of_month, today

    # 3. Fetch Raw Numbers (Passing Dates to FinanceStats)
    # We pass the calculated dates to your helper class
    raw_cash_in = FinanceStats.get_gross_client_cash_in(date_from, date_to)
    supplier_costs = FinanceStats.get_net_supplier_cost_paid(date_from, date_to)
    total_refunds = FinanceStats.get_client_refunds(date_from, date_to)

    # Unpaid Debt is a snapshot (Total owed right now), so we usually don't filter it by date
    unpaid_debt = FinanceStats.get_unpaid_liabilities()

    # Profit Calculation for this period
    cash_profit = raw_cash_in - supplier_costs - total_refunds

    context.update(
        {
            "title": "Financial Dashboard",
            # Data
            "total_revenue": raw_cash_in,
            "total_paid_to_suppliers": supplier_costs,
            "total_refunds": total_refunds,
            "current_balance": cash_profit,  # This acts as "Net Cash Flow" for the period
            "unpaid_debt": unpaid_debt,
            # Filter State (So the template knows which button is active)
            "period": period,
            "date_from": date_from.strftime("%Y-%m-%d"),
            "date_to": date_to.strftime("%Y-%m-%d"),
        }
    )

    return render(request, "core/dashboard.html", context)


# --- PRODUCTIVITY DASHBOARD ---
@staff_member_required
def productivity_dashboard(request):
    """
    Dashboard showing agent productivity metrics with date filters.
    """
    from django.contrib.auth import get_user_model
    from django.db.models import Count, Q

    User = get_user_model()
    context = admin.site.each_context(request)

    # Get date range from request or default to this month
    today = timezone.now().date()
    period = request.GET.get("period", "month")

    # Calculate date range based on period
    if period == "today":
        date_from = today
        date_to = today
        period_label = "Today"
    elif period == "week":
        date_from = today - timedelta(days=today.weekday())  # Monday
        date_to = today
        period_label = "This Week"
    elif period == "month":
        date_from = today.replace(day=1)
        date_to = today
        period_label = today.strftime("%B %Y")
    elif period == "quarter":
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        date_from = today.replace(month=quarter_month, day=1)
        date_to = today
        period_label = f"Q{(today.month - 1) // 3 + 1} {today.year}"
    elif period == "year":
        date_from = today.replace(month=1, day=1)
        date_to = today
        period_label = str(today.year)
    elif period == "custom":
        try:
            date_from = datetime.strptime(
                request.GET.get("date_from", ""), "%Y-%m-%d"
            ).date()
            date_to = datetime.strptime(
                request.GET.get("date_to", ""), "%Y-%m-%d"
            ).date()
            period_label = (
                f"{date_from.strftime('%b %d')} - {date_to.strftime('%b %d, %Y')}"
            )
        except ValueError:
            date_from = today.replace(day=1)
            date_to = today
            period_label = today.strftime("%B %Y")
            period = "month"
    else:
        date_from = today.replace(day=1)
        date_to = today
        period_label = today.strftime("%B %Y")

    # Managers see all agents; regular agents only see their own row
    base_agents_qs = User.objects.filter(is_staff=True)
    if not is_manager(request.user):
        base_agents_qs = base_agents_qs.filter(pk=request.user.pk)

    # Agent stats - bookings created and assigned within date range
    agents = base_agents_qs.annotate(
        bookings_created_total=Count("bookings_created"),
        bookings_created_period=Count(
            "bookings_created",
            filter=Q(
                bookings_created__created_at__date__gte=date_from,
                bookings_created__created_at__date__lte=date_to,
            ),
        ),
        bookings_assigned_total=Count("bookings_assigned"),
        bookings_assigned_active=Count(
            "bookings_assigned",
            filter=~Q(bookings_assigned__status="cancelled"),
        ),
        bookings_confirmed_period=Count(
            "bookings_created",
            filter=Q(
                bookings_created__status="confirmed",
                bookings_created__created_at__date__gte=date_from,
                bookings_created__created_at__date__lte=date_to,
            ),
        ),
        total_revenue_period=Coalesce(
            Sum(
                "bookings_created__total_amount",
                filter=Q(
                    bookings_created__status="confirmed",
                    bookings_created__created_at__date__gte=date_from,
                    bookings_created__created_at__date__lte=date_to,
                ),
            ),
            Value(Decimal("0.00")),
        ),
    ).order_by("-bookings_created_period")

    # Summary stats for the period (all bookings visible to everyone)
    total_bookings_period = Booking.objects.filter(
        created_at__date__gte=date_from, created_at__date__lte=date_to
    ).count()
    total_bookings_all = Booking.objects.count()
    unassigned_bookings = Booking.objects.filter(assigned_to__isnull=True).count()

    context.update(
        {
            "title": "Agent Productivity",
            "agents": agents,
            "total_bookings_period": total_bookings_period,
            "total_bookings_all": total_bookings_all,
            "unassigned_bookings": unassigned_bookings,
            "period_label": period_label,
            "period": period,
            "date_from": date_from.strftime("%Y-%m-%d"),
            "date_to": date_to.strftime("%Y-%m-%d"),
        }
    )

    return render(request, "core/productivity_dashboard.html", context)


# --- VISA CONFIGURATION VIEW ---
@staff_member_required
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
@staff_member_required
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


# --- TOOLS: DYNAMIC DOCUMENT ENGINE ---


@staff_member_required
def document_tool_view(request, slug):
    """Dynamic tool interface for a given DocumentTemplate."""
    template_conf = get_object_or_404(DocumentTemplate, slug=slug)

    editor_settings = EditorSettings.objects.first()
    tinymce_key = (
        editor_settings.tinymce_api_key
        if editor_settings and editor_settings.tinymce_api_key
        else "no-api-key"
    )

    # Optional: link this document to an existing booking and prefill
    # personal information from the booking / client / visa data.
    booking_id = request.GET.get("booking_id")
    booking = None
    prefill = {}
    if booking_id:
        try:
            booking = Booking.objects.select_related("client").get(pk=booking_id)
        except Booking.DoesNotExist:
            booking = None

    if booking:
        client = booking.client
        visa = getattr(booking, "visa_data", None)

        # Prefer visa application data when available, fall back to Client
        prefill["passenger_name"] = getattr(visa, "full_name", None) or client.name
        prefill["passport_number"] = (
            getattr(visa, "passport_number", None) or client.passport
        )
        if getattr(visa, "passport_expiry_date", None):
            prefill["passport_expiry"] = visa.passport_expiry_date
        if getattr(visa, "dob", None):
            prefill["dob"] = visa.dob
        prefill["nationality"] = getattr(visa, "nationality", None) or None
        prefill["email"] = client.email
        prefill["mobile"] = client.phone

    # Build a helper list of fields with optional "initial" value so the
    # template can render defaults without doing dict indexing tricks.
    manual_fields = []
    for f in template_conf.manual_fields_config:
        field = f.copy()
        key = field.get("key")
        if key and key in prefill:
            field["initial"] = prefill[key]
        manual_fields.append(field)

    if request.method == "POST":
        # 1. Collect Manual Data based on JSON config
        manual_data = {}
        for field in template_conf.manual_fields_config:
            key = field.get("key")
            if not key:
                continue
            value = request.POST.get(key, "")
            # IMPORTANT: do not overwrite parsed values with empty strings.
            # Only store keys the user actually filled.
            if value not in ("", None):
                manual_data[key] = value

        # 1.b Auto-generate reference numbers for templates that use them
        # These keys are optional; they will simply be available in the
        # template context if the HTML references them.
        if "reservation_number" not in manual_data or not manual_data.get(
            "reservation_number"
        ):
            # Pattern: 8-digit numeric code (e.g. 48290317)
            from random import randint

            manual_data["reservation_number"] = f"{randint(0, 99999999):08d}"

        if "company_reference" not in manual_data or not manual_data.get(
            "company_reference"
        ):
            # Simple short pseudo-PNR style reference
            from uuid import uuid4

            manual_data["company_reference"] = uuid4().hex[:6].upper()

        if "confidential_code" not in manual_data or not manual_data.get(
            "confidential_code"
        ):
            from uuid import uuid4

            manual_data["confidential_code"] = uuid4().hex[:6].lower()

        # 2. Manual-only mode: no parsing from raw text or external APIs.
        raw_text = ""
        parsed_data = {}

        # 3. Save Document
        doc = GeneratedDocument.objects.create(
            template=template_conf,
            raw_text=raw_text,
            manual_data=manual_data,
            parsed_data=parsed_data,
        )

        # 4. Redirect to Print
        return redirect("print_document", doc_id=doc.id)

    # Render inside the admin shell (header, sidebar, etc.) similar to
    # the financial dashboard and tools hub.
    context = admin.site.each_context(request)
    context.update(
        {
            "template_conf": template_conf,
            "title": f"New {template_conf.name}",
            "tinymce_api_key": tinymce_key,
            "prefill": prefill,
            "manual_fields": manual_fields,
        }
    )
    return render(request, "core/tool_form.html", context)


@staff_member_required
def print_document_view(request, doc_id):
    """Render stored HTML content with stored data as a PDF using WeasyPrint.

    This mirrors the strategy used for booking invoices so we avoid browser
    headers/footers and get a clean A4 PDF for printing.
    """

    doc = get_object_or_404(GeneratedDocument, pk=doc_id)

    # Combine data: parsed first, manual overrides
    context_data = {**doc.parsed_data, **doc.manual_data}
    context_data["today"] = timezone.now()

    # Render HTML from the stored template content
    django_template = Template(doc.template.html_content)
    context = Context(context_data)
    rendered_html = django_template.render(context)

    # Convert to PDF with WeasyPrint
    pdf_file = weasyprint.HTML(
        string=rendered_html,
        base_url=request.build_absolute_uri(),
    ).write_pdf()

    response = HttpResponse(pdf_file, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="document_{doc.id}.pdf"'
    return response


@staff_member_required
def tools_hub(request):
    """Simple tools hub listing available DocumentTemplates and future tools.

    Uses the same admin context pattern as the financial dashboard so it
    appears fully inside the Django admin shell (header, sidebar, etc.).
    """

    context = admin.site.each_context(request)
    booking_id = request.GET.get("booking_id")
    context.update(
        {
            "title": "Tools / Documents",
            "templates": DocumentTemplate.objects.all().order_by("name"),
            "booking_id": booking_id,
        }
    )
    return render(request, "core/tools_hub.html", context)


@staff_member_required
def tool_image_upload(request):
    """Handle image uploads from the WYSIWYG editor.

    Returns JSON with a "location" key as expected by TinyMCE.
    Note: CSRF token must be included in the request headers by the frontend.
    """

    if request.method != "POST" or "file" not in request.FILES:
        return JsonResponse({"error": "Invalid request"}, status=400)

    upload = request.FILES["file"]
    path = default_storage.save(f"tool_uploads/{upload.name}", upload)
    url = default_storage.url(path)
    return JsonResponse({"location": url})
