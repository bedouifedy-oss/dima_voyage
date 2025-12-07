# core/signals.py

from django.db import transaction
from django.db.models import Sum
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Booking, Expense, LedgerEntry, Payment


# --- 1. HELPER: STATUS CALCULATOR ---
def recalculate_booking_status(booking):
    """
    Derived logic to determine status based on payments vs total.
    """
    # 1. Sum up valid payments (exclude voided/legacy if necessary)
    payments = (
        booking.payments.filter(transaction_type="payment").aggregate(
            total=Sum("amount")
        )["total"]
        or 0
    )
    refunds = (
        booking.payments.filter(transaction_type="refund").aggregate(
            total=Sum("amount")
        )["total"]
        or 0
    )

    net_paid = payments - refunds
    total_due = booking.total_amount

    # 2. Determine Status
    new_payment_status = "pending"

    if net_paid >= total_due and total_due > 0:
        new_payment_status = "paid"
    elif net_paid > 0:
        new_payment_status = "advance"  # Partial
    elif net_paid < 0:
        # Rare case: We refunded more than they paid?
        new_payment_status = "refunded"

    # 3. Save only if changed to prevent recursion loops
    if booking.payment_status != new_payment_status:
        booking.payment_status = new_payment_status
        # Use update_fields to avoid triggering the save signal recursively for other fields
        booking.save(update_fields=["payment_status"])


# --- 2. PAYMENT SIGNALS ---


@receiver(post_save, sender=Payment)
def payment_post_save(sender, instance, created, **kwargs):
    """
    1. Update Booking Status.
    2. Create Ledger Entry (only on creation).
    """
    booking = instance.booking
    if not booking:
        return

    # A. Update Status
    recalculate_booking_status(booking)

    # B. Ledger Entry (Only for new records)
    if created:
        if instance.transaction_type == "payment":
            # INCOMING MONEY
            LedgerEntry.objects.create(
                date=instance.date,
                account=f"Cash ({instance.get_method_display()})",
                entry_type="customer_payment",
                debit=instance.amount,  # Cash increases (Debit)
                credit=0,
                booking=booking,
                created_by=instance.created_by,
            )
            # Corresponding Credit to AR is usually implicit in single-entry views,
            # or we can add a second line if you want double-entry strictness later.

        elif instance.transaction_type == "refund":
            # OUTGOING MONEY
            LedgerEntry.objects.create(
                date=instance.date,
                account="Refunds & Returns",
                entry_type="customer_refund",
                debit=0,
                credit=instance.amount,  # Cash decreases (Credit)
                booking=booking,
                created_by=instance.created_by,
            )


# --- 3. BOOKING SIGNALS ---


@receiver(post_save, sender=Booking)
def booking_post_save(sender, instance, created, **kwargs):
    """
    1. If Confirmed & Not Posted -> Post Revenue to Ledger.
    2. If Total Amount changes -> Recalculate Payment Status.
    """

    # A. Revenue Recognition (Drafts are ignored)
    if instance.status == "confirmed" and not instance.is_ledger_posted:
        if instance.total_amount > 0:
            LedgerEntry.objects.create(
                date=instance.created_at.date(),
                account=f"Revenue - {instance.get_booking_type_display()}",
                entry_type="sale_revenue",
                debit=0,
                credit=instance.total_amount,  # Revenue increases (Credit)
                booking=instance,
                created_by=instance.created_by,
            )
            # Mark as posted so we don't duplicate it
            instance.is_ledger_posted = True
            instance.save(update_fields=["is_ledger_posted"])

    # B. Recalculate Status (in case Price changed manually)
    # We wrap in a transaction to ensure data integrity
    transaction.on_commit(lambda: recalculate_booking_status(instance))


# --- EXPENSE SIGNALS (New) ---


@receiver(post_save, sender=Expense)
def expense_post_save(sender, instance, created, **kwargs):
    """
    Automatically records a Ledger Entry when an Expense is marked as 'Paid'
    (either on creation or update).
    """
    if instance.paid:
        # Define a unique identifier for this expense payment
        # We use the ID to check if we already paid it, preventing duplicates.
        ledger_account_name = f"Expense: {instance.name} (#{instance.id})"

        # Check if this specific expense was already recorded in the Ledger
        already_posted = LedgerEntry.objects.filter(
            account=ledger_account_name, entry_type="expense"
        ).exists()

        if not already_posted:
            # Create the Ledger Entry
            LedgerEntry.objects.create(
                date=instance.due_date or timezone.now(),
                account=ledger_account_name,
                entry_type="expense",  # This ensures it counts as Supplier Cost
                debit=instance.amount,
                credit=0,
                # Note: Signals don't have access to 'request.user', so we leave it None
                # or you could try fetching it if you use a middleware, but None is safe.
                created_by=None,
            )
