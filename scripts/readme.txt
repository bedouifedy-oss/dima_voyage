Run the following to restore:

./restore.sh backups/backup_2025-11-28_20-49-47.sql.gz


In production (on your Linux VPS), you don't want to run backup.sh manually. Add it to the system cron.

Open crontab: crontab -e

Add this line to run every day at 3 AM:

Bash

0 3 * * * /path/to/dima_finance/scripts/backup.sh >> /var/log/dima_backup.log 2>&1


:wq
