# core/models.py
from simple_history.models import HistoricalRecords
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal

User = get_user_model()

class Client(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=40, blank=True, null=True)
    passport = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name

class Supplier(models.Model):
    name = models.CharField(max_length=200)
    contact = models.CharField(max_length=200, blank=True, null=True)
    def __str__(self): return self.name

class Booking(models.Model):
    BOOKING_TYPES = [('outgoing_hotel','Outgoing Hotel'), ('local_hotel','Local Hotel'), ('ticket', 'Ticket'), ('omra','Omra'), ('trip','Trip'), ('visa_app','Visa / Services - Application'), ('visa_dummy','Visa / Services - Dummy Booking')]
    STATUS_CHOICES = [('pending','Pending'), ('advance','Advance'), ('confirmed','Confirmed'), ('change','Change'), ('refund','Refund'), ('completed','Completed')]
    ref = models.CharField(max_length=30, unique=True, blank=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    booking_type = models.CharField(max_length=40, choices=BOOKING_TYPES)
    description = models.TextField(blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2) 
    supplier_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00')) 
    is_supplier_paid = models.BooleanField(default=False, help_text="System flag: True if supplier cost has been deducted from ledger")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='booked_by')
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    history = HistoricalRecords() # <--- NEW: Tracks every save/change
    
    def save(self, *args, **kwargs):
        if not self.ref:
            today_str = timezone.now().strftime('%Y%m%d')
            prefix = f"BK-{today_str}"
            count = Booking.objects.filter(ref__startswith=prefix).count()
            new_ref = f"{prefix}-{count + 1:03d}"
            while Booking.objects.filter(ref=new_ref).exists():
                count += 1
                new_ref = f"{prefix}-{count + 1:03d}"
            self.ref = new_ref
        super().save(*args, **kwargs)

    @property
    def paid_amount(self): return self.payments.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
    @property
    def outstanding(self): return self.total_amount - self.paid_amount
    @property
    def percent_paid(self): return 0 if self.total_amount == 0 else (self.paid_amount / self.total_amount) * 100
    def __str__(self): return f"{self.ref} ({self.client.name})"

class Payment(models.Model):
    PAYMENT_METHODS = [('cash','Cash'), ('card','Card'), ('bank','Bank Transfer'), ('mobile','Mobile Money')]
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='payments', null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    date = models.DateField()
    reference = models.CharField(max_length=100, blank=True, null=True) 
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"Payment of {self.amount} for {self.booking.ref if self.booking else 'N/A'}"
    history = HistoricalRecords() # <--- NEW

class Expense(models.Model):
    name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField()
    paid = models.BooleanField(default=False)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True)
    recurrence = models.CharField(max_length=20, blank=True, null=True)
    def __str__(self): return self.name
    history = HistoricalRecords() # <--- NEW

class LedgerEntry(models.Model):
    date = models.DateField()
    account = models.CharField(max_length=100) 
    debit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    booking = models.ForeignKey(Booking, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    def __str__(self): return f"{self.date} - {self.account}: Dr={self.debit}, Cr={self.credit}"

class KnowledgeBase(models.Model):
    CATEGORY_CHOICES = [('outgoing', 'Outgoing'), ('locale', 'Locale'), ('billetterie', 'Billetterie'), ('omra', 'Omra'), ('voyages', 'Voyages organisés'), ('visas', 'Visas'), ('autre', 'Autre')]
    UTILITY_CHOICES = [(i, str(i)) for i in range(1, 6)]
    title = models.CharField(max_length=200, verbose_name="Titre de l'article")
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, verbose_name="Catégorie principale")
    summary = models.TextField(verbose_name="Résumé", help_text="Description concise en 2-3 lignes")
    objective = models.TextField(verbose_name="Objectif principal", blank=True)
    prerequisites = models.TextField(verbose_name="Pré-requis", blank=True, help_text="Compétences, outils, informations nécessaires")
    procedure = models.TextField(verbose_name="Procédure détaillée", help_text="Format long, numérotez clairement chaque étape")
    example = models.TextField(verbose_name="Exemple concret", blank=True)
    escalation_contact = models.CharField(max_length=200, verbose_name="Contacts d'escalade", blank=True)
    tags = models.CharField(max_length=200, verbose_name="Mots-clés / Tags", blank=True, help_text="Séparez-les par des virgules")
    utility_score = models.IntegerField(verbose_name="Utilité", choices=UTILITY_CHOICES, default=3)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Auteur")
    def __str__(self): return f"[{self.get_category_display()}] {self.title}"
    class Meta: verbose_name = "Base de Connaissances"; verbose_name_plural = "Base de Connaissances"

# --- NEW: ANNOUNCEMENT MODEL ---
class Announcement(models.Model):
    PRIORITY_CHOICES = [('low', 'ℹ️ Info'), ('medium', '⚠️ Important'), ('high', '🚨 Critical')]
    title = models.CharField(max_length=200)
    content = models.TextField(help_text="Write your update here.")
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='low')
    acknowledged_by = models.ManyToManyField(User, blank=True, related_name='acknowledged_announcements', editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_announcements')
    def __str__(self): return f"[{self.get_priority_display()}] {self.title}"
    @property
    def approval_count(self): return self.acknowledged_by.count()
    class Meta: ordering = ['-created_at']
