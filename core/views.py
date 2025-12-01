# core/views.py
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
import weasyprint

from .models import Booking
from .forms import VisaForm
from .utils import search_airports

@login_required
def invoice_pdf(request, booking_id):
    # 1. Get the booking (securely)
    booking = get_object_or_404(Booking, id=booking_id)
    
    # 2. Render HTML template with data
    html_string = render_to_string('invoice.html', {'booking': booking})
    
    # 3. Convert to PDF
    pdf_file = weasyprint.HTML(string=html_string).write_pdf()
    
    # 4. Create HTTP response
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="invoice_{booking.ref}.pdf"'
    return response

@staff_member_required
def airport_autocomplete(request):
    term = request.GET.get('term', '')
    
    # Changed to 2 so "TU" works for Tunis
    if len(term) < 2:
        return JsonResponse([], safe=False)
        
    results = search_airports(term)
    return JsonResponse(results, safe=False)

def public_visa_form(request, ref_id):
    booking = get_object_or_404(Booking, ref=ref_id)
    
    # 1. Get language
    lang = request.GET.get('lang', 'tn')

    # 2. Define Messages & Template names based on language
    if lang == 'fr':
        success_msg = "Votre dossier a été transmis à notre équipe avec succès."
        success_template = "visa_success_fr.html"
        form_template = "visa_form_fr.html"
    else:
        success_msg = "دوسيك وصلنا وباش نركحوه. تو نكلموك."
        success_template = "visa_success_tn.html"
        form_template = "visa_form_tn.html"

    # 3. Check if already filled
    if hasattr(booking, 'visa_data'):
        return render(request, success_template, {'msg': success_msg})

    # 4. Handle Submission
    if request.method == 'POST':
        form = VisaForm(request.POST, request.FILES)
        if form.is_valid():
            visa_app = form.save(commit=False)
            visa_app.booking = booking
            visa_app.save()
            return render(request, success_template, {'msg': success_msg})
    else:
        form = VisaForm()

    return render(request, form_template, {'form': form, 'booking': booking, 'lang': lang})
