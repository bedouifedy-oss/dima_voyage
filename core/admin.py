# core/admin.py
import requests
from django.contrib import admin, messages
from django.utils.html import format_html
from django.urls import reverse
from django.db import models 
from django.db.models import Sum, F, Value
from django.db.models.functions import Coalesce
from rangefilter.filters import DateRangeFilterBuilder
from unfold.admin import ModelAdmin
from .models import AmadeusSettings

from .models import (
    Client, Supplier, Booking, Payment, Expense, LedgerEntry, 
    KnowledgeBase, Announcement, User, VisaApplication, WhatsAppSettings
)

# --- CUSTOM FILTERS ---
class OutstandingFilter(admin.SimpleListFilter):
    title = 'Outstanding Balance'
    parameter_name = 'outstanding_status'
    def lookups(self, request, model_admin): return (('yes', 'Has Outstanding Balance'), ('no', 'Fully Paid'))
    def queryset(self, request, queryset):
        qs = queryset.annotate(db_paid=Coalesce(Sum('payments__amount'), Value(0), output_field=models.DecimalField()))
        if self.value() == 'yes': return qs.filter(total_amount__gt=F('db_paid'))
        if self.value() == 'no': return qs.filter(total_amount__lte=F('db_paid'))
        return queryset

# --- OPERATIONS ADMIN ---

@admin.register(Client)
class ClientAdmin(ModelAdmin):
    list_display = ('name', 'phone', 'passport', 'created_at')
    search_fields = ('name', 'phone', 'passport')

@admin.register(Supplier)
class SupplierAdmin(ModelAdmin):
    list_display = ('name', 'contact')

# NEW: Visa Inline (Shows the form data inside the Booking)
class VisaInline(admin.StackedInline):
    model = VisaApplication
    can_delete = False
    verbose_name_plural = '📄 Visa Application Data (From Client)'
    fields = (('full_name', 'passport_number'), 'photo', 'financial_proofs', 'ticket_departure', 'ticket_return')
    readonly_fields = ('submitted_at',)
    extra = 0

@admin.register(Booking)
class BookingAdmin(ModelAdmin):
    autocomplete_fields = ['client']
    list_display = ('ref', 'client', 'booking_type', 'total_amount', 'paid_amount', 'outstanding', 'status', 'invoice_link')
    list_filter = (OutstandingFilter, 'status', 'booking_type', 'created_at')
    search_fields = ('ref', 'client__name')
    readonly_fields = ('ref', 'created_at', 'invoice_link')
    
    inlines = [VisaInline] # <--- Added Inline
    actions = ['send_whatsapp_tn', 'send_whatsapp_fr'] # <--- Added Actions

    def invoice_link(self, obj):
        if obj.pk:
            url = reverse('invoice_pdf', args=[obj.pk])
            return format_html('<a class="button" href="{}" target="_blank">🖨️ Print Invoice</a>', url)
        return "-"
    invoice_link.short_description = "Invoice"
    
    class Media:
        css = {'all': ('https://cdnjs.cloudflare.com/ajax/libs/jqueryui/1.13.2/themes/smoothness/jquery-ui.min.css',)}
        js = (
            'https://cdnjs.cloudflare.com/ajax/libs/jquery/3.6.0/jquery.min.js',
            'https://cdnjs.cloudflare.com/ajax/libs/jqueryui/1.13.2/jquery-ui.min.js',
            'js/airport_search.js',
        )

    # --- WHATSAPP ACTIONS ---
    def send_whatsapp_tn(self, request, queryset):
        self._send_whatsapp_logic(request, queryset, lang='tn')
    send_whatsapp_tn.short_description = "🇹🇳 Send Visa Form (Tunisian)"

    def send_whatsapp_fr(self, request, queryset):
        self._send_whatsapp_logic(request, queryset, lang='fr')
    send_whatsapp_fr.short_description = "🇫🇷 Send Visa Form (French)"

    def _send_whatsapp_logic(self, request, queryset, lang):
        config = WhatsAppSettings.objects.first()
        if not config:
            self.message_user(request, "❌ Configure WhatsApp Settings first.", messages.ERROR)
            return

        count = 0
        for booking in queryset:
            if booking.client.phone:
                base_url = request.build_absolute_uri(reverse('public_visa_form', args=[booking.ref]))
                link = f"{base_url}?lang={lang}"
                
                msg_template = config.template_fr if lang == 'fr' else config.template_tn
                msg = msg_template.format(client_name=booking.client.name, link=link)
                
                try:
                    data = {"token": config.api_token, "to": booking.client.phone, "body": msg}
                    requests.post(config.api_url, data=data)
                    count += 1
                except: pass
        
        lang_name = "French" if lang == 'fr' else "Tunisian"
        self.message_user(request, f"✅ Sent {lang_name} form to {count} clients.")

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
    list_filter = (("date", DateRangeFilterBuilder()), "account")
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
    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        if hasattr(response, 'context_data') and 'cl' in response.context_data:
            qs = response.context_data['cl'].queryset
            revenue = qs.filter(account__startswith='Revenue').aggregate(total=Sum('credit'))['total'] or 0
            expense = qs.filter(account__startswith='Expense').aggregate(total=Sum('debit'))['total'] or 0
            response.context_data['summary'] = {'revenue': revenue, 'expense': expense, 'profit': revenue - expense}
        return response
    def has_delete_permission(self, request, obj=None): return False

