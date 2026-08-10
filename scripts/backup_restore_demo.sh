#!/usr/bin/env bash
# Fase 26 (Hardening, plan Bloque 7): MVP-level backup/restore verification.
#
# MongoDB Atlas M0 (ADR 0015, the tier approved for the whole MVP) does not
# offer managed Cloud Backups at all - that requires an M10+ tier, an
# upgrade explicitly classified as "post-MVP, sin gatillo numerico
# predefinido" in ADR 0015, not reopened by this script. No real
# infrastructure exists yet either way (Fase 27 provisions it). This script
# is therefore deliberately scoped to what IS demonstrable today: a real
# mongodump -> mongorestore round trip against the local Docker Compose
# MongoDB (make dev-up), verified by comparing per-collection document
# counts between the source database and a freshly restored one. It is NOT
# equivalent to an Atlas managed backup/restore and never claims to be -
# see docs/operations/deployment.md, section "Backup / restore".
#
# Usage:
#   make dev-up && make seed-dev
#   bash scripts/backup_restore_demo.sh
set -euo pipefail

MONGO_CONTAINER="procurawise-mongo"
SOURCE_DB="procurawise_local"
RESTORE_DB="procurawise_backup_verify"
DUMP_DIR_IN_CONTAINER="/tmp/procurawise-backup-demo"

if ! docker inspect "$MONGO_CONTAINER" >/dev/null 2>&1; then
  echo "El contenedor $MONGO_CONTAINER no está corriendo - ejecuta 'make dev-up' primero." >&2
  exit 1
fi

echo "== 1. Conteo de documentos por colección en $SOURCE_DB (antes del backup) =="
BEFORE_COUNTS=$(docker exec "$MONGO_CONTAINER" mongosh "$SOURCE_DB" --quiet --eval '
  db.getCollectionNames().sort().map(name => name + ": " + db.getCollection(name).countDocuments()).join("\n")
')
echo "$BEFORE_COUNTS"

echo
echo "== 2. mongodump: $SOURCE_DB -> $DUMP_DIR_IN_CONTAINER (dentro del contenedor) =="
docker exec "$MONGO_CONTAINER" rm -rf "$DUMP_DIR_IN_CONTAINER"
docker exec "$MONGO_CONTAINER" mongodump --db="$SOURCE_DB" --out="$DUMP_DIR_IN_CONTAINER" --quiet

echo
echo "== 3. mongorestore: $DUMP_DIR_IN_CONTAINER -> $RESTORE_DB (base de verificación separada) =="
docker exec "$MONGO_CONTAINER" mongosh "$RESTORE_DB" --quiet --eval 'db.dropDatabase()' >/dev/null
# --dir must point at the *parent* of the "$SOURCE_DB" folder mongodump
# produced (mongorestore expects to discover the db-named subdirectory
# itself when combined with --nsFrom/--nsTo remapping) - pointing directly
# at the db-named subfolder silently restores nothing ("don't know what to
# do with file ..., skipping" for every .bson, confirmed while building
# this script against a real container).
docker exec "$MONGO_CONTAINER" mongorestore \
  --nsFrom="${SOURCE_DB}.*" \
  --nsTo="${RESTORE_DB}.*" \
  --dir="$DUMP_DIR_IN_CONTAINER" \
  --quiet

echo
echo "== 4. Conteo de documentos por colección en $RESTORE_DB (después del restore) =="
AFTER_COUNTS=$(docker exec "$MONGO_CONTAINER" mongosh "$RESTORE_DB" --quiet --eval '
  db.getCollectionNames().sort().map(name => name + ": " + db.getCollection(name).countDocuments()).join("\n")
')
echo "$AFTER_COUNTS"

echo
if [ "$BEFORE_COUNTS" = "$AFTER_COUNTS" ]; then
  echo "OK: los conteos por colección coinciden exactamente entre $SOURCE_DB y $RESTORE_DB restaurada."
  RESULT=0
else
  echo "FALLO: los conteos difieren - ver arriba. No coincide backup/restore." >&2
  RESULT=1
fi

echo
echo "== 5. Limpieza (base de verificación + dump temporal dentro del contenedor) =="
docker exec "$MONGO_CONTAINER" mongosh "$RESTORE_DB" --quiet --eval 'db.dropDatabase()' >/dev/null
docker exec "$MONGO_CONTAINER" rm -rf "$DUMP_DIR_IN_CONTAINER"
echo "Listo."

exit $RESULT
