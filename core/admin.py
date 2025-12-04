# core/admin.py
import secrets
import string
from datetime import datetime

import requests
from django.contrib import admin, messages
from django.db import models  # Essential for the Filter
from django.db.models import F, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from .forms import BookingAdminForm, VisaInlineForm
from .models import (AmadeusSettings, Announcement, Booking, Client, Expense,
                     FlightTicket, KnowledgeBase, LedgerEntry, Payment,
                     Supplier, User, VisaApplication, WhatsAppSettings)


# --- CUSTOM FILTERS ---
class OutstandingFilter(admin.SimpleListFilter):
    title = "Outstanding Balance"
    parameter_name = "outstanding_status"

    def lookups(self, request, model_admin):
        return (("yes", "Has Outstanding Balance"), ("no", "Fully Paid"))

    def queryset(self, request, queryset):
        qs = queryset.annotate(
            db_paid=Coalesce(
                Sum("payments__amount"), Value(0), output_field=models.DecimalField()
            )
        )
        if self.value() == "yes":
            return qs.filter(total_amount__gt=F("db_paid"))
        if self.value() == "no":
            return qs.filter(total_amount__lte=F("db_paid"))
        return queryset


# --- 1. REGISTER DEPENDENCIES FIRST ---


@admin.register(Client)
class ClientAdmin(ModelAdmin):
    list_display = ("name", "phone", "passport", "created_at")
    search_fields = ("name", "phone", "passport")


@admin.register(Supplier)
class SupplierAdmin(ModelAdmin):
    list_display = ("name", "contact")
    search_fields = ("name",)


# --- 2. INLINES ---


class PaymentHistoryInline(admin.TabularInline):
    """Read-Only history. Agents use the Command Center buttons instead."""

    model = Payment
    fields = ("date", "amount", "method", "reference")
    readonly_fields = ("date", "amount", "method", "reference")
    extra = 0
    can_delete = False
    verbose_name = "📜 Transaction History"
    verbose_name_plural = "Transaction History"


class VisaInline(admin.StackedInline):
    model = VisaApplication
    form = VisaInlineForm  # <--- ACTIVATE THE FIX HERE
    can_delete = False
    verbose_name_plural = "📄 Visa Application Data"
    fields = (
        ("full_name", "passport_number"),
        ("dob", "passport_issue_date", "passport_expiry_date"),
        "photo",
        "financial_proofs",
    )
    readonly_fields = ("submitted_at",)
    extra = 0


class FlightTicketInline(admin.StackedInline):
    model = FlightTicket
    extra = 1
    max_num = 1
    verbose_name = "✈️ Flight Ticket Details"
    classes = ("collapse",)


# --- 3. MAIN BOOKING ADMIN ---


