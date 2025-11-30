# core/views.py
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.contrib.auth.decorators import login_required
import weasyprint
from .models import Booking
from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
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
    
    if len(term) < 3:
        return JsonResponse([], safe=False)
        
    results = search_airports(term)
    return JsonResponse(results, safe=False)
