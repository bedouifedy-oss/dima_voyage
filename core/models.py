# core/models.py
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from simple_history.models import HistoricalRecords

User = get_user_model()

# --- SUPPORTING ACTORS ---
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

# --- THE CORE TRANSACTION MODEL ---
class Booking(models.Model):
    # 1. Service Types
    BOOKING_TYPES = [
        ('ticket', '✈️ Air Ticket'),
        ('hotel_out', '🏨 Outgoing Hotel'),
        ('hotel_loc', '🇹🇳 Local Hotel'),
        ('umrah', '🕋 Umrah Package'),
        ('trip', '🚌 Organized Trip'),
        ('visa_app','Visa Application'),
        ('transfer', '🚖 Transfer'),
        ('dummy', '📄 Dummy Booking'),
    ]
    
    # 2. Operations (The "Verb")
    OPERATION_TYPES = [
        ('issue', 'Issue / New Sale'),
        ('change', 'Change / Modification'),
        ('refund', 'Refund / Cancellation'),
    ]

    # 3. Financial Status (The "State")
    PAYMENT_STATUSES = [
        ('pending', 'Pending Payment'),
        ('advance', 'Partial / Advance'),
        ('paid', 'Fully Paid'),
        ('refunded', 'Refunded'),
        ('cancelled', 'Cancelled (Void)'), 
    ]

    ref = models.CharField(max_length=30, unique=True, blank=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    parent_booking = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='amendments', help_text="Link to original booking for Change/Refund")

    booking_type = models.CharField("Service Type", max_length=40, choices=BOOKING_TYPES)
    operation_type = models.CharField("Action", max_length=20, choices=OPERATION_TYPES, default='issue')
    payment_status = models.CharField("Payment Status", max_length=20, choices=PAYMENT_STATUSES, default='pending')
    
    description = models.TextField(blank=True)
    
    # --- Financials ---
    # For Issue/Change
    total_amount = models.DecimalField("Sale Price / Fee", max_digits=12, decimal_places=2, default=Decimal('0.00')) 
    supplier_cost = models.DecimalField("Supplier Cost", max_digits=12, decimal_places=2, default=Decimal('0.00')) 
    
    # For Refund Only
    refund_amount_client = models.DecimalField("Refund TO Client", max_digits=12, decimal_places=2, default=Decimal('0.00'))
    refund_amount_supplier = models.DecimalField("Refund FROM Supplier", max_digits=12, decimal_places=2, default=Decimal('0.00'))

    # Logic Flag
    is_ledger_posted = models.BooleanField(default=False, help_text="System Flag: Ledger entries created")
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='booked_by')
    created_at = models.DateTimeField(auto_now_add=True)
    
    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        if not self.ref:
            today_str = timezone.now().strftime('%Y%m%d')
            # Dynamic Prefix based on Operation
            prefix_map = {'issue': 'BK', 'change': 'CHG', 'refund': 'REF'}
            prefix = f"{prefix_map.get(self.operation_type, 'BK')}-{today_str}"
            
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
    def outstanding(self):
        if self.operation_type == 'refund': return Decimal('0.00')
        return self.total_amount - self.paid_amount

    def __str__(self): return f"{self.ref} ({self.get_booking_type_display()})"

# --- FINANCIAL MODELS ---
class Payment(models.Model):
    PAYMENT_METHODS = [('cash','Cash'), ('card','Card'), ('bank','Bank Transfer'), ('mobile','Mobile Money')]
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='payments', null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    date = models.DateField()
    reference = models.CharField(max_length=100, blank=True, null=True) 
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()
    def __str__(self): return f"Payment of {self.amount}"

class Expense(models.Model):
    name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField()
    paid = models.BooleanField(default=False)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True)
    recurrence = models.CharField(max_length=20, blank=True, null=True)
    history = HistoricalRecords()
    def __str__(self): return self.name

