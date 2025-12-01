# core/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import Payment, LedgerEntry, Expense, Booking, User
from decimal import Decimal

# Helper function for creating immutable Ledger Entries
def create_ledger(date, account, debit, credit, booking, user=None):
    LedgerEntry.objects.create(
        date=date, 
        account=account, 
        debit=debit, 
        credit=credit, 
        booking=booking, 
        created_by=user
    )

@receiver(post_save, sender=Payment)
def payment_post_save(sender, instance, created, **kwargs):
    """
    TRACKS CASH MOVEMENT (Assets/Liabilities).
    This function drives the Payment Status (Pending -> Advance -> Paid/Refunded).
    """
    if created and instance.booking:
        with transaction.atomic():
            b = instance.booking
            amount = instance.amount
            
            # --- 1. REFUND PAYMENT (Money Out) ---
            if b.operation_type == 'refund':
                # Debit Revenue:Refunds (Reduces Sale) | Credit Assets:Cash (Cash Out to Client)
                create_ledger(instance.date, "Revenue:Refunds", amount, 0, b, instance.created_by)
                create_ledger(instance.date, f"Assets:{instance.get_method_display()}", 0, amount, b, instance.created_by)
                
                # Set refund status
                b.payment_status = 'refunded'
                b.save(update_fields=['payment_status'])
                
            # --- 2. STANDARD PAYMENT (Money In) ---
            else:
                # Debit Assets:Cash (Cash In) | Credit Revenue:Sales (Increase Sales)
                create_ledger(instance.date, f"Assets:{instance.get_method_display()}", amount, 0, b, instance.created_by)
                create_ledger(instance.date, "Revenue:Sales", 0, amount, b, instance.created_by)
                
                # Update Booking Status based on outstanding balance
                if b.outstanding <= Decimal('0.00'):
                    b.payment_status = 'paid'
                else:
                    b.payment_status = 'advance'
                b.save(update_fields=['payment_status'])

@receiver(post_save, sender=Booking)
def booking_post_save(sender, instance, created, **kwargs):
    """
    TRACKS SUPPLIER LIABILITIES (Accrual/Cost Booking).
    This function handles the Cost of Goods Sold (COGS) entry.
    """
    # Use the new flag to prevent logic from running more than once per transaction
    if instance.is_ledger_posted:
        return 

    # We only book cost once the transaction is officially created (after initial save)
    # The check for status here is simplified to just check the operation type
    if instance.pk: # Ensure it's not a temporary instance
        with transaction.atomic():
            today = instance.created_at.date()
            user = instance.created_by

            # --- LOGIC: ISSUE or CHANGE (We owe supplier money) ---
            if instance.operation_type in ['issue', 'change']:
                if instance.supplier_cost > Decimal('0.00'):
                    # Debit Expense (Cost) | Credit Liability (Accounts Payable)
                    create_ledger(today, "Expense:Supplier Cost", instance.supplier_cost, 0, instance, user)
                    create_ledger(today, "Liabilities:Supplier Payable", 0, instance.supplier_cost, instance, user)
                    
                    # Mark as processed
                    Booking.objects.filter(pk=instance.pk).update(is_ledger_posted=True)

            # --- LOGIC: REFUND (Supplier refunds us money) ---
            elif instance.operation_type == 'refund':
                if instance.refund_amount_supplier > Decimal('0.00'):
                    # Debit Liability (Reduced debt) | Credit Expense (Cost Reversal)
                    create_ledger(today, "Liabilities:Supplier Payable", instance.refund_amount_supplier, 0, instance, user)
                    create_ledger(today, "Expense:Supplier Cost", 0, instance.refund_amount_supplier, instance, user)
                    
                    Booking.objects.filter(pk=instance.pk).update(is_ledger_posted=True)
