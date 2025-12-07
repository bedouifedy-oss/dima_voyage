# core/admin.py
import secrets
import string
from datetime import datetime
from decimal import Decimal

import requests
from django.contrib import admin, messages
from django.db import models  # Essential for the Filter
from django.db import transaction
from django.db.models import DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from .forms import BookingAdminForm, VisaInlineForm
from .models import (AmadeusSettings, Announcement, Booking,
                     BookingLedgerAllocation, Client, Expense, FlightTicket,
                     KnowledgeBase, LedgerEntry, Payment, Supplier, User,
                     VisaApplication, WhatsAppSettings)


# --- CUSTOM FILTERS ---
class OutstandingFilter(admin.SimpleListFilter):
    title = "Outstanding Balance"
    parameter_name = "outstanding_status"

    def lookups(self, request, model_admin):
        return (("yes", "Has Outstanding Balance"), ("no", "Fully Paid"))

    def queryset(self, request, queryset):
        # We annotate Payments and Refunds separately
        qs = queryset.annotate(
            total_pay=Coalesce(
                Sum("payments__amount", filter=Q(payments__transaction_type="payment")),
                Value(Decimal("0.00")),
                output_field=DecimalField(),
            ),
            total_ref=Coalesce(
                Sum("payments__amount", filter=Q(payments__transaction_type="refund")),
                Value(Decimal("0.00")),
                output_field=DecimalField(),
            ),
        ).annotate(
            # Net Paid = Payments - Refunds
            net_paid=F("total_pay")
            - F("total_ref")
        )

        if self.value() == "yes":
            # If Total > Net Paid, they owe us money
            return qs.filter(total_amount__gt=F("net_paid"))

        if self.value() == "no":
            # If Total <= Net Paid, they are settled
            return qs.filter(total_amount__lte=F("net_paid"))

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


@admin.action(description="💰 Pay Supplier via Ledger (Regularization)")
def pay_via_ledger(modeladmin, request, queryset):
    # 1. Calculate total needed for selected bookings
    total_to_pay = 0
    bookings_to_pay = []

    for booking in queryset:
        if booking.supplier_payment_status == "paid":
            continue  # Skip already paid ones

        # Calculate how much is left to pay on this booking
        paid_so_far = (
            booking.supplier_allocations.aggregate(total=models.Sum("amount"))["total"]
            or 0
        )
        remainder = booking.supplier_cost - paid_so_far

        if remainder > 0:
            total_to_pay += remainder
            bookings_to_pay.append((booking, remainder))

    if total_to_pay == 0:
        messages.warning(request, "Selected bookings are already paid or have 0 cost.")
        return

    # 2. SAFE TRANSACTION: Create Ledger Entry AND Allocations together
    with transaction.atomic():
        # A. Create the Ledger Entry (One big payment)
        ledger_entry = LedgerEntry.objects.create(
            date=timezone.now(),
            account=f"Bulk Payment for {len(bookings_to_pay)} bookings",
            entry_type="supplier_payment",
            debit=total_to_pay,
            created_by=request.user,
        )

        # B. Create the Allocations (The Safety Bridge)
        for booking, amount in bookings_to_pay:
            BookingLedgerAllocation.objects.create(
                ledger_entry=ledger_entry, booking=booking, amount=amount
            )
            # The .save() method on Allocation will automatically
            # update the booking status to 'Paid'

    messages.success(
        request,
        f"Successfully regularized {total_to_pay} TND for {len(bookings_to_pay)} bookings.",
    )


# --- 3. MAIN BOOKING ADMIN ---


