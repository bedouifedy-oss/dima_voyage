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
    def get_gross_client_cash_in():
        """
        RAW CASH IN: Sum of all money received from clients.
        Source: LedgerEntry (Debit) where type='customer_payment'.
        """
        return FinanceStats._safe_sum(
            LedgerEntry.objects.filter(
                entry_type__in=["customer_payment", "payment", "income"]
            ),
            "debit",
        )

    # --- Helper for Refunds ---
    @staticmethod
    def get_client_refunds():
        """Money returned to clients."""
        return FinanceStats._safe_sum(
            LedgerEntry.objects.filter(entry_type__in=["customer_refund", "refund"]),
            "credit",
        )

    # --- 2. SUPPLIER COSTS (Red Card) ---
    @staticmethod
    def get_net_supplier_cost_paid():
        """
        Net Supplier Cost = (Money Paid Out) - (Money Returned/Credit)
        """
        qs = LedgerEntry.objects.filter(
            entry_type__in=["supplier_payment", "expense", "supplier_cost"]
        )
        debits = FinanceStats._safe_sum(qs, "debit")
        credits = FinanceStats._safe_sum(qs, "credit")
        return debits - credits

    # --- 3. ACCOUNT BALANCE (White Card) ---
    @staticmethod
    def get_net_cash_balance():
        """
        Strict Formula: (Total Revenue Cash) - (Refunds) - (Supplier Costs)
        This ensures it is mathematically identical to the other cards.
        """
        # A. Get the exact number shown in the Green Card
        total_revenue_cash = FinanceStats.get_gross_client_cash_in()

        # B. Get Refunds
        refunds = FinanceStats.get_client_refunds()

        # C. Get the exact number shown in the Red Card
        supplier_costs = FinanceStats.get_net_supplier_cost_paid()

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
