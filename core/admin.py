# core/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db import models 
from django.db.models import Sum, F, Value
from django.db.models.functions import Coalesce
from rangefilter.filters import DateRangeFilterBuilder
from unfold.admin import ModelAdmin 

from .models import Client, Supplier, Booking, Payment, Expense, LedgerEntry, KnowledgeBase, Announcement, User

# --- CUSTOM FILTERS ---

class OutstandingFilter(admin.SimpleListFilter):
    title = 'Outstanding Balance'
    parameter_name = 'outstanding_status'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'Has Outstanding Balance'),
            ('no', 'Fully Paid'),
        )

    def queryset(self, request, queryset):
        qs = queryset.annotate(
            db_paid=Coalesce(
                Sum('payments__amount'), 
                Value(0), 
                output_field=models.DecimalField()
            )
        )
        
        if self.value() == 'yes':
            return qs.filter(total_amount__gt=F('db_paid'))
        
        if self.value() == 'no':
            return qs.filter(total_amount__lte=F('db_paid'))
        
        return queryset

# --- OPERATIONS ADMIN ---

@admin.register(Client)
class ClientAdmin(ModelAdmin):
    list_display = ('name', 'phone', 'passport', 'created_at')
    search_fields = ('name', 'phone', 'passport')

@admin.register(Supplier)
class SupplierAdmin(ModelAdmin):
    list_display = ('name', 'contact')

@admin.register(Booking)
class BookingAdmin(ModelAdmin):
    autocomplete_fields = ['client']
    list_display = ('ref', 'client', 'booking_type', 'total_amount', 'paid_amount', 'outstanding', 'status', 'invoice_link')
    list_filter = (OutstandingFilter, 'status', 'booking_type', 'created_at')
    search_fields = ('ref', 'client__name')
    readonly_fields = ('ref', 'created_at', 'invoice_link')

    def invoice_link(self, obj):
        if obj.pk:
            url = reverse('invoice_pdf', args=[obj.pk])
            return format_html('<a class="button" href="{}" target="_blank">🖨️ Print Invoice</a>', url)
        return "-"
    invoice_link.short_description = "Invoice"

# --- FINANCE ADMIN ---

@admin.register(Payment)
class PaymentAdmin(ModelAdmin):
    list_display = ('date', 'amount', 'method', 'booking', 'reference')
    list_filter = ('method', 'date')
    search_fields = ('booking__ref', 'reference')

@admin.register(Expense)
class ExpenseAdmin(ModelAdmin):
    list_display = ('name', 'amount', 'due_date', 'paid', 'supplier')
    list_filter = ('paid', 'due_date')

@admin.register(LedgerEntry)
class LedgerEntryAdmin(ModelAdmin):
    change_list_template = 'admin/core/ledgerentry/change_list.html'
    
    list_display = ('date', 'formatted_account', 'formatted_debit', 'formatted_credit', 'booking')
    
    list_filter = (
        ("date", DateRangeFilterBuilder()), 
        "account"
    )
    date_hierarchy = 'date' 
    
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

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        if hasattr(response, 'context_data') and 'cl' in response.context_data:
            qs = response.context_data['cl'].queryset
            revenue = qs.filter(account__startswith='Revenue').aggregate(total=Sum('credit'))['total'] or 0
            expense = qs.filter(account__startswith='Expense').aggregate(total=Sum('debit'))['total'] or 0
            profit = revenue - expense
            response.context_data['summary'] = {
                'revenue': revenue,
                'expense': expense,
                'profit': profit
            }
        return response
    
    def has_delete_permission(self, request, obj=None):
        return False

# --- SUPPORT ADMIN ---

@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(ModelAdmin):
    list_display = ('title', 'category', 'utility_score', 'updated_at', 'author')
    list_filter = ('category', 'utility_score')
    search_fields = ('title', 'procedure', 'tags', 'summary')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Identification', {
            'fields': ('title', 'category', 'tags')
        }),
        ('Contenu Opérationnel', {
            'fields': ('summary', 'objective', 'prerequisites', 'procedure', 'example')
        }),
        ('Support', {
            'fields': ('escalation_contact', 'utility_score', 'author', 'created_at', 'updated_at')
        }),
    )

    def save_model(self, request, obj, form, change):
        if not obj.author:
            obj.author = request.user
        super().save_model(request, obj, form, change)

# --- NEW: ANNOUNCEMENT ADMIN ---
@admin.register(Announcement)
class AnnouncementAdmin(ModelAdmin):
    list_display = ('title', 'priority', 'created_at', 'approval_progress', 'user_status')
    list_filter = ('priority', 'created_at')
    search_fields = ('title', 'content')
    readonly_fields = ('created_at', 'created_by', 'acknowledged_by')
    
    # The action button to mark as read
    actions = ['mark_as_read']

    def mark_as_read(self, request, queryset):
        for announcement in queryset:
            announcement.acknowledged_by.add(request.user)
        self.message_user(request, "✅ You have successfully acknowledged the selected updates.")
    mark_as_read.short_description = "✅ SIGN / APPROVE Selected Updates"

    # Progress bar for you (Manager)
    def approval_progress(self, obj):
        count = obj.acknowledged_by.count()
        total_staff = User.objects.filter(is_active=True).count()
        if total_staff == 0: return "0%"
        
        percent = int((count / total_staff) * 100)
        color = "green" if percent == 100 else "orange"
        
        return format_html(
            f'<div style="width:100px; background:#eee; border-radius:4px; overflow:hidden;">'
            f'<div style="width:{percent}%; background:{color}; height:10px;"></div>'
            f'</div><span style="font-size:10px;">{count}/{total_staff} Staff</span>'
        )
    approval_progress.short_description = "Approval Status"

    # Simple status for the logged-in user
    def user_status(self, obj):
        return f"{obj.approval_count} Approvals" 
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
