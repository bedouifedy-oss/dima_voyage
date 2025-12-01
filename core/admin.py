# core/admin.py
import secrets
import string
from datetime import datetime
from django.contrib import admin, messages
from django.utils.html import format_html
from django.urls import reverse
from django.db import models  # <--- Essential for the Filter to work
from django.db.models import Sum, F, Value
from django.db.models.functions import Coalesce
from rangefilter.filters import DateRangeFilterBuilder
from unfold.admin import ModelAdmin

from .models import (
    Client, Supplier, Booking, Payment, Expense, LedgerEntry,
    KnowledgeBase, Announcement, User, VisaApplication, WhatsAppSettings,
    AmadeusSettings
)
from .forms import BookingAdminForm

# --- CUSTOM FILTERS ---
class OutstandingFilter(admin.SimpleListFilter):
    title = 'Outstanding Balance'
    parameter_name = 'outstanding_status'
    
    def lookups(self, request, model_admin): 
        return (('yes', 'Has Outstanding Balance'), ('no', 'Fully Paid'))
    
    def queryset(self, request, queryset):
        qs = queryset.annotate(db_paid=Coalesce(Sum('payments__amount'), Value(0), output_field=models.DecimalField()))
        if self.value() == 'yes': return qs.filter(total_amount__gt=F('db_paid'))
        if self.value() == 'no': return qs.filter(total_amount__lte=F('db_paid'))
        return queryset

# --- 1. REGISTER DEPENDENCIES FIRST ---

@admin.register(Client)
class ClientAdmin(ModelAdmin):
    list_display = ('name', 'phone', 'passport', 'created_at')
    search_fields = ('name', 'phone', 'passport')

@admin.register(Supplier)
class SupplierAdmin(ModelAdmin):
    list_display = ('name', 'contact')
    search_fields = ('name',)

# --- 2. INLINES ---

class PaymentHistoryInline(admin.TabularInline):
    """Read-Only history. Agents use the Command Center buttons instead."""
    model = Payment
    fields = ('date', 'amount', 'method', 'reference')
    readonly_fields = ('date', 'amount', 'method', 'reference')
    extra = 0
    can_delete = False
    verbose_name = "📜 Transaction History"
    verbose_name_plural = "Transaction History"

class VisaInline(admin.StackedInline):
    model = VisaApplication
    can_delete = False
    verbose_name_plural = '📄 Visa Application Data'
    fields = (('full_name', 'passport_number'), 'photo', 'financial_proofs')
    readonly_fields = ('submitted_at',)
    extra = 0

# --- 3. MAIN BOOKING ADMIN ---

@admin.register(Booking)
class BookingAdmin(ModelAdmin):
    form = BookingAdminForm
    autocomplete_fields = ['client']
    
    list_display = (
        'ref', 
        'client', 
        'created_at',  # Using created_at instead of trip_date
        'total_amount', 
        'status_badge',  
        'balance_display',
        'invoice_link'
    )
    
    list_filter = (
        OutstandingFilter, 
        'payment_status', 
        'booking_type', 
        'created_at'
    )
    search_fields = ('ref', 'client__name', 'client__phone', 'client__passport')
    
    readonly_fields = ('ref', 'payment_status', 'created_at', 'balance_display', 'invoice_link')

    fieldsets = (
        ('✈️ Trip & Customer', {
            'fields': (
                ('ref', 'created_at'), 
                'client', 
                'booking_type', # <--- FIXED: Removed 'trip_date' from here
                'description'
            )
        }),
        ('🔄 Operation (Changes/Refunds)', {
            'fields': (('operation_type', 'parent_booking'),),
            'classes': ('collapse',), 
            'description': "Link to a parent booking if this is a modification."
        }),
        ('💰 Financials', {
            'fields': (('total_amount', 'supplier_cost'), 'balance_display'),
        }),
        ('💳 Payment Command Center', {
            'fields': ('payment_action', ('transaction_amount', 'transaction_method')),
            'classes': ('background-gray',), 
            'description': "Select an action to instantly update status and ledger."
        }),
    )

    inlines = [VisaInline, PaymentHistoryInline]

    def save_model(self, request, obj, form, change):
        # A. Auto-Generate Reference
        if not obj.ref:
            year_suffix = str(datetime.now().year)[-2:]
            unique_code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
            obj.ref = f"DV-{year_suffix}-{unique_code}"

        # B. Save Booking
        super().save_model(request, obj, form, change)

        # C. Process Payment Ghost Fields
        action = form.cleaned_data.get('payment_action')
        amount = form.cleaned_data.get('transaction_amount')
        method = form.cleaned_data.get('transaction_method')

        if action == 'none': return

        final_amount = 0
        if action == 'full':
            paid_so_far = obj.payments.aggregate(Sum('amount'))['amount__sum'] or 0
            final_amount = obj.total_amount - paid_so_far
        elif action == 'partial':
            final_amount = amount
        elif action == 'refund':
            final_amount = -abs(amount) 

        if final_amount != 0:
            Payment.objects.create(
                booking=obj,
                amount=final_amount,
                method=method,
                date=datetime.now().date(),
                reference=f"AUTO-{action.upper()}"
            )
            self.message_user(request, f"✅ Processed {action.upper()}: {final_amount} TND")

    # --- UI Helpers ---
    def status_badge(self, obj):
        colors = {'PAID': 'green', 'PARTIAL': 'orange', 'PENDING': 'red', 'REFUNDED': 'gray'}
        color = colors.get(obj.payment_status, 'gray')
        label = obj.get_payment_status_display() if obj.payment_status else "Unknown"
        return format_html(f'<span style="color:{color}; font-weight:bold;">● {label}</span>')
    status_badge.short_description = "Status"

    def balance_display(self, obj):
        if not obj.pk: return "-"
        paid = obj.payments.aggregate(Sum('amount'))['amount__sum'] or 0
        balance = obj.total_amount - paid
        
        if balance > 0:
            return format_html(f'<b style="color:#d9534f;">{balance:,.2f} TND Due</b>')
        elif balance == 0:
            return format_html('<b style="color:#5cb85c;">✔ Settled</b>')
        else:
            return format_html(f'<b style="color:#0275d8;">{abs(balance):,.2f} TND (Credit)</b>')
    balance_display.short_description = "Balance"

    def invoice_link(self, obj):
        if obj.pk:
            return format_html('<a href="#" target="_blank" class="button">🖨️ Invoice</a>') 
        return "-"
    invoice_link.short_description = "Invoice"

