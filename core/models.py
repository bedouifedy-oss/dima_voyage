# core/models.py
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
    
    def __str__(self):
        return self.name

class Supplier(models.Model):
    name = models.CharField(max_length=200)
    contact = models.CharField(max_length=200, blank=True, null=True)
    
    def __str__(self):
        return self.name

class Booking(models.Model):
    BOOKING_TYPES = [
        ('outgoing_hotel','Outgoing Hotel'),
        ('local_hotel','Local Hotel'),
        ('omra','Omra'),
        ('trip','Trip'),
        # Visa / Services Sub-types
        ('visa_app','Visa / Services - Application'),
        ('visa_dummy','Visa / Services - Dummy Booking'),
    ]
    
    STATUS_CHOICES = [
        ('pending','Pending'),       # Initial state
        ('advance','Advance'),       # Partial payment received
        ('confirmed','Confirmed'),   # Payment received AND Supplier Paid
        ('change','Change'),         # Modification (Refund + New Booking logic)
        ('refund','Refund'),         # Full cancellation
        ('completed','Completed')    # Done
    ]
    
    # UPDATED: Added blank=True so the admin form does not require it (auto-generated)
    ref = models.CharField(max_length=30, unique=True, blank=True)
    
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    booking_type = models.CharField(max_length=40, choices=BOOKING_TYPES)
    description = models.TextField(blank=True)
    
    # Financials
    total_amount = models.DecimalField(max_digits=12, decimal_places=2) # Sale Price
    supplier_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00')) # Cost
    
    # Internal Flags
    is_supplier_paid = models.BooleanField(default=False, help_text="System flag: True if supplier cost has been deducted from ledger")

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='booked_by')
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # --- 🤖 NEW: AUTO-GENERATION LOGIC ---
    def save(self, *args, **kwargs):
        if not self.ref: # Only generate if REF is empty
            today_str = timezone.now().strftime('%Y%m%d') # e.g., "20251129"
            prefix = f"BK-{today_str}"
            
            # Count existing bookings for today to determine the next number
            count = Booking.objects.filter(ref__startswith=prefix).count()
            
            # Create new ID (e.g., BK-20251129-001)
            new_ref = f"{prefix}-{count + 1:03d}"
            
            # Safety loop: If ID exists (rare), increment until unique
            while Booking.objects.filter(ref=new_ref).exists():
                count += 1
                new_ref = f"{prefix}-{count + 1:03d}"
            
            self.ref = new_ref
            
        super().save(*args, **kwargs)
    # -------------------------------------

    @property
    def paid_amount(self):
        return self.payments.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

    @property
    def outstanding(self):
        return self.total_amount - self.paid_amount
    
    @property
    def percent_paid(self):
        if self.total_amount == 0: return 0
        return (self.paid_amount / self.total_amount) * 100
    
    def __str__(self):
        return f"{self.ref} ({self.client.name})"

class Payment(models.Model):
    PAYMENT_METHODS = [
        ('cash','Cash'),
        ('card','Card'),
        ('bank','Bank Transfer'),
        ('mobile','Mobile Money')
    ]
    
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='payments', null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    date = models.DateField()
    reference = models.CharField(max_length=100, blank=True, null=True) 
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Payment of {self.amount} for {self.booking.ref if self.booking else 'N/A'}"

class Expense(models.Model):
    name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField()
    paid = models.BooleanField(default=False)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True)
    recurrence = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return self.name

class LedgerEntry(models.Model):
    date = models.DateField()
    account = models.CharField(max_length=100) 
    debit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    booking = models.ForeignKey(Booking, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    def __str__(self):
        return f"{self.date} - {self.account}: Dr={self.debit}, Cr={self.credit}"
