# core/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import Payment, LedgerEntry, Expense, Booking

def create_ledger(date, account, debit, credit, booking, user=None):
    LedgerEntry.objects.create(date=date, account=account, debit=debit, credit=credit, booking=booking, created_by=user)

@receiver(post_save, sender=Payment)
def payment_post_save(sender, instance, created, **kwargs):
    """
    Tracks CASH movement.
    """
    if created and instance.booking:
        with transaction.atomic():
            b = instance.booking
            
            # 1. If this is a REFUND Payment (We are PAYING the client)
            if b.operation_type == 'refund':
                # Credit Assets (Cash Out), Debit Revenue (Revenue Reduction)
                create_ledger(instance.date, "Revenue:Refunds", instance.amount, 0, b, instance.created_by)
                create_ledger(instance.date, "Assets:Cash", 0, instance.amount, b, instance.created_by)
                b.payment_status = 'refunded'
                b.save(update_fields=['payment_status'])
                
            # 2. Normal Payment (Client PAYS us)
            else:
                create_ledger(instance.date, f"Assets:{instance.get_method_display()}", instance.amount, 0, b, instance.created_by)
                create_ledger(instance.date, "Revenue:Sales", 0, instance.amount, b, instance.created_by)
                
                # Check if fully paid
                if b.outstanding <= 0:
                    b.payment_status = 'paid'
                else:
                    b.payment_status = 'advance'
                b.save(update_fields=['payment_status'])

@receiver(post_save, sender=Booking)
def booking_post_save(sender, instance, created, **kwargs):
    """
    Tracks SUPPLIER Liabilities (Accrual Basis).
    """
    if instance.is_ledger_posted:
        return # Prevent duplicate postings

    # Only post to ledger if the deal is firm (Advance paid or Fully paid)
    # OR if it's a Refund operation
    valid_statuses = ['advance', 'paid', 'refunded', 'confirmed']
    
    if instance.payment_status in valid_statuses or instance.operation_type == 'refund':
        with transaction.atomic():
            today = instance.created_at.date()
            user = instance.created_by

            # LOGIC: ISSUE (New Sale) or CHANGE (Modification)
            if instance.operation_type in ['issue', 'change']:
                # If we have a supplier cost, we owe them money
                if instance.supplier_cost > 0:
                    # Debit Expense (Cost), Credit Liability (Accounts Payable)
                    create_ledger(today, "Expense:Supplier Cost", instance.supplier_cost, 0, instance, user)
                    create_ledger(today, "Liabilities:Supplier Payable", 0, instance.supplier_cost, instance, user)
                    
                    Booking.objects.filter(pk=instance.pk).update(is_ledger_posted=True)

            # LOGIC: REFUND (Reversal)
            elif instance.operation_type == 'refund':
                # If Supplier refunds us
                if instance.refund_amount_supplier > 0:
                    # Debit Liability (We don't owe them anymore), Credit Expense (Cost Reversal)
                    create_ledger(today, "Liabilities:Supplier Payable", instance.refund_amount_supplier, 0, instance, user)
                    create_ledger(today, "Expense:Supplier Cost", 0, instance.refund_amount_supplier, instance, user)
                    
                    Booking.objects.filter(pk=instance.pk).update(is_ledger_posted=True)
