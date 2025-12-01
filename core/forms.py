# core/forms.py
from django import forms
from .models import VisaApplication

class VisaForm(forms.ModelForm):
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
