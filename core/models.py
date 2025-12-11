# core/models.py
from decimal import Decimal

from django.db import models
from django.urls import reverse
from django.utils import timezone
from simple_history.models import HistoricalRecords

from .constants import BOOKING_STATUSES  # New
from .constants import LEDGER_ENTRY_TYPES  # New
from .constants import OPERATION_TYPES  # NEW IMPORT
from .constants import PAYMENT_TRANSACTION_TYPES  # New
from .constants import BOOKING_TYPES, PAYMENT_STATUSES, SUPPLIER_PAYMENT_STATUSES


def get_user():
    from django.contrib.auth import get_user_model

    return get_user_model()


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


class EditorSettings(models.Model):
    """Configuration for rich-text editor integrations (e.g. TinyMCE)."""

    name = models.CharField(max_length=50, default="Default")
    tinymce_api_key = models.CharField(
        max_length=255,
        help_text="TinyMCE Cloud API key (from tiny.cloud dashboard).",
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "Editor Settings"
        verbose_name_plural = "Editor Settings"

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
    ref = models.CharField(max_length=30, unique=True, blank=True, db_index=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, db_index=True)
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

    STATUS_CHOICES = [
        ("quote", "📝 Quote / Draft"),
        ("confirmed", "✅ Confirmed"),
        ("cancelled", "🚫 Cancelled"),
    ]
    status = models.CharField(
        "Booking Status",
        max_length=20,
        choices=BOOKING_STATUSES,  # Updated choice list
        default="quote",
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

    supplier_payment_status = models.CharField(
        "Supplier Payment Status",
        max_length=20,
        choices=SUPPLIER_PAYMENT_STATUSES,  # Make sure to import this from constants!
        default="unpaid",
    )

    refund_amount_client = models.DecimalField(
        "Refund TO Client",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Legacy field - use Refunds action instead",
    )
    refund_amount_supplier = models.DecimalField(
        "Refund FROM Supplier",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Legacy field",
    )

    # Flag: Replaces is_supplier_paid
    is_ledger_posted = models.BooleanField(
        default=False, help_text="System Flag: Ledger entries created"
    )

    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="bookings_created",
        verbose_name="Created By",
        help_text="Agent who created this booking (auto-assigned)",
    )
    assigned_to = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings_assigned",
        verbose_name="Assigned To",
        help_text="Agent responsible for handling this booking",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        permissions = [
            ("view_financial_dashboard", "Can view financial dashboard"),
            ("view_all_bookings", "Can view all bookings (not just own)"),
            ("assign_to_others", "Can assign bookings to other agents"),
            ("cancel_any_booking", "Can cancel any booking"),
            ("manage_financials", "Can manage payments, ledger, and expenses"),
        ]

    def save(self, *args, **kwargs):
        # 1. Generate Ref if missing (New Booking)
        if not self.ref:
            today_str = timezone.now().strftime("%Y%m%d")
            prefix_map = {"issue": "BK", "change": "CHG", "refund": "REF"}
            prefix = f"{prefix_map.get(self.operation_type, 'BK')}-{today_str}"

            count = Booking.objects.filter(ref__startswith=prefix).count()
            new_ref = f"{prefix}-{count + 1:03d}"
            while Booking.objects.filter(ref=new_ref).exists():
                count += 1
                new_ref = f"{prefix}-{count + 1:03d}"
            self.ref = new_ref

        # 2. Self-Heal Status (Prevent IntegrityError on old records)
        # This must be OUTSIDE the 'if not self.ref' block to fix existing records too
        if not self.status:
            self.status = "quote"

        super().save(*args, **kwargs)

    @property
    def paid_amount(self):
        # NEW LOGIC: Sum only 'payment' types, subtract 'refund' types
        payments = (
            self.payments.filter(transaction_type="payment").aggregate(
                total=models.Sum("amount")
            )["total"]
            or 0
        )
        refunds = (
            self.payments.filter(transaction_type="refund").aggregate(
                total=models.Sum("amount")
            )["total"]
            or 0
        )
        return payments - refunds

    @property
    def outstanding(self):
        return self.total_amount - self.paid_amount

    def __str__(self):
        return f"{self.ref} ({self.get_booking_type_display()})"


class MyAssignedBooking(Booking):
    """Proxy model for 'My Assigned Bookings' admin view."""

    class Meta:
        proxy = True
        verbose_name = "My Assigned Booking"
        verbose_name_plural = "My Assigned Bookings"


# --- FINANCIAL MODELS ---
class Payment(models.Model):
    PAYMENT_METHODS = [
        ("CASH", "Cash"),
        ("CARD", "Card"),
        ("BANK", "Bank Transfer"),
        ("MOBILE", "Mobile Money"),
        ("CHECK", "Check"),
    ]

    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name="payments",
        null=True,
        blank=True,
    )

    # This allows us to store Refunds in this same table.
    transaction_type = models.CharField(
        max_length=20, choices=PAYMENT_TRANSACTION_TYPES, default="payment"
    )

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default="CASH")
    date = models.DateField()
    reference = models.CharField(max_length=100, blank=True, null=True)

    created_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    def __str__(self):
        direction = "OUT" if self.transaction_type == "refund" else "IN"
        return f"[{direction}] {self.get_method_display()} : {self.amount}"


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

    # --- NEW FIELD: Strict Type ---
    entry_type = models.CharField(
        max_length=30,
        choices=LEDGER_ENTRY_TYPES,
        null=True,
        blank=True,
        help_text="Strict classification for reports",
    )

    debit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    booking = models.ForeignKey(
        Booking, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True)

    is_consolidated = models.BooleanField(
        default=False,
        help_text="True if this entry has been included in a Daily Revenue Closing",
    )

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
    author = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True)

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
        "auth.User",
        blank=True,
        related_name="acknowledged_announcements",
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True)

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
        "Full Name", max_length=200, blank=True, null=True
    )  # Made optional just in case
    passport_number = models.CharField("Passport Number", max_length=50)  # REQUIRED
    photo = models.ImageField(upload_to="visas/photos/")  # REQUIRED

    # --- DETAILS (Relaxed for later entry) ---
    dob = models.DateField("Date of Birth", blank=True, null=True)
    nationality = models.CharField("Nationality", max_length=100, blank=True, null=True)
    passport_issue_date = models.DateField("Issue Date", blank=True, null=True)
    passport_expiry_date = models.DateField("Expiry Date", blank=True, null=True)

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