@admin.register(Booking)
class BookingAdmin(ModelAdmin):
    form = BookingAdminForm
    autocomplete_fields = ["client"]

    list_display = (
        "ref",
        "client",
        "created_at",  # Using created_at instead of trip_date
        "total_amount",
        "status_badge",
        "balance_display",
        "invoice_link",
    )

    list_filter = (OutstandingFilter, "payment_status", "booking_type", "created_at")
    search_fields = ("ref", "client__name", "client__phone", "client__passport")

    readonly_fields = (
        "ref",
        "payment_status",
        "created_at",
        "balance_display",
        "invoice_link",
        "send_whatsapp_link",
    )

    # --- Added Actions Here ---
    actions = ["configure_whatsapp_send", "send_whatsapp_tn", "send_whatsapp_fr"]

    fieldsets = (
        (
            "✈️ Trip & Customer",
            {
                "fields": (
                    ("ref", "created_at"),
                    "client",
                    "booking_type",
                    "description",
                )
            },
        ),
        (
            "🔄 Operation (Changes/Refunds)",
            {
                "fields": (("operation_type", "parent_booking"),),
                "classes": ("collapse",),
                "description": "Link to a parent booking if this is a modification.",
            },
        ),
        (
            "💰 Financials",
            {
                "fields": (("total_amount", "supplier_cost"), "balance_display"),
            },
        ),
        (
            "💳 Payment Command Center",
            {
                "fields": (
                    "payment_action",
                    ("transaction_amount", "transaction_method"),
                ),
                "classes": ("background-gray",),
                "description": "Select an action to instantly update status and ledger.",
            },
        ),
    )

    inlines = [VisaInline, FlightTicketInline, PaymentHistoryInline]

    def save_model(self, request, obj, form, change):
        # A. Auto-Generate Reference
        if not obj.ref:
            year_suffix = str(datetime.now().year)[-2:]
            unique_code = "".join(
                secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4)
            )
            obj.ref = f"DV-{year_suffix}-{unique_code}"

        # B. Save Booking
        super().save_model(request, obj, form, change)

        # C. Process Payment Ghost Fields
        action = form.cleaned_data.get("payment_action")
        amount = form.cleaned_data.get("transaction_amount")
        method = form.cleaned_data.get("transaction_method")

        if action == "none":
            return

        final_amount = 0
        if action == "full":
            paid_so_far = obj.payments.aggregate(Sum("amount"))["amount__sum"] or 0
            final_amount = obj.total_amount - paid_so_far
        elif action == "partial":
            final_amount = amount
        elif action == "refund":
            final_amount = -abs(amount)

        if final_amount != 0:
            Payment.objects.create(
                booking=obj,
                amount=final_amount,
                method=method,
                date=datetime.now().date(),
                reference=f"AUTO-{action.upper()}",
            )
            self.message_user(
                request, f"✅ Processed {action.upper()}: {final_amount} TND"
            )

    # --- NEW ACTION LOGIC ---

    def send_whatsapp_link(self, obj):
        if not obj.pk:
            return "-"
        return format_html(
            '<span style="color: gray;">Go to "Bookings List" > Select this booking > Choose "Send Visa Form" from Actions menu.</span>'
        )

    send_whatsapp_link.short_description = "Send WhatsApp"

    def configure_whatsapp_send(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(
                request,
                "⚠️ Please select exactly one booking to configure.",
                messages.WARNING,
            )
            return

        booking = queryset.first()
        # Redirect to our new configuration page
        return redirect("admin_configure_visa", booking_id=booking.pk)

    configure_whatsapp_send.short_description = "📤 Configure & Send Visa Form"

    # --- WHATSAPP SENDING LOGIC (Added) ---

    def send_whatsapp_tn(self, request, queryset):
        self._send_whatsapp_logic(request, queryset, lang="tn")

    send_whatsapp_tn.short_description = "🇹🇳 Send Visa Form (Tunisian)"

    def send_whatsapp_fr(self, request, queryset):
        self._send_whatsapp_logic(request, queryset, lang="fr")

    send_whatsapp_fr.short_description = "🇫🇷 Send Visa Form (French)"

    def _send_whatsapp_logic(self, request, queryset, lang):
        config = WhatsAppSettings.objects.first()
        if not config:
            self.message_user(
                request, "❌ Error: WhatsApp Settings not configured.", messages.ERROR
            )
            return

        count = 0
        for booking in queryset:
            if booking.client.phone:
                # Generate the Public Link (This now uses your configured fields!)
                link = request.build_absolute_uri(
                    reverse("public_visa_form", args=[booking.ref])
                )

                # Select Template
                msg_template = (
                    config.template_fr if lang == "fr" else config.template_tn
                )

                # Format Message
                try:
                    msg = msg_template.format(
                        client_name=booking.client.name, link=link, ref=booking.ref
                    )
                except KeyError:
                    # Fallback if template has wrong placeholders
                    msg = f"Hello {booking.client.name}, please upload your documents here: {link}"

                # Send via API (UltraMsg)
                try:
                    payload = {
                        "token": config.api_token,
                        "to": booking.client.phone,
                        "body": msg,
                    }
                    requests.post(config.api_url, data=payload)
                    count += 1
                except Exception as e:
                    self.message_user(
                        request,
                        f"⚠️ Failed to send to {booking.client.name}: {e}",
                        messages.WARNING,
                    )

        lang_name = "French" if lang == "fr" else "Tunisian"
        self.message_user(request, f"✅ Sent {lang_name} form to {count} clients.")

    # --- UI Helpers ---
    def status_badge(self, obj):
        colors = {
            "PAID": "green",
            "PARTIAL": "orange",
            "PENDING": "red",
            "REFUNDED": "gray",
        }
        color = colors.get(obj.payment_status, "gray")
        label = obj.get_payment_status_display() if obj.payment_status else "Unknown"
        return format_html(
            f'<span style="color:{color}; font-weight:bold;">● {label}</span>'
        )

    status_badge.short_description = "Status"

    def balance_display(self, obj):
        if not obj.pk:
            return "-"
        paid = obj.payments.aggregate(Sum("amount"))["amount__sum"] or 0
        balance = obj.total_amount - paid

        if balance > 0:
            return format_html(f'<b style="color:#d9534f;">{balance:,.2f} TND Due</b>')
        elif balance == 0:
            return format_html('<b style="color:#5cb85c;">✔ Settled</b>')
        else:
            return format_html(
                f'<b style="color:#0275d8;">{abs(balance):,.2f} TND (Credit)</b>'
            )

    balance_display.short_description = "Balance"

    def invoice_link(self, obj):
        if obj.pk:
            url = reverse("invoice_pdf", args=[obj.pk])
            return format_html(
                '<a href="{}" target="_blank" class="button">🖨️ Invoice</a>', url
            )
        return "-"

    invoice_link.short_description = "Invoice"


# --- 4. OTHER ADMINS ---


@admin.register(Payment)
class PaymentAuditAdmin(ModelAdmin):
    list_display = ("date", "amount", "method", "booking", "reference")
    list_filter = ("method", "date")
    search_fields = ("booking__ref", "reference")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Expense)
