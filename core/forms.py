from django import forms

from .models import Booking, Payment, VisaApplication

# --- 1. FIELD TRANSLATIONS ---
VISA_LABELS = {
    "full_name": {"tn": "الاسم الكامل", "fr": "Nom complet"},
    "dob": {"tn": "تاريخ الولادة", "fr": "Date de naissance"},
    "nationality": {"tn": "الجنسية", "fr": "Nationalité"},
    "passport_number": {"tn": "رقم الباسبور", "fr": "Numéro de passeport"},
    "passport_issue_date": {"tn": "تاريخ إصدار الباسبور", "fr": "Date de délivrance"},
    "passport_expiry_date": {"tn": "تاريخ انتهاء الباسبور", "fr": "Date d'expiration"},
    "photo": {"tn": "تصويرة الباسبور", "fr": "Photo du passeport"},
    "has_previous_visa": {
        "tn": "عندك فيزا سابقة؟",
        "fr": "Avez-vous un visa précédent ?",
    },
    "previous_visa_details": {
        "tn": "تفاصيل التأشيرات السابقة",
        "fr": "Détails des visas précédents",
    },
    # Contact
    "phone": {"tn": "رقم التليفون", "fr": "Téléphone"},
    "email": {"tn": "الإيميل", "fr": "Email"},
    "address": {"tn": "العنوان", "fr": "Adresse"},
    "emergency_contact": {"tn": "شكون نكلمو في حالة طوارئ", "fr": "Contact d'urgence"},
    # Trip Details
    "travel_reason": {"tn": "سبب السفر", "fr": "Motif du voyage"},
    "departure_date": {"tn": "تاريخ الذهاب", "fr": "Date de départ"},
    "return_date": {"tn": "تاريخ المروح", "fr": "Date de retour"},
    "itinerary": {"tn": "برنامج الرحلة", "fr": "Itinéraire"},
    "ticket_departure": {"tn": "تذكرة الذهاب", "fr": "Billet de départ"},
    "ticket_return": {"tn": "تذكرة العودة", "fr": "Billet de retour"},
    "travel_insurance": {"tn": "تأمين السفر", "fr": "Assurance voyage"},
    # Accommodation
    "accommodation_type": {"tn": "نوع السكن", "fr": "Type d'hébergement"},
    "host_name": {"tn": "اسم المستضيف", "fr": "Nom de l'hôte"},
    "host_address": {"tn": "عنوان المستضيف", "fr": "Adresse de l'hôte"},
    "host_phone": {"tn": "تليفون المستضيف", "fr": "Téléphone de l'hôte"},
    "host_email": {"tn": "إيميل المستضيف", "fr": "Email de l'hôte"},
    "host_relationship": {"tn": "صلة القرابة", "fr": "Relation avec l'hôte"},
    "hotel_name": {"tn": "اسم الوتيل", "fr": "Nom de l'hôtel"},
    "hotel_address": {"tn": "عنوان الوتيل", "fr": "Adresse de l'hôtel"},
    "hotel_reservation": {"tn": "حجز الوتيل", "fr": "Réservation d'hôtel"},
    # Financials
    "payer": {"tn": "شكون باش يخلص؟", "fr": "Qui finance le voyage ?"},
    "financial_proofs": {"tn": "إثباتات مالية", "fr": "Preuves financières"},
    "guarantor_details": {"tn": "معلومات الضامن", "fr": "Détails du garant"},
    # Consents
    "consent_accurate": {
        "tn": "أصرح أن المعلومات صحيحة",
        "fr": "Je déclare que ces informations sont exactes",
    },
    "consent_data": {
        "tn": "أوافق على معالجة بياناتي",
        "fr": "J'accepte le traitement de mes données",
    },
    "consent_send_docs": {
        "tn": "موافق بش نبعث الوثائق",
        "fr": "J'accepte d'envoyer les documents",
    },
}


# --- 2. CONFIGURATION FORM ---
class VisaFieldConfigurationForm(forms.Form):
    _choices = []

    for f in VisaApplication._meta.fields:
        if f.name in ["id", "booking", "submitted_at", "photo", "passport_number"]:
            continue

        # Priority: French Label -> Model Verbose -> DB Name
        if f.name in VISA_LABELS:
            label = VISA_LABELS[f.name]["fr"]
        elif hasattr(f, "verbose_name") and f.verbose_name:
            label = f.verbose_name
        else:
            label = f.name

        _choices.append((f.name, label))

    selected_fields = forms.MultipleChoiceField(
        choices=_choices,
        widget=forms.CheckboxSelectMultiple,
        label="Select Additional Fields",
        required=False,
    )


