# core/signals.py
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.db import transaction
from django.utils import timezone
from .models import Payment, LedgerEntry, Expense, Booking

# --------------------------------------------------------------------------
# HELPER: Create Ledger Entry
# --------------------------------------------------------------------------
def create_ledger(date, account, debit, credit, booking, user=None):
    LedgerEntry.objects.create(
        date=date,
        account=account,
        debit=debit,
        credit=credit,
        booking=booking,
        created_by=user
    )

# --------------------------------------------------------------------------
# 1. PAYMENT LOGIC
# --------------------------------------------------------------------------
@receiver(post_save, sender=Payment)
def payment_post_save(sender, instance, created, **kwargs):
    """
    1. Records Incoming Payment (+).
    2. Checks 50% Threshold for Supplier Payment (-).
    3. Updates Status (Pending -> Advance -> Confirmed).
    """
    if created:
        with transaction.atomic():
            # A. Record the Payment (Always +)
            # Debit Assets (Cash), Credit Revenue (Client Account)
            create_ledger(instance.date, f"Assets:{instance.get_method_display()}", instance.amount, 0, instance.booking, instance.created_by)
            create_ledger(instance.date, "Revenue:Client Sales", 0, instance.amount, instance.booking, instance.created_by)

            # B. Check Logic on Booking
            if instance.booking:
                booking = instance.booking
                percent = booking.percent_paid
                
                # Update Status Logic
                if booking.status == 'pending':
                    booking.status = 'advance'
                    booking.save(update_fields=['status'])

                # Supplier Payment Rule: If > 50% and NOT yet paid
                if percent >= 50 and not booking.is_supplier_paid:
                    # Trigger Supplier Payment ( - )
                    # Debit Expense (Cost of Sales), Credit Assets (Cash/Bank)
                    create_ledger(instance.date, "Expense:Supplier Cost", booking.supplier_cost, 0, booking, instance.created_by)
                    create_ledger(instance.date, "Assets:Cash", 0, booking.supplier_cost, booking, instance.created_by)
                    
                    booking.is_supplier_paid = True
                    # If fully paid and supplier paid, mark Confirmed
                    if percent >= 100:
                        booking.status = 'confirmed'
                    
                    booking.save(update_fields=['is_supplier_paid', 'status'])
                
                # If hit 100% and supplier already paid previously
                elif percent >= 100 and booking.is_supplier_paid and booking.status != 'confirmed':
                     booking.status = 'confirmed'
                     booking.save(update_fields=['status'])

# --------------------------------------------------------------------------
# 2. BOOKING CHANGE / REFUND LOGIC
# --------------------------------------------------------------------------

# PRE_SAVE: Snapshot old values before database update
@receiver(pre_save, sender=Booking)
def booking_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_instance = Booking.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
            instance._old_supplier_cost = old_instance.supplier_cost
            instance._old_total_amount = old_instance.total_amount
            instance._old_is_supplier_paid = old_instance.is_supplier_paid
        except Booking.DoesNotExist:
            pass

# POST_SAVE: Handle complex Logic (Refund / Change)
@receiver(post_save, sender=Booking)
def booking_post_save(sender, instance, created, **kwargs):
    if created: return # New bookings handled by initial logic/payments

    # Access old values saved in pre_save
    old_status = getattr(instance, '_old_status', None)
    old_supplier_cost = getattr(instance, '_old_supplier_cost', 0)
    old_total_amount = getattr(instance, '_old_total_amount', 0)
    old_supplier_paid = getattr(instance, '_old_is_supplier_paid', False)
    
    today = timezone.now().date()
    user = instance.created_by

    with transaction.atomic():
        
        # --- CASE: REFUND ---
        if instance.status == 'refund' and old_status != 'refund':
            # 1. Reverse Sale (-)
            # Debit Revenue, Credit Cash (Money back to client)
            # We assume we refund what was Paid. 
            paid_sum = instance.paid_amount
            create_ledger(today, "Revenue:Client Sales", paid_sum, 0, instance, user)
            create_ledger(today, "Assets:Cash", 0, paid_sum, instance, user)
            
            # 2. Reverse Supplier Cost (+)
            # If we had paid the supplier, we get it back (or cancel the payable)
            if old_supplier_paid:
                create_ledger(today, "Assets:Cash", old_supplier_cost, 0, instance, user)
                create_ledger(today, "Expense:Supplier Cost", 0, old_supplier_cost, instance, user)
        
        # --- CASE: CHANGE ---
        elif instance.status == 'change' and old_status != 'change':
            # "Change is like a refund and a booking at the same time"
            
            # PART A: REVERSE OLD (The "Refund" part)
            # 1. Reverse Old Supplier Cost (If it was paid)
            if old_supplier_paid:
                 # + for old supplier cost (We get it back/Credit expense)
                 create_ledger(today, "Assets:Cash", old_supplier_cost, 0, instance, user)
                 create_ledger(today, "Expense:Supplier Cost", 0, old_supplier_cost, instance, user)
            
            # 2. Reverse Old Sale Price (The booked amount)
            # Note: Technically we only reverse actual payments in cash basis, 
            # but per your request to "- old sale price", we adjust the Revenue ledger.
            # We will reverse the Revenue equal to what was paid previously or the full amount?
            # Safest is to reverse the Booking Amount relative to Revenue.
            # Implementation: We create a Contra-Revenue entry.
            create_ledger(today, "Revenue:Client Sales", old_total_amount, 0, instance, user)
            create_ledger(today, "Assets:Cash", 0, old_total_amount, instance, user) # Assuming money moves
            
            # PART B: APPLY NEW (The "New Booking" part)
            # 1. Add New Sale Price
            create_ledger(today, "Assets:Cash", instance.total_amount, 0, instance, user)
            create_ledger(today, "Revenue:Client Sales", 0, instance.total_amount, instance, user)
            
            # 2. Add New Supplier Cost (-)
            # We check the 50% rule against the NEW total
            percent = instance.percent_paid
            if percent >= 50:
                 create_ledger(today, "Expense:Supplier Cost", instance.supplier_cost, 0, instance, user)
                 create_ledger(today, "Assets:Cash", 0, instance.supplier_cost, instance, user)
                 # Update flag without triggering save loop
                 Booking.objects.filter(pk=instance.pk).update(is_supplier_paid=True)
            else:
                 # Reset flag if new amount makes it < 50%
                 Booking.objects.filter(pk=instance.pk).update(is_supplier_paid=False)

# --------------------------------------------------------------------------
# 3. EXPENSE LOGIC (Standard)
# --------------------------------------------------------------------------
@receiver(post_save, sender=Expense)
def expense_post_save(sender, instance, created, **kwargs):
    if instance.paid and instance.amount > 0:
        already_posted = LedgerEntry.objects.filter(
            booking=None,
            date=instance.due_date,
            debit=instance.amount,
            account__startswith="Expense:"
        ).exists()

        if not already_posted:
            with transaction.atomic():
                create_ledger(instance.due_date, f"Expense:{instance.name}", instance.amount, 0, None)
                create_ledger(instance.due_date, "Assets:Cash", 0, instance.amount, None)
