# core/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Sum
from rangefilter.filters import DateRangeFilterBuilder
from .models import Client, Supplier, Booking, Payment, Expense, LedgerEntry

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'passport', 'created_at')
    search_fields = ('name', 'phone', 'passport')

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact')

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    # 1. Added 'invoice_link' to the list display
    list_display = ('ref', 'client', 'booking_type', 'total_amount', 'paid_amount', 'outstanding', 'status', 'invoice_link')
    
    list_filter = ('status', 'booking_type', 'created_at')
    search_fields = ('ref', 'client__name')
    
    # 2. Added 'invoice_link' to read-only fields so it appears inside the form too
    readonly_fields = ('ref', 'created_at', 'invoice_link')

    # 3. The logic to generate the PDF button
    def invoice_link(self, obj):
        if obj.pk:
            url = reverse('invoice_pdf', args=[obj.pk])
            return format_html('<a class="button" href="{}" target="_blank">🖨️ Print Invoice</a>', url)
        return "-"
    invoice_link.short_description = "Invoice"

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('date', 'amount', 'method', 'booking', 'reference')
    list_filter = ('method', 'date')
    search_fields = ('booking__ref', 'reference')

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('name', 'amount', 'due_date', 'paid', 'supplier')
    list_filter = ('paid', 'due_date')

@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    # Point to the custom template for the dashboard
    change_list_template = 'admin/core/ledgerentry/change_list.html'
    
    list_display = ('date', 'formatted_account', 'formatted_debit', 'formatted_credit', 'booking')
    
    # Enables Start/End picker
    list_filter = (
        ("date", DateRangeFilterBuilder()), 
        "account"
    )
    
    date_hierarchy = 'date' # Adds the breadcrumb date nav
    
    # --- VISUAL FORMATTING ---
    def formatted_account(self, obj):
        if obj.account.startswith('Revenue'):
            return format_html('<span style="color: green; font-weight:bold;">{}</span>', obj.account)
        elif obj.account.startswith('Expense'):
            return format_html('<span style="color: red; font-weight:bold;">{}</span>', obj.account)
        return obj.account
    formatted_account.short_description = "Account"

    def formatted_debit(self, obj):
        if obj.debit > 0:
            return format_html('<span style="color: #aa0000;">{}</span>', obj.debit)
        return "-"
    formatted_debit.short_description = "Debit"

    def formatted_credit(self, obj):
        if obj.credit > 0:
            return format_html('<span style="color: #008800;">{}</span>', obj.credit)
        return "-"
    formatted_credit.short_description = "Credit"

    # --- DASHBOARD CALCULATION LOGIC ---
    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)

        # Ensure we are looking at the list view (not an error or redirect)
        if hasattr(response, 'context_data') and 'cl' in response.context_data:
            qs = response.context_data['cl'].queryset

            # 1. Calculate Revenue (Sum of Credits in Revenue accounts)
            revenue = qs.filter(account__startswith='Revenue').aggregate(total=Sum('credit'))['total'] or 0
            
            # 2. Calculate Expenses (Sum of Debits in Expense accounts)
            # Note: We include both 'Expense:' (Supplier Cost) and regular operational expenses
            expense = qs.filter(account__startswith='Expense').aggregate(total=Sum('debit'))['total'] or 0

            # 3. Calculate Net Profit
            profit = revenue - expense

            # Send data to the template
            response.context_data['summary'] = {
                'revenue': revenue,
                'expense': expense,
                'profit': profit
            }
        
        return response
    
    # CRITICAL: Prevent manual deletion of ledger entries for audit safety
    def has_delete_permission(self, request, obj=None):
        return False