class LedgerEntry(models.Model):
    date = models.DateField()
    account = models.CharField(max_length=100) 
    debit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    booking = models.ForeignKey(Booking, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    def __str__(self): return f"{self.date} - {self.account}: Dr={self.debit}, Cr={self.credit}"

# --- SUPPORT MODELS ---
class KnowledgeBase(models.Model):
    CATEGORY_CHOICES = [('outgoing', 'Outgoing'), ('locale', 'Locale'), ('billetterie', 'Billetterie'), ('omra', 'Omra'), ('voyages', 'Voyages organisés'), ('visas', 'Visas'), ('autre', 'Autre')]
    UTILITY_CHOICES = [(i, str(i)) for i in range(1, 6)]
    title = models.CharField("Titre", max_length=200)
    category = models.CharField("Catégorie", max_length=50, choices=CATEGORY_CHOICES)
    summary = models.TextField("Résumé")
    objective = models.TextField("Objectif", blank=True)
    prerequisites = models.TextField("Pré-requis", blank=True)
    procedure = models.TextField("Procédure détaillée")
    example = models.TextField("Exemple", blank=True)
    escalation_contact = models.CharField("Contact Escalade", max_length=200, blank=True)
    tags = models.CharField("Tags", max_length=200, blank=True)
    utility_score = models.IntegerField("Utilité", choices=UTILITY_CHOICES, default=3)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    def __str__(self): return self.title
    class Meta: verbose_name_plural = "Knowledge Base"

class Announcement(models.Model):
    PRIORITY_CHOICES = [('low', 'ℹ️ Info'), ('medium', '⚠️ Important'), ('high', '🚨 Critical')]
    title = models.CharField(max_length=200)
    content = models.TextField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='low')
    acknowledged_by = models.ManyToManyField(User, blank=True, related_name='acknowledged_announcements', editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    def __str__(self): return self.title
    class Meta: ordering = ['-created_at']
    @property
    def approval_count(self): return self.acknowledged_by.count()

# --- SETTINGS MODELS ---
class WhatsAppSettings(models.Model):
    name = models.CharField(max_length=50, default="Configuration")
    api_url = models.URLField(help_text="e.g. https://api.ultramsg.com/...")
    api_token = models.CharField(max_length=200)
    template_tn = models.TextField("Message (Tunisian)", default="عسلامة {client_name}...\n{link}")
    template_fr = models.TextField("Message (Français)", default="Bonjour {client_name}...\n{link}")
    def __str__(self): return self.name
    class Meta: verbose_name_plural = "WhatsApp Settings"

class AmadeusSettings(models.Model):
    ENV_CHOICES = [('test', 'Test / Sandbox'), ('production', 'Live / Production')]
    name = models.CharField(max_length=50, default="Amadeus Configuration")
    client_id = models.CharField("API Key", max_length=100)
    client_secret = models.CharField("API Secret", max_length=100)
    environment = models.CharField(max_length=20, choices=ENV_CHOICES, default='test')
    def __str__(self): return f"Amadeus ({self.get_environment_display()})"
    class Meta: verbose_name = "Amadeus API Settings"; verbose_name_plural = "Amadeus API Settings"

# --- FLIGHT PARSER MODEL ---
class FlightTicket(models.Model):
    # (Kept mostly same, but relies on new Booking model)
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='ticket')
    raw_paste_data = models.TextField(blank=True)
    airline_code = models.CharField(max_length=10, blank=True)
    flight_number = models.CharField(max_length=10, blank=True)
    departure_city = models.CharField(max_length=10, blank=True)
    arrival_city = models.CharField(max_length=10, blank=True)
    real_departure_date = models.DateField(null=True, blank=True)
    departure_time = models.CharField(max_length=10, blank=True)
    arrival_time = models.CharField(max_length=10, blank=True)
    pnr_ref = models.CharField(max_length=10, default="XJ9K2M")
    live_status = models.CharField(max_length=50, default="Unknown")
    last_checked = models.DateTimeField(null=True, blank=True)
    
    # Simple regex parsing logic (Simplified here, paste your full logic if needed)
    def save(self, *args, **kwargs): super().save(*args, **kwargs)
    @property
    def status_color(self): return "gray" # Simplified
    def __str__(self): return f"Ticket: {self.booking.ref}"

# --- VISA APPLICATION MODEL ---
class VisaApplication(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='visa_data')
    full_name = models.CharField("الاسم الكامل", max_length=200)
    dob = models.DateField("تاريخ الولادة")
    nationality = models.CharField("الجنسية", max_length=100)
    passport_number = models.CharField("رقم الباسبور", max_length=50)
    passport_issue_date = models.DateField("تاريخ إصدار")
    passport_expiry_date = models.DateField("تاريخ انتهاء")
    has_previous_visa = models.BooleanField(default=False)
    previous_visa_details = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=50)
    email = models.EmailField()
    address = models.TextField()
    photo = models.ImageField(upload_to='visas/photos/')
    travel_reason = models.CharField(max_length=200)
    departure_date = models.DateField()
    return_date = models.DateField()
    itinerary = models.TextField(blank=True)
    ticket_departure = models.FileField(blank=True, null=True)
    ticket_return = models.FileField(blank=True, null=True)
    travel_insurance = models.FileField(blank=True, null=True)
    accommodation_type = models.CharField(max_length=20, default='hotel')
    host_name = models.CharField(blank=True, max_length=200)
    host_address = models.TextField(blank=True)
    host_phone = models.CharField(blank=True, max_length=50)
    host_email = models.EmailField(blank=True)
    host_relationship = models.CharField(blank=True, max_length=100)
    hotel_name = models.CharField(blank=True, max_length=200)
    hotel_address = models.TextField(blank=True)
    hotel_reservation = models.FileField(blank=True, null=True)
    payer = models.CharField(max_length=20, default='self')
    guarantor_details = models.TextField(blank=True)
    financial_proofs = models.FileField(blank=True, null=True)
    emergency_contact = models.TextField()
    consent_accurate = models.BooleanField(default=False)
    consent_data = models.BooleanField(default=False)
    consent_send_docs = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"Visa: {self.full_name}"
