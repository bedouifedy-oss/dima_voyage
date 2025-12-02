from django import forms

from .models import Booking, VisaApplication


class BookingAdminForm(forms.ModelForm):
    # --- GHOST FIELDS (Command Center) ---
    PAYMENT_CHOICES = [
        ("none", "⚪ Save Only (No Payment)"),
        ("full", "🟢 Full Payment (Auto-Calc)"),
        ("partial", "🟡 Partial Payment"),
        ("refund", "🔴 Refund (Correction)"),
    ]

    payment_action = forms.ChoiceField(
        choices=PAYMENT_CHOICES,
        required=False,
        initial="none",
        widget=forms.RadioSelect(attrs={"class": "payment-action-buttons"}),
        label="💳 Payment Action",
    )

    transaction_amount = forms.DecimalField(
        required=False,
        decimal_places=2,
        max_digits=10,
        min_value=0,
        widget=forms.NumberInput(attrs={"placeholder": "Enter Amount"}),
        label="Amount",
        help_text="Required if choosing Partial or Refund.",
    )

    transaction_method = forms.ChoiceField(
        choices=[("CASH", "Cash"), ("BANK", "Bank Transfer"), ("CHECK", "Check")],
        required=False,
        initial="CASH",
        label="Method",
    )

    class Meta:
        model = Booking
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()

        # --- 1. CRITICAL SECURITY: CLIENT LOCKING ---
        # Ensure that if this is a sub-transaction (Refund/Change),
        # it belongs to the same client as the parent booking.
        parent_booking = cleaned_data.get("parent_booking")
        client = cleaned_data.get("client")
        operation_type = cleaned_data.get("operation_type")

        if parent_booking and operation_type in ["change", "refund"]:
            if client != parent_booking.client:
                # This error blocks the save if the agent tries to mix clients
                self.add_error(
                    "client",
                    f"⛔ SECURITY ERROR: You cannot link this transaction to Parent Booking '{parent_booking.ref}' "
                    f"because it belongs to {parent_booking.client.name}, but you selected {client.name}.",
                )

        # --- 2. Prevent Self-Referencing ---
        if (
            self.instance.pk
            and parent_booking
            and parent_booking.pk == self.instance.pk
        ):
            self.add_error(
                "parent_booking", "⛔ Logic Error: A booking cannot be its own parent."
            )

        # --- 3. Payment Logic Validation ---
        action = cleaned_data.get("payment_action")
        amount = cleaned_data.get("transaction_amount")

        if action in ["partial", "refund"] and not amount:
            self.add_error(
                "transaction_amount",
                "⚠️ Missing Data: You selected a Payment Action but did not enter an Amount.",
            )

        return cleaned_data


# (Keep your VisaForm as is)
class VisaForm(forms.ModelForm):
    class Meta:
        model = VisaApplication
        exclude = ["booking", "submitted_at"]
        widgets = {
            "dob": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "passport_issue_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "passport_expiry_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "departure_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "return_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "address": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "previous_visa_details": forms.Textarea(
                attrs={"rows": 2, "class": "form-control"}
            ),
            "itinerary": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "emergency_contact": forms.Textarea(
                attrs={"rows": 2, "class": "form-control"}
            ),
            "guarantor_details": forms.Textarea(
                attrs={"rows": 2, "class": "form-control"}
            ),
            "accommodation_type": forms.Select(attrs={"class": "form-select"}),
            "payer": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            if not isinstance(
                self.fields[field].widget,
                (forms.CheckboxInput, forms.RadioSelect, forms.FileInput),
            ):
                existing = self.fields[field].widget.attrs.get("class", "")
                self.fields[field].widget.attrs["class"] = existing + " form-control"
