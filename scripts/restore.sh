#!/bin/bash
set -e 

# Configuration
CONTAINER_NAME="dima_finance-db-1"
DB_USER="dima"
DB_NAME="dima_finance"

if [ -z "$1" ]; then
    echo "❌ Usage: .scripts/restore.sh <path_to_backup_file.sql.gz>"
    exit 1
fi

BACKUP_FILE=$1

if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ File not found: $BACKUP_FILE"
    exit 1
fi

echo "⚠️  DANGER ZONE ⚠️"
echo "You are about to DESTROY '$DB_NAME' and replace it with '$BACKUP_FILE'."
read -p "Are you sure? (Type 'yes' to proceed): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Operation cancelled."
    exit 0
fi

echo "♻️  Restoring database..."

# 1. Terminate connections (Removed -T)
docker exec $CONTAINER_NAME psql -U $DB_USER -d postgres -c "
SELECT pg_terminate_backend(pid) 
FROM pg_stat_activity 
WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();"

# 2. Drop and Recreate DB (Removed -T)
docker exec $CONTAINER_NAME psql -U $DB_USER -d postgres -c "DROP DATABASE IF EXISTS $DB_NAME;"
docker exec $CONTAINER_NAME psql -U $DB_USER -d postgres -c "CREATE DATABASE $DB_NAME;"

# 3. Restore (Added -i for interactive input stream)
gunzip -c $BACKUP_FILE | docker exec -i $CONTAINER_NAME psql -U $DB_USER -d $DB_NAME

echo "✅ Restore complete."