# --- 4. OTHER ADMINS ---

@admin.register(Payment)
class PaymentAuditAdmin(ModelAdmin):
    list_display = ('date', 'amount', 'method', 'booking', 'reference')
    list_filter = ('method', 'date')
    search_fields = ('booking__ref', 'reference')
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False

@admin.register(Expense)
class ExpenseAdmin(ModelAdmin):
    list_display = ('name', 'amount', 'due_date', 'paid', 'supplier')
    list_filter = ('paid', 'due_date')

@admin.register(LedgerEntry)
class LedgerEntryAdmin(ModelAdmin):
    change_list_template = 'admin/core/ledgerentry/change_list.html'
    list_display = ('date', 'formatted_account', 'formatted_debit', 'formatted_credit', 'booking')
    list_filter = ('date', 'account')
    date_hierarchy = 'date'
    
    def formatted_account(self, obj):
        if obj.account.startswith('Revenue'): return format_html('<span style="color: green; font-weight:bold;">{}</span>', obj.account)
        elif obj.account.startswith('Expense'): return format_html('<span style="color: red; font-weight:bold;">{}</span>', obj.account)
        return obj.account
    formatted_account.short_description = "Account"

    def formatted_debit(self, obj): return format_html('<span style="color: #aa0000;">{}</span>', obj.debit) if obj.debit > 0 else "-"
    formatted_debit.short_description = "Debit"

    def formatted_credit(self, obj): return format_html('<span style="color: #008800;">{}</span>', obj.credit) if obj.credit > 0 else "-"
    formatted_credit.short_description = "Credit"
    
    # --- THIS WAS MISSING: It calculates the totals ---
    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        
        # Check if we have data to summarize
        if hasattr(response, 'context_data') and 'cl' in response.context_data:
            qs = response.context_data['cl'].queryset
            
            # 1. Calculate Total Revenue (Credits to Revenue accounts)
            revenue = qs.filter(account__startswith='Revenue').aggregate(total=Sum('credit'))['total'] or 0
            
            # 2. Calculate Total Expenses (Debits to Expense accounts)
            expense = qs.filter(account__startswith='Expense').aggregate(total=Sum('debit'))['total'] or 0
            
            # 3. Inject into template
            response.context_data['summary'] = {
                'revenue': revenue, 
                'expense': expense, 
                'profit': revenue - expense
            }
            
        return response
    
    def has_delete_permission(self, request, obj=None): return False
@admin.register(Announcement)
class AnnouncementAdmin(ModelAdmin):
    list_display = ('title', 'priority', 'created_at', 'approval_progress', 'user_status')
    list_filter = ('priority', 'created_at')
    
    def approval_progress(self, obj):
        count = obj.acknowledged_by.count()
        total_staff = User.objects.filter(is_active=True).count() or 1
        percent = int((count / total_staff) * 100)
        color = "green" if percent == 100 else "orange"
        return format_html(f'<div style="width:100px; background:#eee; border-radius:4px; overflow:hidden;"><div style="width:{percent}%; background:{color}; height:10px;"></div></div>')
    approval_progress.short_description = "Progress"
    
    def user_status(self, obj):
        return f"{obj.acknowledged_by.count()} Approvals"

@admin.register(WhatsAppSettings)
class WhatsAppSettingsAdmin(ModelAdmin):
    list_display = ('name', 'api_url')

@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(ModelAdmin):
    list_display = ('title', 'category', 'utility_score')

@admin.register(AmadeusSettings)
class AmadeusSettingsAdmin(ModelAdmin):
    list_display = ('name', 'environment', 'client_id')
