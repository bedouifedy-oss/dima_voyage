# core/models.py
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from .constants import (BOOKING_TYPES, OPERATION_TYPES,  # NEW IMPORT
                        PAYMENT_STATUSES)

User = get_user_model()


def default_visa_fields():
    return ["passport_number", "photo", "full_name"]


# --- SUPPORTING ACTORS ---
class Client(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=40, blank=True, null=True)
    passport = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Supplier(models.Model):
    name = models.CharField(max_length=200)
    contact = models.CharField(max_length=200, blank=True, null=True)

    def __str__(self):
        return self.name


# --- THE CORE TRANSACTION MODEL ---
class Booking(models.Model):
    # 1. Classification & Status
    ref = models.CharField(max_length=30, unique=True, blank=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    parent_booking = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="amendments",
        help_text="Link to original booking for Change/Refund",
    )
    visa_form_config = models.JSONField(
        default=default_visa_fields, blank=True, verbose_name="Public Form Fields"
    )
    # Choices are now imported from .constants
    booking_type = models.CharField(
        "Service Type", max_length=40, choices=BOOKING_TYPES
    )
    operation_type = models.CharField(
        "Action", max_length=20, choices=OPERATION_TYPES, default="issue"
    )
    payment_status = models.CharField(
        "Payment Status", max_length=20, choices=PAYMENT_STATUSES, default="pending"
    )

    description = models.TextField(blank=True)

    # 2. Financials
    total_amount = models.DecimalField(
        "Sale Price / Fee", max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    supplier_cost = models.DecimalField(
        "Supplier Cost", max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    refund_amount_client = models.DecimalField(
        "Refund TO Client",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Amount we give back to client",
    )
    refund_amount_supplier = models.DecimalField(
        "Refund FROM Supplier",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Amount received back from supplier",
    )

    # Flag: Replaces is_supplier_paid
    is_ledger_posted = models.BooleanField(
        default=False, help_text="System Flag: Ledger entries created"
    )

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="booked_by"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        if not self.ref:
            today_str = timezone.now().strftime("%Y%m%d")
            # Dynamic Prefix based on Operation
            prefix_map = {"issue": "BK", "change": "CHG", "refund": "REF"}
            prefix = f"{prefix_map.get(self.operation_type, 'BK')}-{today_str}"

            count = Booking.objects.filter(ref__startswith=prefix).count()
            new_ref = f"{prefix}-{count + 1:03d}"
            while Booking.objects.filter(ref=new_ref).exists():
                count += 1
                new_ref = f"{prefix}-{count + 1:03d}"
            self.ref = new_ref
        super().save(*args, **kwargs)

    @property
    def paid_amount(self):
        # Calculates total paid by summing related payments
        return self.payments.aggregate(total=models.Sum("amount"))["total"] or 0

    @property
    def outstanding(self):
        # Dynamic calculation
        return self.total_amount - self.paid_amount

    def __str__(self):
        return f"{self.ref} ({self.get_booking_type_display()})"


# --- FINANCIAL MODELS ---
class Payment(models.Model):
    # FIX 1: Uppercase keys to match forms.py and Admin logic
    PAYMENT_METHODS = [
        ("CASH", "Cash"),
        ("CARD", "Card"),
        ("BANK", "Bank Transfer"),
        ("MOBILE", "Mobile Money"),
        ("CHECK", "Check"),  # Added to match your form options
    ]

    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name="payments",  # Critical for Admin 'Balance' calculation
        null=True,
        blank=True,
    )

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default="CASH")
    date = models.DateField()
    reference = models.CharField(max_length=100, blank=True, null=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Tracking history is excellent for financial auditing
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.get_method_display()} of {self.amount}"


class Expense(models.Model):
    name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField()
    paid = models.BooleanField(default=False)
    supplier = models.ForeignKey(
        Supplier, on_delete=models.SET_NULL, null=True, blank=True
    )
    recurrence = models.CharField(max_length=20, blank=True, null=True)
    history = HistoricalRecords()

    def __str__(self):
        return self.name


