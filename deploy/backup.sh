#!/usr/bin/env bash
# Copies the database and the uploaded files to /var/backups/pea and keeps the last 14 days, checks that the audit
# log is intact, and (when set up) sends an encrypted copy off the server.
#   ./deploy/backup.sh          (deploy.sh runs it too; install it in cron as DEPLOY.md shows)
# Off-site copies need two settings in deploy/.env (see DEPLOY.md, "Backups"): BACKUP_GPG_RECIPIENT, the key the
# copies are encrypted for, and BACKUP_REMOTE, where rsync sends them. Without them the copies stay on this server,
# which helps after a mistake but not after the disk dies.
set -euo pipefail
cd "$(dirname "$0")"

dest=${BACKUP_DIR:-/var/backups/pea}
keep_days=${BACKUP_KEEP_DAYS:-14}
stamp=$(date +%Y-%m-%d-%H%M)
mkdir -p "$dest"
umask 077 # the backups hold personal data: only this user may read them

# A setting from deploy/.env, read as plain text (the file is never run as a script)
setting() { grep -E "^$1=" .env 2>/dev/null | tail -n 1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' || true; }

echo "== Backup to $dest ($(date '+%Y-%m-%d %H:%M'))"
# Written under a temporary name first, so a backup that fails halfway is never mistaken for a good one
docker compose exec -T db pg_dump -U pea -d pea --format=custom > "$dest/.pea-$stamp.dump"
mv "$dest/.pea-$stamp.dump" "$dest/pea-$stamp.dump"
# A one-off container from the API's image reads the files, so this works even while the API is down
docker compose run --rm -T --no-deps api tar -C /data -czf - storage > "$dest/.storage-$stamp.tar.gz"
mv "$dest/.storage-$stamp.tar.gz" "$dest/storage-$stamp.tar.gz"

find "$dest" -maxdepth 1 -type f \( -name 'pea-*.dump' -o -name 'storage-*.tar.gz' \) -mtime "+$keep_days" -delete
ls -lh "$dest" | tail -n 4

# The audit log's hash chain (scripts/verify_audit.py). The line it prints, with the newest entry's hash, stays in
# backup.log, so entries removed later from the end of the log would show too. Never stops a backup or a deploy.
echo "== Audit log"
if docker compose exec -T api python -c "import scripts.verify_audit" > /dev/null 2>&1; then
  docker compose exec -T api python -m scripts.verify_audit || echo "!! THE AUDIT LOG IS BROKEN: see the line above, and DEPLOY.md"
else
  echo "(skipped: the API isn't running, or is older than the audit check)"
fi

# Off the server: encrypted for BACKUP_GPG_RECIPIENT (only the holder of its private key can read the copies; the key
# isn't on this server), then sent to BACKUP_REMOTE with rsync over SSH. Personal data never leaves unencrypted.
remote=$(setting BACKUP_REMOTE)
recipient=$(setting BACKUP_GPG_RECIPIENT)
if [[ -n "$remote" ]]; then
  echo "== Encrypted copy to $remote"
  if [[ -z "$recipient" ]]; then
    echo "!! BACKUP_REMOTE is set but BACKUP_GPG_RECIPIENT isn't: not sending unencrypted personal data off the server"
    exit 1
  fi
  outbox=$(mktemp -d)
  trap 'rm -rf "$outbox"' EXIT
  for file in "$dest/pea-$stamp.dump" "$dest/storage-$stamp.tar.gz"; do
    gpg --batch --yes --trust-model always --encrypt --recipient "$recipient" \
      --output "$outbox/$(basename "$file").gpg" "$file"
  done
  rsync --archive --partial --timeout=600 "$outbox/" "$remote/"
  echo "Sent $(ls "$outbox" | wc -l) encrypted files"
fi
