from decimal import Decimal

import pytest

from core.models import Booking, Client, LedgerEntry, Payment


@pytest.mark.django_db
def test_full_payment_flow(admin_client):
    # 1. Setup
    client = Client.objects.create(
        name="Test Client", phone="12345678", passport="A123"
    )

    data = {
        "ref": "TEST-001",
        "client": client.id,
        "booking_type": "ticket",
        "operation_type": "issue",
        "total_amount": "5000.00",
        "supplier_cost": "3000.00",
        "description": "Test Trip",
        "payment_action": "full",
        "transaction_amount": "",
        "transaction_method": "CASH",
        "_save": "Save",
        # --- INLINES ---
        # Visa (Prefix: visa_data)
        "visa_data-TOTAL_FORMS": "0",
        "visa_data-INITIAL_FORMS": "0",
        "visa_data-MIN_NUM_FORMS": "0",
        "visa_data-MAX_NUM_FORMS": "1000",
        # Flight Ticket (Prefix: ticket)
        "ticket-TOTAL_FORMS": "0",
        "ticket-INITIAL_FORMS": "0",
        "ticket-MIN_NUM_FORMS": "0",
        "ticket-MAX_NUM_FORMS": "1000",
        # Payments (Prefix: payments)
        "payments-TOTAL_FORMS": "0",
        "payments-INITIAL_FORMS": "0",
        "payments-MIN_NUM_FORMS": "0",
        "payments-MAX_NUM_FORMS": "1000",
    }

    url = "/admin/core/booking/add/"
    response = admin_client.post(url, data, secure=True)

    # --- SAFE DEBUGGING BLOCK ---
    if response.status_code != 302:
        print(f"\n❌ --- SAVE FAILED (Status {response.status_code}) ---")

        # Safely check for context
        context = getattr(response, "context", None)

        if context:
            if "adminform" in context:
                print(f"Main Form Errors: {context['adminform'].form.errors}")
                print(
                    f"Main Form Non-Field: {context['adminform'].form.non_field_errors()}"
                )

            if "inline_admin_formsets" in context:
                print("\n--- Checking Inlines ---")
                for formset in context["inline_admin_formsets"]:
                    fs = formset.formset
                    if not fs.is_valid():
                        print(f"Inline '{fs.prefix}' Errors: {fs.errors}")
                        print(f"Non-Form Errors: {fs.non_form_errors()}")
                        if not fs.management_form.is_valid():
                            print(
                                f"CRITICAL: Management Form Invalid! {fs.management_form.errors}"
                            )
        else:
            print("⚠️ Context is None! Dumping raw HTML content to find the error:")
            # Print the first 5000 characters of HTML to find the error message
            print(response.content.decode()[:5000])

        pytest.fail("Booking save failed. See debug info above.")

    # 3. Assertions
    booking = Booking.objects.first()

    # If booking wasn't created, fail with a clear message
    if not booking:
        pytest.fail("❌ Booking object was not created in the database.")

    print(f"\n✅ Booking Created: {booking.ref}")
    assert booking.total_amount == Decimal("5000.00")
    assert booking.payment_status == "PAID"

    cash_entry = LedgerEntry.objects.get(account="Assets:CASH")
    assert cash_entry.debit == Decimal("5000.00")