class ExpenseAdmin(ModelAdmin):
    list_display = ("name", "amount", "due_date", "paid", "supplier")
    list_filter = ("paid", "due_date")


@admin.register(LedgerEntry)
class LedgerEntryAdmin(ModelAdmin):
    change_list_template = "admin/core/ledgerentry/change_list.html"
    list_display = (
        "date",
        "formatted_account",
        "formatted_debit",
        "formatted_credit",
        "booking",
    )
    list_filter = ("date", "account")
    date_hierarchy = "date"

    def formatted_account(self, obj):
        if obj.account.startswith("Revenue"):
            return format_html(
                '<span style="color: green; font-weight:bold;">{}</span>', obj.account
            )
        elif obj.account.startswith("Expense"):
            return format_html(
                '<span style="color: red; font-weight:bold;">{}</span>', obj.account
            )
        return obj.account

    formatted_account.short_description = "Account"

    def formatted_debit(self, obj):
        return (
            format_html('<span style="color: #aa0000;">{}</span>', obj.debit)
            if obj.debit > 0
            else "-"
        )

    formatted_debit.short_description = "Debit"

    def formatted_credit(self, obj):
        return (
            format_html('<span style="color: #008800;">{}</span>', obj.credit)
            if obj.credit > 0
            else "-"
        )

    formatted_credit.short_description = "Credit"

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        if hasattr(response, "context_data") and "cl" in response.context_data:
            qs = response.context_data["cl"].queryset
            revenue = (
                qs.filter(account__startswith="Revenue").aggregate(total=Sum("credit"))[
                    "total"
                ]
                or 0
            )
            expense = (
                qs.filter(account__startswith="Expense").aggregate(total=Sum("debit"))[
                    "total"
                ]
                or 0
            )
            response.context_data["summary"] = {
                "revenue": revenue,
                "expense": expense,
                "profit": revenue - expense,
            }
        return response

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Announcement)
class AnnouncementAdmin(ModelAdmin):
    list_display = (
        "title",
        "priority",
        "created_at",
        "approval_progress",
        "user_status",
    )
    list_filter = ("priority", "created_at")

    def approval_progress(self, obj):
        count = obj.acknowledged_by.count()
        total_staff = User.objects.filter(is_active=True).count() or 1
        percent = int((count / total_staff) * 100)
        color = "green" if percent == 100 else "orange"
        return format_html(
            f'<div style="width:100px; background:#eee; border-radius:4px; overflow:hidden;"><div style="width:{percent}%; background:{color}; height:10px;"></div></div>'
        )

    approval_progress.short_description = "Progress"

    def user_status(self, obj):
        return f"{obj.acknowledged_by.count()} Approvals"


@admin.register(WhatsAppSettings)
class WhatsAppSettingsAdmin(ModelAdmin):
    list_display = ("name", "api_url")


@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(ModelAdmin):
    list_display = ("title", "category", "utility_score")


@admin.register(AmadeusSettings)
class AmadeusSettingsAdmin(ModelAdmin):
    list_display = ("name", "environment", "client_id")


@admin.register(VisaApplication)
class VisaApplicationAdmin(ModelAdmin):
    list_display = ("full_name", "passport_number", "booking_link", "submitted_at")
    search_fields = ("full_name", "passport_number", "booking__ref")
    readonly_fields = ("submitted_at",)

    def booking_link(self, obj):
        if obj.booking:
            url = reverse("admin:core_booking_change", args=[obj.booking.pk])
            return format_html('<a href="{}">{}</a>', url, obj.booking.ref)
        return "-"

    booking_link.short_description = "Related Booking"
