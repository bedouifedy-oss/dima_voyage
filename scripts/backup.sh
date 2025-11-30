#!/bin/bash
# Stop script on error and ensure pipe errors are caught
set -e
set -o pipefail

# Configuration
CONTAINER_NAME="dima_finance-db-1"
DB_USER="dima"
DB_NAME="dima_finance"
BACKUP_DIR="./backups"
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
FILENAME="$BACKUP_DIR/backup_$TIMESTAMP.sql.gz"

# Ensure backup directory exists
mkdir -p $BACKUP_DIR

echo "📦 Starting backup of $DB_NAME..."

# Execute dump inside container and pipe to gzip on host
# REMOVED -T flag. 
docker exec $CONTAINER_NAME pg_dump -U $DB_USER $DB_NAME | gzip > $FILENAME

# Check if file exists and has size greater than 100 bytes (empty gzip is ~20 bytes)
if [ -s "$FILENAME" ] && [ $(wc -c < "$FILENAME") -gt 100 ]; then
    echo "✅ Backup successful: $FILENAME"
    # Cleanup old backups (optional)
    find $BACKUP_DIR -type f -name "*.sql.gz" -mtime +30 -delete
else
    echo "❌ Backup failed or file is empty!"
    rm -f $FILENAME
    exit 1
fi