# In core/models.py, scroll to the bottom (after LedgerEntry)


class BookingLedgerAllocation(models.Model):
    """
    The Safety Bridge: Links a real money move (LedgerEntry)
    to a specific liability (Booking).
    """

    ledger_entry = models.ForeignKey(
        LedgerEntry,
        on_delete=models.CASCADE,
        related_name="allocations",
        help_text="The actual payment record",
    )
    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name="supplier_allocations",
        help_text="The booking debt being paid",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="How much of this payment covers this specific booking",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Auto-update the booking status when an allocation is made
        self.update_booking_status()

    def update_booking_status(self):
        """
        Calculates if the booking is fully paid based on all allocations.
        """
        total_paid = self.booking.supplier_allocations.aggregate(
            total=models.Sum("amount")
        )["total"] or Decimal("0.00")

        if total_paid >= self.booking.supplier_cost:
            self.booking.supplier_payment_status = "paid"
        elif total_paid > 0:
            self.booking.supplier_payment_status = "partial"
        else:
            self.booking.supplier_payment_status = "unpaid"

        self.booking.save(update_fields=["supplier_payment_status"])

    def __str__(self):
        return f"{self.amount} allocated to {self.booking.ref}"


# --- DYNAMIC DOCUMENT GENERATOR MODELS ---


class DocumentTemplate(models.Model):
    PARSER_CHOICES = [
        ("none", "No Parsing (Manual Only)"),
    ]

    name = models.CharField(max_length=100, help_text="e.g., 'Flight Ticket (Amadeus)'")
    slug = models.SlugField(unique=True, help_text="Unique ID, e.g., 'flight_ticket'")

    # Configuration
    parser_type = models.CharField(
        max_length=50, choices=PARSER_CHOICES, default="none"
    )

    # We store the Manual Fields definition as JSON
    # Example: [{"key": "pax_name", "label": "Passenger Name", "type": "text"}]
    manual_fields_config = models.JSONField(
        default=list,
        blank=True,
        help_text="Define the manual inputs needed.",
    )

    # The HTML Template Code (Stored in DB)
    # For simplicity, we store the HTML content directly here so it can be edited in Admin.
    html_content = models.TextField(
        help_text="Paste your HTML template here. Use Django {{ variables }} syntax."
    )

    def __str__(self):
        return self.name


class GeneratedDocument(models.Model):
    template = models.ForeignKey(DocumentTemplate, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    # Data Storage
    raw_text = models.TextField(
        blank=True,
        null=True,
        help_text="The pasted text used for parsing (e.g. GDS/Voucher).",
    )
    manual_data = models.JSONField(default=dict, blank=True)
    parsed_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "\U0001F4C4 Generated Document"

    def __str__(self):
        # Try to find a name, fallback to ID
        name = (
            self.manual_data.get("passenger_name")
            or self.manual_data.get("name")
            or f"Doc #{self.id}"
        )
        return f"{self.template.name} - {name}"

    def get_print_url(self):
        return reverse("print_document", args=[self.id])