# --- 3. BOOKING ADMIN FORM ---


class BookingAdminForm(forms.ModelForm):
    # --- COMMAND CENTER FIELDS (Ghost Fields) ---
    ACTION_CHOICES = [
        ("none", "--- Select Action ---"),
        ("payment", "💰 Add Payment (Income)"),
        ("refund", "💸 Issue Refund (Outgoing)"),
        ("supplier_payment", "📤 Record Supplier Payment"),
    ]

    payment_action = forms.ChoiceField(
        choices=ACTION_CHOICES, required=False, label="⚡ Quick Action"
    )

    transaction_amount = forms.DecimalField(
        required=False, decimal_places=2, max_digits=12, min_value=0, label="Amount"
    )

    transaction_method = forms.ChoiceField(
        choices=Payment.PAYMENT_METHODS, required=False, label="Method"
    )

    class Meta:
        model = Booking
        fields = "__all__"
        widgets = {
            "visa_form_config": forms.CheckboxSelectMultiple(
                choices=[
                    ("dob", "Date of Birth"),
                    ("nationality", "Nationality"),
                    ("passport_issue_date", "Passport Issue Date"),
                    ("passport_expiry_date", "Passport Expiry Date"),
                    ("has_previous_visa", "Previous Visa History"),
                    ("travel_reason", "Reason for Travel"),
                    ("departure_date", "Departure Date"),
                    ("return_date", "Return Date"),
                    ("ticket_departure", "Flight Ticket (Departure)"),
                    ("ticket_return", "Flight Ticket (Return)"),
                    ("travel_insurance", "Travel Insurance"),
                    ("hotel_reservation", "Hotel Reservation"),
                    ("financial_proofs", "Bank Statement / Proofs"),
                    ("emergency_contact", "Emergency Contact"),
                ]
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get("payment_action")
        amount = cleaned_data.get("transaction_amount")

        # Validation: If an action is selected, Amount is required
        if action != "none" and action is not None:
            if not amount:
                self.add_error(
                    "transaction_amount", "⚠️ Amount is required for this action."
                )

        return cleaned_data


# --- 4. PUBLIC VISA FORM ---
class VisaForm(forms.ModelForm):
    class Meta:
        model = VisaApplication
        fields = "__all__"
        exclude = ["booking", "submitted_at"]

        widgets = {
            "dob": forms.DateInput(attrs={"type": "date"}),
            "passport_issue_date": forms.DateInput(attrs={"type": "date"}),
            "passport_expiry_date": forms.DateInput(attrs={"type": "date"}),
            "departure_date": forms.DateInput(attrs={"type": "date"}),
            "return_date": forms.DateInput(attrs={"type": "date"}),
            "address": forms.Textarea(attrs={"rows": 2}),
            "previous_visa_details": forms.Textarea(attrs={"rows": 2}),
            "itinerary": forms.Textarea(attrs={"rows": 2}),
            "emergency_contact": forms.Textarea(attrs={"rows": 2}),
            "guarantor_details": forms.Textarea(attrs={"rows": 2}),
            "accommodation_type": forms.Select(attrs={"class": "form-select"}),
            "payer": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        visible_fields = kwargs.pop("visible_fields", None)
        lang = kwargs.pop("lang", "tn")

        super().__init__(*args, **kwargs)

        # 1. Visibility Logic
        mandatory = ["passport_number", "photo"]
        if visible_fields:
            allowed = set(mandatory + visible_fields)
            for field_name in list(self.fields.keys()):
                if field_name not in allowed:
                    del self.fields[field_name]

        # 2. Styling & Translation Logic
        for field_name, field in self.fields.items():
            if not isinstance(
                field.widget, (forms.CheckboxInput, forms.RadioSelect, forms.FileInput)
            ):
                existing = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = existing + " form-control"

            if field_name in VISA_LABELS:
                translation = VISA_LABELS[field_name].get(lang)
                if translation:
                    field.label = translation


# --- 5. INTERNAL ADMIN INLINE FORM (Fixes Mixed Language) ---
class VisaInlineForm(forms.ModelForm):
    class Meta:
        model = VisaApplication
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Force ALL labels to use the French translation from our Dictionary
        for field_name, field in self.fields.items():
            if field_name in VISA_LABELS:
                # Use French ('fr') for the Admin Panel context
                # You can change 'fr' to 'tn' if you prefer Arabic in the Admin
                label = VISA_LABELS[field_name].get("fr")
                if label:
                    field.label = label
