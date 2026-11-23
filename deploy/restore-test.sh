#!/usr/bin/env bash
# Proves a backup can be restored: loads it into a throwaway database (a separate container without any network,
# never the live one), compares it with the live database, checks the uploaded files' archive, then removes it all.
#   ./deploy/restore-test.sh                                  # the newest backup
#   ./deploy/restore-test.sh /var/backups/pea/pea-….dump      # a particular one
# Run it now and then (DEPLOY.md suggests monthly): a backup that has never been restored isn't proven.
set -euo pipefail
cd "$(dirname "$0")"

dest=${BACKUP_DIR:-/var/backups/pea}
dump=${1:-$(ls -t "$dest"/pea-*.dump 2>/dev/null | head -n 1)}
[[ -f "$dump" ]] || { echo "No backup found in $dest"; exit 1; }
archive="$dest/storage-$(basename "$dump" .dump | sed 's/^pea-//').tar.gz"
name="pea-restore-test-$$"

echo "== Restoring $(basename "$dump") into a throwaway database ($name)"
docker run -d --rm --name "$name" --network none -e POSTGRES_PASSWORD="$(openssl rand -hex 16)" \
  postgres:16-alpine > /dev/null
trap 'docker stop "$name" > /dev/null 2>&1 || true' EXIT
for _ in $(seq 60); do docker exec "$name" pg_isready -U postgres -q 2>/dev/null && break; sleep 1; done
docker exec "$name" createdb -U postgres pea
docker exec -i "$name" pg_restore -U postgres -d pea --no-owner --no-privileges --exit-on-error < "$dump"

count() { echo "select (select version_num from alembic_version) || ' / ' || (select count(*) from users) || ' people / '
  || (select count(*) from audit_log) || ' audit entries / ' || (select count(*) from files) || ' files'"; }
restored=$(docker exec -i "$name" psql -U postgres -d pea -At < <(count))
live=$(docker compose exec -T db psql -U pea -d pea -At < <(count))
echo "Restored: $restored"
echo "Live now: $live (newer changes since the backup are normal)"

if [[ -f "$archive" ]]; then
  echo "== Uploaded files: $(tar -tzf "$archive" | grep -vc '/$') in $(basename "$archive"), archive readable"
else
  echo "!! No files archive for this backup ($archive)"
  exit 1
fi
echo "== The backup restores. The throwaway database is removed now."