@admin.register(Booking)
class BookingAdmin(ModelAdmin):
    form = BookingAdminForm
    autocomplete_fields = ["client"]

    list_display = (
        "ref",
        "client",
        "created_at",  # Using created_at instead of trip_date
        "booking_type",
        "supplier_payment_status",  # <--- NEW: The Status Dot
        "total_amount",
        "status_badge",
        "balance_display",
        "invoice_link",
    )

    list_filter = (
        OutstandingFilter,
        "payment_status",
        "supplier_payment_status",
        "booking_type",
        "created_at",
    )

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
    actions = [
        "configure_whatsapp_send",
        "send_whatsapp_tn",
        "send_whatsapp_fr",
        "cancel_booking",
        pay_via_ledger,
    ]  # Added cancel_booking
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

        if action == "none" or not amount:
            return

        # 1. ADD PAYMENT
        if action == "payment":
            Payment.objects.create(
                booking=obj,
                amount=amount,
                method=method,
                transaction_type="payment",
                date=datetime.now().date(),
                reference="MANUAL-ENTRY",
                created_by=request.user,
            )
            self.message_user(request, f"✅ Payment of {amount} Recorded.")

        # 2. ISSUE REFUND
        elif action == "refund":
            Payment.objects.create(
                booking=obj,
                amount=amount,  # Store positive number, logic handles the rest
                method=method,
                transaction_type="refund",
                date=datetime.now().date(),
                reference="MANUAL-REFUND",
                created_by=request.user,
            )
            self.message_user(request, f"💸 Refund of {amount} Issued.")

        # 3. SUPPLIER PAYMENT (Does not affect Customer Status)
        elif action == "supplier_payment":
            # Just a ledger entry, no Payment object linked to customer balance
            LedgerEntry.objects.create(
                date=datetime.now().date(),
                account=f"Supplier Pay - {obj.ref}",
                entry_type="supplier_payment",
                debit=amount,
                credit=0,
                booking=obj,
                created_by=request.user,
            )
            self.message_user(request, f"📤 Supplier Payment of {amount} Recorded.")

    # --- NEW ACTION: CANCEL BOOKING ---
    @admin.action(description="🚫 Cancel Booking (Full Refund)")
    def cancel_booking(self, request, queryset):
        for booking in queryset:
            with transaction.atomic():
                # 1. Calculate what was paid
                paid = (
                    booking.payments.filter(transaction_type="payment").aggregate(
                        Sum("amount")
                    )["amount__sum"]
                    or 0
                )
                refunded = (
                    booking.payments.filter(transaction_type="refund").aggregate(
                        Sum("amount")
                    )["amount__sum"]
                    or 0
                )
                net_balance = paid - refunded

                # 2. Issue Refund if money exists
                if net_balance > 0:
                    Payment.objects.create(
                        booking=booking,
                        amount=net_balance,
                        transaction_type="refund",
                        date=datetime.now().date(),
                        method="CASH",  # Default to Cash for safety
                        reference="AUTO-CANCEL-REFUND",
                        created_by=request.user,
                    )

                # 3. Update Status
                booking.status = "cancelled"
                booking.save()

        self.message_user(
            request, f"✅ {queryset.count()} booking(s) cancelled and refunded."
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
        # Calculate Refunds to see if we need to show the tag
        refunds = obj.payments.filter(transaction_type="refund").aggregate(
            total=Coalesce(Sum("amount"), Value(Decimal("0.00")))
        )["total"]

        # SCENARIO A: BOOKING IS CANCELLED
        if obj.status == "cancelled":
            if refunds > 0:
                return format_html(
                    '<span style="color:#888; font-weight:bold;">🚫 Cancelled</span><br>'
                    '<span style="font-size:10px; color:#28a745;">(Full Refund)</span>'
                )
            return format_html(
                '<span style="color:#888; font-weight:bold;">🚫 Cancelled</span>'
            )

        colors = {
            "paid": "green",
            "advance": "orange",
            "pending": "red",
            "refunded": "gray",
        }
        color = colors.get(obj.payment_status, "gray")
        label = obj.get_payment_status_display() or "Unknown"

        # Standard Dot
        main_badge = format_html(
            f'<span style="color:{color}; font-weight:bold;">● {label}</span>'
        )

        # Append Refund Tag if money was returned
        if refunds > 0:
            return format_html(
                f"{main_badge}<br>"
                f'<span style="font-size:10px; color:#e0a800;">↩️ Refunded</span>'
            )

        return main_badge

    status_badge.short_description = "Status"

    def balance_display(self, obj):
        if not obj.pk:
            return "-"

        # 1. Calculate Payments & Refunds
        payments = obj.payments.filter(transaction_type="payment").aggregate(
            total=Coalesce(Sum("amount"), Value(Decimal("0.00")))
        )["total"]

        refunds = obj.payments.filter(transaction_type="refund").aggregate(
            total=Coalesce(Sum("amount"), Value(Decimal("0.00")))
        )["total"]

        # 2. Net Math: Balance = Total - (Paid - Refunded)
        # We keep the logic you requested: Refunds increase the Due Balance.
        net_paid = payments - refunds
        balance = obj.total_amount - net_paid

        # 3. Display Logic (Just Numbers)
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

    def get_readonly_fields(self, request, obj=None):
        """
        Dynamic Read-Only Logic:
        If the booking is CANCELLED, make ALL fields read-only (Grayed out).
        Otherwise, use the standard read-only fields.
        """
        # 1. Get standard read-only fields defined in the class
        standard_readonly = list(super().get_readonly_fields(request, obj))

        # 2. Check if object exists and is cancelled
        if obj and obj.status == "cancelled":
            # Get ALL field names in the model
            all_fields = [f.name for f in self.model._meta.fields]
            # Also add any non-model readonly fields you display (like balance_display)
            custom_fields = [
                "balance_display",
                "invoice_link",
                "send_whatsapp_link",
                "status_badge",
                "supplier_payment_status",
            ]
            return all_fields + custom_fields

        # 3. If not cancelled, return normal list
        return standard_readonly


# --- 4. OTHER ADMINS ---


@admin.register(Payment)
class PaymentAuditAdmin(ModelAdmin):
    list_display = ("date", "amount", "method", "booking", "reference")
    list_filter = ("method", "date")
    search_fields = ("booking__ref", "reference")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # If it's cancelled, you can LOOK (view), but you cannot CHANGE (save).
        if obj and obj.status == "cancelled":
            return False
        return super().has_change_permission(request, obj)


@admin.action(description="💰 Pay Expenses via Ledger")
def pay_expenses_via_ledger(modeladmin, request, queryset):
    """
    Creates a single Ledger Expense entry for selected Expenses
    and marks them as paid.
    Uses entry_type='expense' so it counts towards Supplier Costs/Consolidation.
    """
    # 1. Filter only unpaid expenses
    unpaid_expenses = queryset.filter(paid=False)

    if not unpaid_expenses.exists():
        messages.warning(request, "⚠️ No unpaid expenses selected.")
        return

    # 2. Calculate Total Safe Sum
    total_to_pay = unpaid_expenses.aggregate(
        total=Coalesce(
            Sum("amount"), Value(Decimal("0.00")), output_field=DecimalField()
        )
    )["total"]

    if total_to_pay <= 0:
        messages.warning(request, "⚠️ Total amount is 0.")
        return

    # 3. Create Ledger Entry & Update Status
    try:
        with transaction.atomic():
            # A. Create Ledger Entry (Money Out)
            LedgerEntry.objects.create(
                date=timezone.now(),
                account=f"Expense Payment ({unpaid_expenses.count()} items)",
                # CRITICAL: 'expense' type ensures it is calculated in Supplier Costs
                entry_type="expense",
                debit=total_to_pay,
                credit=0,
                created_by=request.user,
                is_consolidated=False,
            )

            # B. Mark Expenses as Paid
            rows_updated = unpaid_expenses.update(paid=True)

        messages.success(
            request,
            f"✅ Paid {total_to_pay} TND for {rows_updated} expenses via Ledger.",
        )

    except Exception as e:
        messages.error(request, f"❌ Error: {str(e)}")


@admin.register(Expense)
class ExpenseAdmin(ModelAdmin):
    list_display = ("name", "amount", "due_date", "paid", "supplier")
    list_filter = ("paid", "due_date")

    actions = [pay_expenses_via_ledger]


@admin.action(description="📈 Consolidate as Revenue (Close Day)")
def consolidate_daily_revenue(modeladmin, request, queryset):
    """
    Calculates GROSS Revenue (Client Cash In - Client Refunds) from selected rows.

    CRITICAL CHANGE: Does NOT subtract Supplier Costs from the Revenue figure.
    This ensures Profit = (Gross Revenue - Supplier Costs) works correctly in the view.

    Locking: Marks ALL selected rows (Clients + Suppliers) as consolidated
    so they cannot be processed again.
    """
    # 1. Define Category Filters
    client_in_types = ["customer_payment", "payment", "income"]
    client_out_types = ["customer_refund", "refund"]

    # We define supplier types only to lock them, not to calc revenue
    supplier_types = ["supplier_payment", "expense", "supplier_cost"]

    all_valid_types = client_in_types + client_out_types + supplier_types

    # 2. Filter: Only Valid Types AND Not Yet Consolidated
    valid_entries = queryset.filter(
        entry_type__in=all_valid_types, is_consolidated=False
    )

    if not valid_entries.exists():
        messages.warning(request, "⚠️ No valid, unconsolidated rows selected.")
        return

    # 3. Helper for Safe Summing
    def get_sum(qs, field):
        return qs.aggregate(
            total=Coalesce(
                Sum(field), Value(Decimal("0.00")), output_field=DecimalField()
            )
        )["total"]

    # 4. Calculate Components (CLIENT SIDE ONLY)

    # A. Client Money
    client_in = get_sum(valid_entries.filter(entry_type__in=client_in_types), "debit")
    client_out = get_sum(
        valid_entries.filter(entry_type__in=client_out_types), "credit"
    )

    # 5. Gross Net Calculation
    # Formula: (Client Payments) - (Client Refunds)
    # We DO NOT subtract Supplier Costs here, because they exist as separate Debit entries
    # in the ledger and will be subtracted in the Profit calculation automatically.
    gross_revenue = client_in - client_out

    # 6. Create the Revenue Entry
    # We use the date of the most recent transaction
    closing_date = valid_entries.latest("date").date

    try:
        with transaction.atomic():
            # Create Revenue Entry (Credit Side)
            LedgerEntry.objects.create(
                date=closing_date,
                account=f"Daily Revenue Closing ({valid_entries.count()} txns)",
                entry_type="sale_revenue",
                debit=0,
                credit=gross_revenue,
                created_by=request.user,
                is_consolidated=True,
            )

            # 7. MARK ROWS AS CONSOLIDATED (The Lock)
            # We lock EVERYTHING selected (including expenses) so they are part of this "Closing"
            valid_entries.update(is_consolidated=True)

        messages.success(
            request,
            f"✅ Daily Gross Revenue of {gross_revenue} TND recognized. {valid_entries.count()} entries locked (Expenses included).",
        )

    except Exception as e:
        messages.error(request, f"❌ Error during consolidation: {str(e)}")


@admin.register(LedgerEntry)
class LedgerEntryAdmin(ModelAdmin):
    change_list_template = "admin/core/ledgerentry/change_list.html"
    list_display = (
        "date",
        "formatted_account",
        "entry_type",
        "formatted_debit",
        "formatted_credit",
        "consolidation_status",
        "booking",
    )
    list_filter = ("date", "entry_type", "is_consolidated", "account")
    date_hierarchy = "date"

    def consolidation_status(self, obj):
        if obj.is_consolidated:
            # Gray Lock for processed items
            return format_html(
                '<span style="color: #9ca3af; font-weight:bold; display:flex; align-items:center; gap:5px;">'
                "🔒 Consolidated"
                "</span>"
            )
        # Green Dot for items ready to be processed
        return format_html(
            '<span style="color: #10b981; font-weight:bold;">● Open</span>'
        )

    consolidation_status.short_description = "Status"

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
    actions = [consolidate_daily_revenue]

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)

        try:
            qs = response.context_data["cl"].queryset
        except (AttributeError, KeyError):
            return response

        # --- HELPER ---
        def get_sum(queryset, field):
            return queryset.aggregate(
                total=Coalesce(
                    Sum(field), Value(Decimal("0.00")), output_field=DecimalField()
                )
            )["total"]

        # --- 1. TOTAL REVENUE ---
        # Sum of all Sale Revenue entries (These are usually Consolidated items)
        revenue_qs = qs.filter(entry_type="sale_revenue")
        total_revenue = get_sum(revenue_qs, "credit")

        # --- 2. CASH COLLECTED (Client Side Only) ---
        # A. Client Money IN (Debit)
        client_in_qs = qs.filter(
            entry_type__in=["customer_payment", "payment", "income"]
        )
        client_cash_in = get_sum(client_in_qs, "debit")

        # B. Client Money OUT (Credit)
        client_out_qs = qs.filter(entry_type__in=["customer_refund", "refund"])
        client_refunds = get_sum(client_out_qs, "credit")

        # RESULT: "Cash Collected" = Client In - Client Out
        # This ignores supplier costs, keeping your 900.00 TND figure intact.
        cash_collected = client_cash_in - client_refunds

        # --- 3. SUPPLIER COST (Net) ---
        # Filters: entry_type="supplier_payment", "expense"
        supplier_qs = qs.filter(
            entry_type__in=["supplier_payment", "expense", "supplier_cost"]
        )

        # A. Money Out to Supplier (Debit)
        supplier_paid = get_sum(supplier_qs, "debit")

        # B. Money Back from Supplier (Credit)
        supplier_refunded = get_sum(supplier_qs, "credit")

        # RESULT: Net Supplier Cost (Paid - Refunded)
        # This ensures 2450 - 1000 = 1450.00 TND
        net_supplier_cost = supplier_paid - supplier_refunded

        # --- 4. PROFIT ---
        # Invoiced Revenue - Net Supplier Costs
        profit = total_revenue - net_supplier_cost

        # --- PASS TO TEMPLATE ---
        response.context_data["summary"] = {
            "revenue": total_revenue,
            "expense": net_supplier_cost,  # Shows Net Cost (1450.00)
            "profit": profit,
            "net_cash": cash_collected,  # Shows Client Cash Only (900.00)
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