class LedgerEntry(models.Model):
    date = models.DateField()
    account = models.CharField(max_length=100)
    debit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    booking = models.ForeignKey(
        Booking, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"{self.date} - {self.account}: Dr={self.debit}, Cr={self.credit}"


# --- SUPPORT MODELS ---
class KnowledgeBase(models.Model):
    CATEGORY_CHOICES = [
        ("outgoing", "Outgoing"),
        ("locale", "Locale"),
        ("billetterie", "Billetterie"),
        ("omra", "Omra"),
        ("voyages", "Voyages organisés"),
        ("circuits", "circuits"),
        ("visas", "Visas"),
        ("autre", "Autre"),
    ]
    UTILITY_CHOICES = [(i, str(i)) for i in range(1, 6)]
    title = models.CharField("Titre", max_length=200)
    category = models.CharField("Catégorie", max_length=50, choices=CATEGORY_CHOICES)
    summary = models.TextField("Résumé")
    objective = models.TextField("Objectif", blank=True)
    prerequisites = models.TextField("Pré-requis", blank=True)
    procedure = models.TextField("Procédure détaillée")
    example = models.TextField("Exemple", blank=True)
    escalation_contact = models.CharField(
        "Contact Escalade", max_length=200, blank=True
    )
    tags = models.CharField("Tags", max_length=200, blank=True)
    utility_score = models.IntegerField("Utilité", choices=UTILITY_CHOICES, default=3)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name_plural = "Knowledge Base"


class Announcement(models.Model):
    PRIORITY_CHOICES = [
        ("low", "ℹ️ Info"),
        ("medium", "⚠️ Important"),
        ("high", "🚨 Critical"),
    ]
    title = models.CharField(max_length=200)
    content = models.TextField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="low")
    acknowledged_by = models.ManyToManyField(
        User, blank=True, related_name="acknowledged_announcements", editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ["-created_at"]

    @property
    def approval_count(self):
        return self.acknowledged_by.count()


# --- SETTINGS MODELS ---
class WhatsAppSettings(models.Model):
    name = models.CharField(max_length=50, default="Configuration")
    api_url = models.URLField(help_text="e.g. https://api.ultramsg.com/...")
    api_token = models.CharField(max_length=200)
    template_tn = models.TextField(
        "Message (Tunisian)", default="عسلامة {client_name}...\n{link}"
    )
    template_fr = models.TextField(
        "Message (Français)", default="Bonjour {client_name}...\n{link}"
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "WhatsApp Settings"


class AmadeusSettings(models.Model):
    ENV_CHOICES = [("test", "Test / Sandbox"), ("production", "Live / Production")]
    name = models.CharField(max_length=50, default="Amadeus Configuration")
    client_id = models.CharField("API Key", max_length=100)
    client_secret = models.CharField("API Secret", max_length=100)
    environment = models.CharField(max_length=20, choices=ENV_CHOICES, default="test")

    def __str__(self):
        return f"Amadeus ({self.get_environment_display()})"

    class Meta:
        verbose_name = "Amadeus API Settings"
        verbose_name_plural = "Amadeus API Settings"


# --- FLIGHT PARSER MODEL ---
class FlightTicket(models.Model):
    # (Kept mostly same, but relies on new Booking model)
    booking = models.OneToOneField(
        Booking, on_delete=models.CASCADE, related_name="ticket"
    )
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

    # Simple regex parsing logic
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    @property
    def status_color(self):
        return "gray"

    def __str__(self):
        return f"Ticket: {self.booking.ref}"


# --- VISA APPLICATION MODEL ---
class VisaApplication(models.Model):
    booking = models.OneToOneField(
        Booking, on_delete=models.CASCADE, related_name="visa_data"
    )
    # --- ESSENTIALS (Public Form) ---
    # We keep these required because the form asks for them
    full_name = models.CharField(
        "الاسم الكامل", max_length=200, blank=True, null=True
    )  # Made optional just in case
    passport_number = models.CharField("رقم الباسبور", max_length=50)  # REQUIRED
    photo = models.ImageField(upload_to="visas/photos/")  # REQUIRED

    # --- DETAILS (Relaxed for later entry) ---
    dob = models.DateField("تاريخ الولادة", blank=True, null=True)
    nationality = models.CharField("الجنسية", max_length=100, blank=True, null=True)
    passport_issue_date = models.DateField("تاريخ إصدار", blank=True, null=True)
    passport_expiry_date = models.DateField("تاريخ انتهاء", blank=True, null=True)

    # --- OPTIONAL HISTORY ---
    has_previous_visa = models.BooleanField(default=False)
    previous_visa_details = models.TextField(blank=True, null=True)

    # --- CONTACT (Relaxed) ---
    phone = models.CharField(max_length=50, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)

    # --- TRIP DETAILS (Relaxed) ---
    travel_reason = models.CharField(max_length=200, blank=True, null=True)
    departure_date = models.DateField(blank=True, null=True)
    return_date = models.DateField(blank=True, null=True)
    itinerary = models.TextField(blank=True, null=True)

    # --- FILES (Already mostly optional, but ensuring consistency) ---
    ticket_departure = models.FileField(blank=True, null=True)
    ticket_return = models.FileField(blank=True, null=True)
    travel_insurance = models.FileField(blank=True, null=True)

    # --- ACCOMMODATION ---
    accommodation_type = models.CharField(
        max_length=20, default="hotel", blank=True, null=True
    )
    host_name = models.CharField(blank=True, max_length=200, null=True)
    host_address = models.TextField(blank=True, null=True)
    host_phone = models.CharField(blank=True, max_length=50, null=True)
    host_email = models.EmailField(blank=True, null=True)
    host_relationship = models.CharField(blank=True, max_length=100, null=True)
    hotel_name = models.CharField(blank=True, max_length=200, null=True)
    hotel_address = models.TextField(blank=True, null=True)
    hotel_reservation = models.FileField(blank=True, null=True)

    # --- FINANCIALS ---
    payer = models.CharField(max_length=20, default="self", blank=True, null=True)
    guarantor_details = models.TextField(blank=True, null=True)
    financial_proofs = models.FileField(blank=True, null=True)

    # --- EMERGENCY ---
    emergency_contact = models.TextField(blank=True, null=True)

    # --- CONSENT ---
    consent_accurate = models.BooleanField(default=False)
    consent_data = models.BooleanField(default=False)
    consent_send_docs = models.BooleanField(default=False)

    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Visa: {self.full_name}"
