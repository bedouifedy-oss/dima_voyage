import pytest
from core.models import Booking, Payment, Client, LedgerEntry
from decimal import Decimal

@pytest.mark.django_db
def test_full_payment_flow(admin_client):
    # 1. Setup
    client = Client.objects.create(name="Test Client", phone="12345678", passport="A123")

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
    response = admin_client.post(url, data)

    # --- VERBOSE DEBUGGING ---
    if response.status_code != 302:
        print("\n❌ --- SAVE FAILED (200 OK) ---")
        
        if 'adminform' in response.context:
            print(f"Main Form Valid? {response.context['adminform'].form.is_valid()}")
            print(f"Main Form Errors: {response.context['adminform'].form.errors}")
            print(f"Main Form Non-Field Errors: {response.context['adminform'].form.non_field_errors()}")

        if 'inline_admin_formsets' in response.context:
            print("\n--- Checking Inlines ---")
            for formset in response.context['inline_admin_formsets']:
                fs = formset.formset
                prefix = fs.prefix
                print(f"Inline '{prefix}': Valid? {fs.is_valid()}")
                if not fs.is_valid():
                    print(f"   Errors: {fs.errors}")
                    print(f"   Non-Form Errors: {fs.non_form_errors()}")
                    # Check if Management Form is valid
                    if not fs.management_form.is_valid():
                        print(f"   CRITICAL: Management Form Invalid!")
                        print(f"   {fs.management_form.errors}")

        pytest.fail("Booking save failed. Check the Verbose Output above.")

    # 3. Assertions
    # We grab the FIRST booking created to verify it saved correctly
    booking = Booking.objects.first()
    
    print(f"\n✅ Booking Created: {booking.ref}")
    assert booking.total_amount == Decimal("5000.00")
    assert booking.payment_status == "PAID"
    
    cash_entry = LedgerEntry.objects.get(account="Assets:CASH")
    assert cash_entry.debit == Decimal("5000.00")
