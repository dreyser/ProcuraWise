#!/usr/bin/env bash
# Runs the Playwright E2E suite against a real API + Vite + Mongo/Azurite.
# Extracted from the Makefile (was a single trap-in-a-recipe one-liner) after
# `make test-e2e` segfaulted in CI (GitHub Actions ubuntu-latest) right after
# both specs printed "passed", during cleanup - never reproduced locally.
# The most likely culprit was `$(MAKE) dev-down` being invoked recursively
# from *inside* a signal trap that itself lived inside a backslash-continued,
# `$$`-escaped Make recipe line - a fragile combination of GNU Make's
# recursive-make/jobserver machinery and shell trap handling. This script
# removes that nesting entirely (calls `docker compose down` directly, not
# through `make`) and is independently testable/shellcheck-able, unlike an
# inline Makefile recipe string.
set -uo pipefail
# Deliberately not `set -e`: cleanup() must still run every step even if an
# earlier one already failed, so a partial failure doesn't leak processes.

cd "$(dirname "$0")/.." || exit 1

API_LOG=/tmp/procurawise-e2e-api.log
WEB_LOG=/tmp/procurawise-e2e-web.log
API_PID=""
WEB_PID=""

cleanup() {
  [ -n "$API_PID" ] && kill "$API_PID" 2>/dev/null
  [ -n "$WEB_PID" ] && kill "$WEB_PID" 2>/dev/null
  pkill -f "uvicorn.*procurawise.api.main:app.*--port 8000" 2>/dev/null
  pkill -f "vite.*--port 5173" 2>/dev/null
  docker compose down
}
trap cleanup EXIT INT TERM

(cd service && uv run uvicorn procurawise.api.main:app --port 8000 >"$API_LOG" 2>&1) &
API_PID=$!
(cd apps/web && pnpm dev --port 5173 >"$WEB_LOG" 2>&1) &
WEB_PID=$!

echo "Esperando a que la API este lista..."
i=0
until curl -sf http://localhost:8000/health/ready >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -ge 60 ]; then
    echo "La API no respondio a tiempo"
    cat "$API_LOG"
    exit 1
  fi
  sleep 1
done

echo "Esperando a que el frontend este listo..."
i=0
until curl -sf http://localhost:5173/ >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -ge 60 ]; then
    echo "El frontend no respondio a tiempo"
    cat "$WEB_LOG"
    exit 1
  fi
  sleep 1
done

(cd apps/web && pnpm exec playwright test)
