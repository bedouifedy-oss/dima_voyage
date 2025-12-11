import pytest
from django.test import Client as DjangoClient
from django.urls import reverse

from core.models import Booking, Client, VisaApplication


@pytest.mark.django_db
def test_public_visa_form_get():
    django_client = DjangoClient()
    c = Client.objects.create(
        name="Test Client", phone="+21612345678", passport="A1234567"
    )
    booking = Booking.objects.create(
        ref="TEST-001",
        client=c,
        booking_type="ticket",
        operation_type="issue",
        total_amount="1000.00",
        supplier_cost="800.00",
        description="Test booking",
    )
    url = reverse("public_visa_form", kwargs={"ref": booking.ref})
    response = django_client.get(url)
    assert response.status_code == 200
    assert booking.ref.encode() in response.content


@pytest.mark.django_db
def test_public_visa_form_post_minimal():
    django_client = DjangoClient()
    c = Client.objects.create(
        name="Test Client", phone="+21612345678", passport="A1234567"
    )
    booking = Booking.objects.create(
        ref="TEST-002",
        client=c,
        booking_type="ticket",
        operation_type="issue",
        total_amount="1000.00",
        supplier_cost="800.00",
        description="Test booking",
    )
    url = reverse("public_visa_form", kwargs={"ref": booking.ref})
    from django.core.files.uploadedfile import SimpleUploadedFile

    # Minimal 1x1 JPEG image (valid)
    fake_photo = SimpleUploadedFile(
        "photo.jpg",
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x01\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00\xaa\xff\xd9",
        content_type="image/jpeg",
    )
    data = {
        "passport_number": "A1234567",
        "photo": fake_photo,
    }
    response = django_client.post(url, data)
    assert response.status_code == 200
    assert VisaApplication.objects.filter(booking=booking).exists()
