# core/forms.py
from django import forms
from .models import Booking, VisaApplication


# --- 1. The "Picker" Form (For Admin Configuration) ---
class VisaFieldConfigurationForm(forms.Form):
    # Get all fields from the model dynamically
    _choices = [
        (f.name, f.verbose_name or f.name) 
        for f in VisaApplication._meta.get_fields() 
        if f.name not in ['id', 'booking', 'submitted_at', 'photo', 'passport_number'] 
        # We exclude photo/passport because they are always mandatory
    ]
    
    selected_fields = forms.MultipleChoiceField(
        choices=_choices,
        widget=forms.CheckboxSelectMultiple,
        label="Select Additional Fields",
        required=False
    )

# --- 2. The Booking Admin Form (Command Center) ---
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
        parent_booking = cleaned_data.get("parent_booking")
        client = cleaned_data.get("client")
        operation_type = cleaned_data.get("operation_type")

        if parent_booking and operation_type in ["change", "refund"]:
            if client != parent_booking.client:
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

# --- 3. The Public Visa Form (Now Dynamic) ---

VISA_LABELS = {
    'full_name': {'tn': 'الاسم الكامل', 'fr': 'Nom complet'},
    'dob': {'tn': 'تاريخ الولادة', 'fr': 'Date de naissance'},
    'nationality': {'tn': 'الجنسية', 'fr': 'Nationalité'},
    'passport_number': {'tn': 'رقم الباسبور', 'fr': 'Numéro de passeport'},
    'passport_issue_date': {'tn': 'تاريخ إصدار الباسبور', 'fr': 'Date de délivrance'},
    'passport_expiry_date': {'tn': 'تاريخ انتهاء الباسبور', 'fr': 'Date d\'expiration'},
    'photo': {'tn': 'تصويرة الباسبور', 'fr': 'Photo du passeport'},
    
    'phone': {'tn': 'رقم التليفون', 'fr': 'Téléphone'},
    'email': {'tn': 'الإيميل', 'fr': 'Email'},
    'address': {'tn': 'العنوان', 'fr': 'Adresse'},
    
    'travel_reason': {'tn': 'سبب السفر', 'fr': 'Motif du voyage'},
    'departure_date': {'tn': 'تاريخ الذهاب', 'fr': 'Date de départ'},
    'return_date': {'tn': 'تاريخ المروح', 'fr': 'Date de retour'},
    'itinerary': {'tn': 'برنامج الرحلة', 'fr': 'Itinéraire'},

    # --- PREVIOUSLY MISSING FIELDS (Added Now) ---
    'previous_visa_details': {'tn': 'تفاصيل التأشيرات السابقة', 'fr': 'Détails des visas précédents'},
    'has_previous_visa': {'tn': 'عندك فيزا سابقة؟', 'fr': 'Avez-vous un visa précédent ?'},
    'ticket_departure': {'tn': 'تذكرة الذهاب', 'fr': 'Billet de départ'},
    'ticket_return': {'tn': 'تذكرة العودة', 'fr': 'Billet de retour'},
    'travel_insurance': {'tn': 'تأمين السفر', 'fr': 'Assurance voyage'},
    
    'accommodation_type': {'tn': 'نوع السكن', 'fr': 'Type d\'hébergement'},
    'host_name': {'tn': 'اسم المستضيف', 'fr': 'Nom de l\'hôte'},
    'host_address': {'tn': 'عنوان المستضيف', 'fr': 'Adresse de l\'hôte'},
    'host_phone': {'tn': 'تليفون المستضيف', 'fr': 'Téléphone de l\'hôte'},
    'host_email': {'tn': 'إيميل المستضيف', 'fr': 'Email de l\'hôte'},
    'host_relationship': {'tn': 'صلة القرابة', 'fr': 'Relation avec l\'hôte'},
    
    'hotel_name': {'tn': 'اسم الوتيل', 'fr': 'Nom de l\'hôtel'},
    'hotel_address': {'tn': 'عنوان الوتيل', 'fr': 'Adresse de l\'hôtel'},
    'hotel_reservation': {'tn': 'حجز الوتيل', 'fr': 'Réservation d\'hôtel'},
    
    'payer': {'tn': 'شكون باش يخلص؟', 'fr': 'Qui finance le voyage ?'},
    'financial_proofs': {'tn': 'إثباتات مالية', 'fr': 'Preuves financières'},
    'guarantor_details': {'tn': 'معلومات الضامن', 'fr': 'Détails du garant'},
    
    'emergency_contact': {'tn': 'شكون نكلمو في حالة طوارئ', 'fr': 'Contact d\'urgence'},
    
    # Consents
    'consent_accurate': {'tn': 'أصرح أن المعلومات صحيحة', 'fr': 'Je déclare que ces informations sont exactes'},
    'consent_data': {'tn': 'أوافق على معالجة بياناتي', 'fr': 'J\'accepte le traitement de mes données'},
}

class VisaForm(forms.ModelForm):
    class Meta:
        model = VisaApplication
        fields = '__all__'
        exclude = ["booking", "submitted_at"]
        
        # Keep your existing widget definitions for styling
        widgets = {
            "dob": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "passport_issue_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "passport_expiry_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "departure_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "return_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "address": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "previous_visa_details": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "itinerary": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "emergency_contact": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "guarantor_details": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "accommodation_type": forms.Select(attrs={"class": "form-select"}),
            "payer": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        # Capture the 'visible_fields' argument
        visible_fields = kwargs.pop('visible_fields', None)
        # Capture the 'lang' argument (Default to Tunisian)
        lang = kwargs.pop('lang', 'tn')  
        
        super().__init__(*args, **kwargs)
        
        # 1. Handle Dynamic Field Visibility
        mandatory = ['passport_number', 'photo']
        
        if visible_fields:
            # Combine mandatory + selected fields
            allowed = set(mandatory + visible_fields)
            
            # Remove any field that isn't in the allowed list
            for field_name in list(self.fields.keys()):
                if field_name not in allowed:
                    del self.fields[field_name]
        
        # 2. Apply CSS Styling & Translations
        for field_name, field in self.fields.items():
            # Apply Bootstrap styling (if not already handled by widgets)
            if not isinstance(
                field.widget,
                (forms.CheckboxInput, forms.RadioSelect, forms.FileInput),
            ):
                existing = field.widget.attrs.get("class", "")
                if "form-control" not in existing:
                     field.widget.attrs["class"] = existing + " form-control"

            # Apply Translations
            if field_name in VISA_LABELS:
                # Get the label for the requested language, default to the field name if missing
                translation = VISA_LABELS[field_name].get(lang)
                if translation:
                    field.label = translation