# --- SUPPORT ADMIN ---

@admin.register(WhatsAppSettings)
class WhatsAppSettingsAdmin(ModelAdmin):
    list_display = ('name', 'api_url')

@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(ModelAdmin):
    list_display = ('title', 'category', 'utility_score', 'updated_at', 'author')
    list_filter = ('category', 'utility_score')
    search_fields = ('title', 'procedure', 'tags', 'summary')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (('Identification', {'fields': ('title', 'category', 'tags')}), ('Contenu Opérationnel', {'fields': ('summary', 'objective', 'prerequisites', 'procedure', 'example')}), ('Support', {'fields': ('escalation_contact', 'utility_score', 'author', 'created_at', 'updated_at')}))
    def save_model(self, request, obj, form, change):
        if not obj.author: obj.author = request.user
        super().save_model(request, obj, form, change)

@admin.register(Announcement)
class AnnouncementAdmin(ModelAdmin):
    list_display = ('title', 'priority', 'created_at', 'approval_progress', 'user_status')
    list_filter = ('priority', 'created_at')
    search_fields = ('title', 'content')
    readonly_fields = ('created_at', 'created_by', 'acknowledged_by')
    actions = ['mark_as_read']
    def mark_as_read(self, request, queryset):
        for announcement in queryset: announcement.acknowledged_by.add(request.user)
        self.message_user(request, "✅ You have successfully acknowledged the selected updates.")
    mark_as_read.short_description = "✅ SIGN / APPROVE Selected Updates"
    def approval_progress(self, obj):
        count = obj.acknowledged_by.count()
        total_staff = User.objects.filter(is_active=True).count()
        if total_staff == 0: return "0%"
        percent = int((count / total_staff) * 100)
        color = "green" if percent == 100 else "orange"
        return format_html(f'<div style="width:100px; background:#eee; border-radius:4px; overflow:hidden;"><div style="width:{percent}%; background:{color}; height:10px;"></div></div><span style="font-size:10px;">{count}/{total_staff} Staff</span>')
    approval_progress.short_description = "Approval Status"
    def user_status(self, obj): return f"{obj.approval_count} Approvals"
    def save_model(self, request, obj, form, change):
        if not obj.created_by: obj.created_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(AmadeusSettings)
class AmadeusSettingsAdmin(ModelAdmin):
    list_display = ('name', 'environment', 'client_id')
    
    # Security: Hide the secret in the list view
    def get_queryset(self, request):
        return super().get_queryset(request).defer('client_secret')
