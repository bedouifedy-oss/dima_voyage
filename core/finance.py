# core/finance.py
from decimal import Decimal

from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce

from .models import Booking, Expense, LedgerEntry


class FinanceStats:
    @staticmethod
    def _safe_sum(queryset, field_name):
        """Helper to safely sum decimals."""
        return queryset.aggregate(
            total=Coalesce(
                Sum(field_name), Value(Decimal("0.00")), output_field=DecimalField()
            )
        )["total"]

    # --- 1. TOTAL REVENUE (Green Card) ---
    @staticmethod
    def get_gross_client_cash_in(start_date=None, end_date=None):
        """
        RAW CASH IN: Sum of all money received from clients.
        Source: LedgerEntry (Debit) where type='customer_payment'.
        """
        qs = LedgerEntry.objects.filter(
            entry_type__in=["customer_payment", "payment", "income"]
        )

        # Apply Date Filter if provided
        if start_date and end_date:
            qs = qs.filter(date__range=[start_date, end_date])

        return FinanceStats._safe_sum(qs, "debit")

    # --- Helper for Refunds ---
    @staticmethod
    def get_client_refunds(start_date=None, end_date=None):
        """Money returned to clients."""
        qs = LedgerEntry.objects.filter(entry_type__in=["customer_refund", "refund"])

        if start_date and end_date:
            qs = qs.filter(date__range=[start_date, end_date])

        return FinanceStats._safe_sum(qs, "credit")

    # --- 2. SUPPLIER COSTS (Red Card) ---
    @staticmethod
    def get_net_supplier_cost_paid(start_date=None, end_date=None):
        """
        Net Supplier Cost = (Money Paid Out) - (Money Returned/Credit)
        """
        qs = LedgerEntry.objects.filter(
            entry_type__in=["supplier_payment", "expense", "supplier_cost"]
        )

        if start_date and end_date:
            qs = qs.filter(date__range=[start_date, end_date])

        total_debits = FinanceStats._safe_sum(qs, "debit")
        total_credits = FinanceStats._safe_sum(qs, "credit")
        return total_debits - total_credits

    # --- 3. ACCOUNT BALANCE (White Card) ---
    @staticmethod
    def get_net_cash_balance(start_date=None, end_date=None):
        """
        Strict Formula: (Total Revenue Cash) - (Refunds) - (Supplier Costs)
        This ensures it is mathematically identical to the other cards.
        """
        # A. Get the exact number shown in the Green Card
        total_revenue_cash = FinanceStats.get_gross_client_cash_in(start_date, end_date)

        # B. Get Refunds
        refunds = FinanceStats.get_client_refunds(start_date, end_date)

        # C. Get the exact number shown in the Red Card
        supplier_costs = FinanceStats.get_net_supplier_cost_paid(start_date, end_date)

        # Calculation
        return total_revenue_cash - refunds - supplier_costs

    # --- 4. UNPAID LIABILITIES (Yellow Card) ---
    @staticmethod
    def get_unpaid_liabilities():
        """Unpaid Bookings + Unpaid Expenses"""
        booking_debt = Decimal("0.00")
        for booking in Booking.objects.exclude(supplier_payment_status="paid"):
            paid_so_far = FinanceStats._safe_sum(
                booking.supplier_allocations.all(), "amount"
            )
            remainder = booking.supplier_cost - paid_so_far
            if remainder > 0:
                booking_debt += remainder

        expense_debt = FinanceStats._safe_sum(
            Expense.objects.filter(paid=False), "amount"
        )
        return booking_debt + expense_debt

    # --- EXTRA: Invoiced Revenue (For Profit Reports) ---
    @staticmethod
    def get_total_revenue_invoiced():
        return FinanceStats._safe_sum(
            LedgerEntry.objects.filter(entry_type="sale_revenue"), "credit"
        )
