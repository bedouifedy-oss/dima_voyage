# core/management/commands/seed.py
from django.core.management.base import BaseCommand
from core.models import Client, Booking, Payment, Supplier, Expense
from django.contrib.auth import get_user_model
from decimal import Decimal
from datetime import date, timedelta
import random

User = get_user_model()

class Command(BaseCommand):
    help = 'Seeds the database with initial testing data.'

    def handle(self, *args, **options):
        self.stdout.write("Starting database seeding...")
        
        # 1. Create Superuser (Admin)
        try:
            u, created = User.objects.get_or_create(username='admin', defaults={'email': 'admin@example.com', 'is_staff': True, 'is_superuser': True})
            if created:
                u.set_password('password') # ⚠️ CHANGE THIS IMMEDIATELY
                u.save()
                self.stdout.write(self.style.SUCCESS('Superuser "admin" created with password "password"'))
            else:
                self.stdout.write('Superuser "admin" already exists.')
        except Exception as e:
             self.stdout.write(self.style.ERROR(f"Error creating user: {e}"))
             return

        # 2. Create Clients and Suppliers
        c = Client.objects.create(name='Ali Hassan', phone='+21655123456', passport='A1234567')
        s1 = Supplier.objects.create(name='Emirates Airlines', contact='flights@emirates.com')
        s2 = Supplier.objects.create(name='Hilton Hotels', contact='hotels@hilton.com')

        # 3. Create Sample Bookings
        b1 = Booking.objects.create(
            ref='DIMA-20251128-0001', 
            client=c, 
            booking_type='ticket', 
            description='Round trip to Dubai',
            total_amount=Decimal('1200.00'), 
            supplier_cost=Decimal('900.00'), 
            created_by=u,
            status='pending'
        )
        b2 = Booking.objects.create(
            ref='DIMA-20251127-0002', 
            client=c, 
            booking_type='hotel', 
            description='Paris hotel 4 nights',
            total_amount=Decimal('800.00'), 
            supplier_cost=Decimal('650.00'), 
            created_by=u,
            status='confirmed'
        )
        
        # 4. Create Payments
        # Partial payment for b1 (Outstanding: 1200 - 500 = 700)
        Payment.objects.create(
            booking=b1, 
            amount=Decimal('500.00'), 
            method='bank', 
            date=date.today(), 
            reference='TXID12345', 
            created_by=u
        )
        
        # Full payment for b2
        Payment.objects.create(
            booking=b2, 
            amount=Decimal('800.00'), 
            method='card', 
            date=date.today() - timedelta(days=1), 
            reference='CARD67890', 
            created_by=u
        )
        
        # 5. Create Expenses (Future Spendings)
        Expense.objects.create(
            name='Office Rent',
            amount=Decimal('1500.00'),
            due_date=date.today() + timedelta(days=5),
            paid=False,
            recurrence='monthly'
        )
        Expense.objects.create(
            name='Marketing Software Subscription',
            amount=Decimal('199.99'),
            due_date=date.today() + timedelta(days=60),
            paid=False,
            supplier=None,
            recurrence='monthly'
        )

        self.stdout.write(self.style.SUCCESS("Database seeding complete. Go to http://localhost:8000/admin"))
