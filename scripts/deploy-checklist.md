# VPS Deployment Checklist

## Pre-Deployment Tasks

### 1. Static Files
- [x] Dockerfile updated with collectstatic step
- [x] Static files collected locally (6 files copied, 162 unmodified)
- [ ] Verify all static files are present in production

### 2. Environment Variables
Set these on your VPS:
```bash
DJANGO_SECRET_KEY=your-secure-secret-key
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DATABASE_URL=postgres://user:password@host:5432/dbname
```

### 3. Build and Deploy
```bash
# Build and start services
docker-compose up --build

# Run migrations
docker-compose exec web python manage.py migrate

# Create superuser if needed
docker-compose exec web python manage.py createsuperuser

# Seed initial data
docker-compose exec web python manage.py seed
```

### 4. Verify Layout
- [ ] Admin panel loads correctly at /admin
- [ ] Dashboard displays properly at /dashboard/
- [ ] Tools hub works at /tools/
- [ ] Dark/light mode switching works
- [ ] All CSS and JS files load (check browser console)

### 5. Static File Verification
Check that these are accessible:
- /static/unfold/css/styles.css
- /static/dima_voyages.png
- /static/js/airport_search.js

### 6. Common Issues to Check
- [ ] 404 errors for static files
- [ ] CSS custom properties not working
- [ ] Admin theme not loading
- [ ] Media file uploads working

## Post-Deployment Verification
```bash
# Check container logs
docker-compose logs web
docker-compose logs nginx

# Test static file serving
curl -I http://yourdomain.com/static/unfold/css/styles.css
```
