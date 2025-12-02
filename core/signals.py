# core/signals.py
from decimal import Decimal

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Booking, LedgerEntry, Payment


# Helper to track previous state
@receiver(pre_save, sender=Booking)
def cache_previous_financials(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_instance = Booking.objects.get(pk=instance.pk)
            instance._old_total_amount = old_instance.total_amount
            instance._old_supplier_cost = old_instance.supplier_cost
        except Booking.DoesNotExist:
            pass


@receiver(post_save, sender=Booking)
def update_ledger_on_booking(sender, instance, created, **kwargs):
    """
    ACCRUAL BASIS: Record Revenue/Expense.
    Handles DELTA logic (Changes) to prevent double-counting.
    """
    with transaction.atomic():
        # Get old values (default to 0 if new)
        old_total = getattr(instance, "_old_total_amount", Decimal("0.00"))
        old_cost = getattr(instance, "_old_supplier_cost", Decimal("0.00"))

        # --- 1. REVENUE (Sales) ---
        revenue_diff = instance.total_amount - old_total

        if revenue_diff != 0:
            is_increase = revenue_diff > 0
            abs_diff = abs(revenue_diff)

            LedgerEntry.objects.create(
                booking=instance,
                account="Revenue:Sales",
                date=instance.created_at,
                # description=... (REMOVED: Field does not exist in DB)
                debit=0 if is_increase else abs_diff,
                credit=abs_diff if is_increase else 0,
                created_by=instance.created_by,
            )

        # --- 2. EXPENSE (Supplier Cost) ---
        cost_diff = instance.supplier_cost - old_cost

        if cost_diff != 0:
            is_increase = cost_diff > 0
            abs_diff = abs(cost_diff)

            # A. Expense Side
            LedgerEntry.objects.create(
                booking=instance,
                account="Expense:Supplier Cost",
                date=instance.created_at,
                # description=... (REMOVED)
                debit=abs_diff if is_increase else 0,
                credit=0 if is_increase else abs_diff,
                created_by=instance.created_by,
            )

            # B. Liability Side
            LedgerEntry.objects.create(
                booking=instance,
                account="Liabilities:Supplier Payable",
                date=instance.created_at,
                # description=... (REMOVED)
                debit=0 if is_increase else abs_diff,
                credit=abs_diff if is_increase else 0,
                created_by=instance.created_by,
            )


@receiver(post_save, sender=Payment)
def update_ledger_on_payment(sender, instance, created, **kwargs):
    """
    CASH BASIS: Money moving hands.
    """
    if not created:
        return

    with transaction.atomic():
        # ledger_ref = ... (REMOVED: Field does not exist in DB)

        cash_account = "Assets:CASH"
        if instance.method == "BANK":
            cash_account = "Assets:Bank"
        elif instance.method == "CHECK":
            cash_account = "Assets:Check"

        LedgerEntry.objects.create(
            # reference=... (REMOVED)
            booking=instance.booking,
            date=instance.date,
            # description=... (REMOVED)
            account=cash_account,
            debit=instance.amount,
            credit=0,
            created_by=instance.created_by,
        )

        # Update Status
        booking = instance.booking
        total_paid = sum(p.amount for p in booking.payments.all())

        new_status = booking.payment_status
        if total_paid >= booking.total_amount:
            new_status = "PAID"
        elif total_paid > 0:
            new_status = "PARTIAL"
        else:
            new_status = "PENDING"

        if booking.payment_status != new_status:
            booking.payment_status = new_status
            booking.save(update_fields=["payment_status"])
