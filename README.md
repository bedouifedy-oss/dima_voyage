Dima Voyage – Internal Admin Panel & Analytics Platform

This repository contains the internal admin system for Dima Voyage, built with Django, fully containerized with Docker, and integrated with Metabase for real-time analytics.
It supports operational workflows, compliance/KYC logic, financial tracking, booking management, and dynamic reporting dashboards.

The architecture is designed for maintainability, secure deployment, and reproducibility across environments.

📦 Features

Custom Django admin with extended templates

Integrated Metabase dashboards (via external or internal deployment)

User management and operational workflow logic

Seed script for initial data (seed.py)

Automated backup & restore scripts (backup.sh, restore.sh)

Dockerized environment for consistent deployment

Database versioning through Django migrations

Internal invoice templates and booking logic

🧱 Project Structure
dima_finance/
│
├── config/                 # Django project settings
├── core/                   # Main application (models, admin, signals, templates)
│   ├── management/         # CLI management commands (seed etc.)
│   ├── migrations/         # Database migrations
│   ├── templates/          # Custom admin and invoice templates
│
├── scripts/                # Backup/restore scripts and utilities
│   ├── backups/            # Generated database backups
│
├── docker-compose.yml      # Multi-service environment
├── Dockerfile              # Django app container
├── requirements.txt        # Python dependencies
├── manage.py               # Django management entrypoint

🚀 Running Locally (Docker)
1. Build and start all services:
docker-compose up --build

2. Access the services:

Django admin → http://localhost:8000/admin

Django app → http://localhost:8000

Metabase (if included) → http://localhost:3000

🛠 Development Commands

Apply migrations:

docker-compose exec web python manage.py migrate


Create superuser:

docker-compose exec web python manage.py createsuperuser


Seed initial data:

docker-compose exec web python manage.py seed

📂 Database Backups

Backup the PostgreSQL database:

./scripts/backup.sh


Restore from a backup:

./scripts/restore.sh backups/<file.sql.gz>


Backups are stored in scripts/backups/.

🧪 Running Locally Without Docker

Install dependencies:

pip install -r requirements.txt


Run migrations:

python manage.py migrate


Start the server:

python manage.py runserver

☁️ Deployment Notes (GCP / VPS)

This repository is prepared for deployment on:

Google Cloud Run

Google Compute Engine (VM)

Any VPS with Docker installed

Minimal environment variables required:

SECRET_KEY=...
DATABASE_URL=...
DEBUG=False
ALLOWED_HOSTS=...


For GCP → build using Cloud Build or build locally and deploy container.

📊 Metabase Integration

Metabase is deployed separately (container or cloud), but the Django project exposes clean models and tables for analytics.
Ideal for:

Financial dashboards

Booking performance

Supplier payments

Activity logs and KYC/compliance checks

🔒 Security Notes

Never commit .env or secrets

Use .gitignore to exclude migration caches, media, internal logs

When deploying to GCP, store secrets in Secret Manager

Follow least-privilege access in Django admin

📜 License

This project is intended for internal use and does not include an open-source license.

👤 Maintainer

Fedy (bedouifedy-oss)
GitHub: https://github.com/bedouifedy-oss
