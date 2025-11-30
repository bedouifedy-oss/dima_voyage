# Dockerfile
FROM python:3.12-slim

# 1. Prevent Python from writing pyc files to disc
ENV PYTHONUNBUFFERED 1
ENV DJANGO_SETTINGS_MODULE config.settings

# 2. Set work directory
WORKDIR /code

# 3. Install SYSTEM dependencies (Required for WeasyPrint & Postgres)
# We group these in one RUN command to keep the image small
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-cffi \
    python3-brotli \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz-subset0 \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# 4. Install Python dependencies
COPY requirements.txt /code/
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy project code
COPY . /code/

# 6. Default command
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]