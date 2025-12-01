# core/models.py
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from simple_history.models import HistoricalRecords # Audit Log

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
    BOOKING_TYPES = [
        ('ticket', 'Ticket'),
        ('outgoing_hotel','Outgoing Hotel'),
        ('local_hotel','Local Hotel'),
        ('omra','Omra'),
        ('trip','Trip'),
        ('visa_app','Visa / Services - Application'),
        ('visa_dummy','Visa / Services - Dummy Booking'),
    ]
    STATUS_CHOICES = [('pending','Pending'), ('advance','Advance'), ('confirmed','Confirmed'), ('change','Change'), ('refund','Refund'), ('completed','Completed')]
    
    ref = models.CharField(max_length=30, unique=True, blank=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    booking_type = models.CharField(max_length=40, choices=BOOKING_TYPES)
    description = models.TextField(blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2) 
    supplier_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00')) 
    is_supplier_paid = models.BooleanField(default=False, help_text="System flag")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='booked_by')
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    history = HistoricalRecords() # Audit Log

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
    def approval_count(self):
        return self.acknowledged_by.count()

# --- WHATSAPP CONFIGURATION ---
class WhatsAppSettings(models.Model):
    name = models.CharField(max_length=50, default="Configuration")
    api_url = models.URLField(help_text="e.g. https://api.ultramsg.com/...")
    api_token = models.CharField(max_length=200)
    template_tn = models.TextField("Message (Tunisian)", default="عسلامة {client_name}،\nباش نكمّلو دوسي الفيزا، يرحم والديك عمرلنا الفورمولار هذا:\n{link}\n\nDima Voyage.")
    template_fr = models.TextField("Message (Français)", default="Bonjour {client_name},\nMerci de remplir ce formulaire pour compléter votre dossier de visa:\n{link}\n\nCordialement, Dima Voyage.")
    def __str__(self): return self.name
    class Meta: verbose_name_plural = "WhatsApp Settings"

# --- VISA APPLICATION (ARABIC FORM) ---
class VisaApplication(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='visa_data')
    
    # Section 1
    full_name = models.CharField("الاسم الكامل (باسبور)", max_length=200)
    dob = models.DateField("تاريخ الولادة")
    nationality = models.CharField("الجنسية", max_length=100)
    passport_number = models.CharField("رقم الباسبور", max_length=50)
    passport_issue_date = models.DateField("تاريخ إصدار الباسبور")
    passport_expiry_date = models.DateField("تاريخ انتهاء الباسبور")
    has_previous_visa = models.BooleanField("عملت فيزا في 5 سنين اللي فاتو؟", default=False)
    previous_visa_details = models.TextField("تفاصيل الفيزا السابقة", blank=True, null=True)
    phone = models.CharField("رقم الهاتف", max_length=50)
    email = models.EmailField("الإيميل")
    address = models.TextField("العنوان الكامل")
    photo = models.ImageField("صور شمسية", upload_to='visas/photos/')

    # Section 2
    travel_reason = models.CharField("سبب السفر", max_length=200)
    departure_date = models.DateField("تاريخ الذهاب")
    return_date = models.DateField("تاريخ الرجوع")
    itinerary = models.TextField("المدن / البرنامج", blank=True)
    ticket_departure = models.FileField("تذكرة الذهاب", upload_to='visas/tickets/', blank=True, null=True)
    ticket_return = models.FileField("تذكرة العودة", upload_to='visas/tickets/', blank=True, null=True)
    travel_insurance = models.FileField("التأمين على السفر", upload_to='visas/insurance/', blank=True, null=True)

    # Section 3
    ACCOMMODATION_TYPES = [('hotel', 'فندق'), ('host', 'عند مستضيف'), ('other', 'نوع آخر')]
    accommodation_type = models.CharField("نوع الإقامة", max_length=20, choices=ACCOMMODATION_TYPES, default='hotel')
    host_name = models.CharField("اسم المستضيف", max_length=200, blank=True)
    host_address = models.TextField("عنوان المستضيف", blank=True)
    host_phone = models.CharField("رقم هاتف المستضيف", max_length=50, blank=True)
    host_email = models.EmailField("إيميل المستضيف", blank=True)
    host_relationship = models.CharField("العلاقة بالمستضيف", max_length=100, blank=True)
    hotel_name = models.CharField("اسم الفندق", max_length=200, blank=True)
    hotel_address = models.TextField("عنوان الفندق", blank=True)
    hotel_reservation = models.FileField("نسخة من حجز الفندق", upload_to='visas/hotels/', blank=True, null=True)

    # Section 4
    PAYER_TYPES = [('self', 'أنت'), ('host', 'المستضيف'), ('sponsor', 'ضامن'), ('other', 'آخر')]
    payer = models.CharField("شكون باش يتكفّل بالمصاريف؟", max_length=20, choices=PAYER_TYPES, default='self')
    guarantor_details = models.TextField("تفاصيل الضامن", blank=True)
    financial_proofs = models.FileField("وثائق إثبات الموارد", upload_to='visas/financials/', blank=True, null=True)

    # Section 5
    emergency_contact = models.TextField("شخص للاتصال في الحالات الاستعجالية")
    consent_accurate = models.BooleanField("تأكيد صحة المعلومات", default=False)
    consent_data = models.BooleanField("الموافقة على جمع البيانات", default=False)
    consent_send_docs = models.BooleanField("الموافقة على الإرسال", default=False)

    submitted_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"Visa: {self.full_name}"

class AmadeusSettings(models.Model):
    ENV_CHOICES = [
        ('test', 'Test / Sandbox'),
        ('production', 'Live / Production'),
    ]

    name = models.CharField(max_length=50, default="Amadeus Configuration")
    client_id = models.CharField("API Key", max_length=100, help_text="From Amadeus Dashboard")
    client_secret = models.CharField("API Secret", max_length=100, help_text="From Amadeus Dashboard")
    environment = models.CharField(max_length=20, choices=ENV_CHOICES, default='test')
    
    def __str__(self):
        return f"Amadeus ({self.get_environment_display()})"

    class Meta:
        verbose_name = "Amadeus API Settings"
        verbose_name_plural = "Amadeus API Settings"
