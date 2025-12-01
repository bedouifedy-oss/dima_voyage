# core/forms.py
from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from .models import Booking, VisaApplication

class BookingAdminForm(forms.ModelForm):
    """
    Combined Form:
    1. Enforces Customer Locking (Safety).
    2. Provides "Command Center" for Payments (Efficiency).
    """
    
    # --- COMMAND CENTER: GHOST FIELDS ---
    # These fields do not exist in the Booking model. 
    # They are used to trigger actions in admin.py.

    PAYMENT_CHOICES = [
        ('none', '⚪ Save Only (No Payment)'),
        ('full', '🟢 Full Payment (Auto-Calc)'),
        ('partial', '🟡 Partial Payment'),
        ('refund', '🔴 Refund (Correction)'),
    ]

    payment_action = forms.ChoiceField(
        choices=PAYMENT_CHOICES,
        required=False,
        initial='none',
        widget=forms.RadioSelect(attrs={'class': 'payment-action-buttons'}),
        label="💳 Payment Action"
    )

    transaction_amount = forms.DecimalField(
        required=False,
        decimal_places=2,
        max_digits=10,
        min_value=0,
        widget=forms.NumberInput(attrs={'placeholder': 'Enter Amount (if partial)'}),
        label="Amount",
        help_text="Required if choosing Partial or Refund."
    )

    transaction_method = forms.ChoiceField(
        choices=[('CASH', 'Cash'), ('BANK', 'Bank Transfer'), ('CHECK', 'Check')],
        required=False,
        initial='CASH',
        label="Method"
    )

    class Meta:
        model = Booking
        fields = '__all__'
    
    def clean(self):
        cleaned_data = super().clean()
        
        # --- PART 1: YOUR EXISTING SAFETY LOGIC ---
        parent_booking = cleaned_data.get("parent_booking")
        client = cleaned_data.get("client")
        operation_type = cleaned_data.get("operation_type")
        
        # Check 1: Client Locking
        if parent_booking and operation_type in ['change', 'refund']:
            if client != parent_booking.client:
                self.add_error('client', 
                               f"⛔ Customer Mismatch! You cannot link this to Parent Booking '{parent_booking.ref}' "
                               f"because it belongs to {parent_booking.client.name}, not {client.name}.")
        
        # Check 2: Self-Referencing
        if parent_booking and self.instance.pk and parent_booking.pk == self.instance.pk:
            self.add_error('parent_booking', "⛔ A booking cannot be its own parent.")

        # --- PART 2: NEW PAYMENT LOGIC ---
        action = cleaned_data.get('payment_action')
        amount = cleaned_data.get('transaction_amount')

        if action in ['partial', 'refund'] and not amount:
            self.add_error('transaction_amount', "⚠️ You selected a Payment Action but did not enter an Amount.")

        return cleaned_data


class VisaForm(forms.ModelForm):
    """
    Form for the public client-facing Visa application (RTL/LTR support).
    (Kept exactly as you provided)
    """
    class Meta:
        model = VisaApplication
        exclude = ['booking', 'submitted_at']
        widgets = {
            'dob': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'passport_issue_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'passport_expiry_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'departure_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'return_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            
            'address': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'previous_visa_details': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'itinerary': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'emergency_contact': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'guarantor_details': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            
            'accommodation_type': forms.Select(attrs={'class': 'form-select'}),
            'payer': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            if not isinstance(self.fields[field].widget, (forms.CheckboxInput, forms.RadioSelect, forms.FileInput)):
                existing = self.fields[field].widget.attrs.get('class', '')
                self.fields[field].widget.attrs['class'] = existing + ' form-control'
