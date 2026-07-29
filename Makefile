# Pin bash explicitly: without this, make falls back to the system default
# /bin/sh, which is a bash-derived shell on macOS (where this Makefile is
# developed/verified) but dash on the GitHub Actions ubuntu-latest runner.
# dash has known bugs in trap+background-job (`&`/`$!`) handling when the
# trap itself spawns further processes - exactly the pattern `test-e2e` uses
# (kill + two pkill -f + a nested $(MAKE) dev-down inside a single EXIT
# trap) - which segfaulted dash in CI right after both Playwright specs
# printed "2 passed", during the trap's cleanup. Never reproduced locally
# because macOS's /bin/sh doesn't have this issue.
SHELL := /bin/bash

.PHONY: dev test test-backend test-frontend lint lint-backend lint-frontend typecheck typecheck-backend typecheck-frontend contracts migrate dev-up dev-down dev-logs dev-status dev-reset test-integration test-e2e seed-dev seed-reset

dev:
	@trap 'kill 0' EXIT INT TERM; \
	(cd service && uv run uvicorn procurawise.api.main:app --reload --port 8000) & \
	(cd apps/web && pnpm dev) & \
	wait

test: test-backend test-frontend

test-backend:
	cd service && uv run pytest -m "not docker"

test-frontend:
	cd apps/web && pnpm test

lint: lint-backend lint-frontend

lint-backend:
	cd service && uv run ruff check . && uv run ruff format --check .

lint-frontend:
	cd apps/web && pnpm lint && pnpm format

typecheck: typecheck-backend typecheck-frontend

typecheck-backend:
	cd service && uv run mypy procurawise

typecheck-frontend:
	cd apps/web && pnpm typecheck

contracts:
	cd service && uv run python -m procurawise.api.export_openapi
	cd apps/web && pnpm contracts

migrate:
	cd service && uv run python -m procurawise.shared.migrations

seed-dev:
	cd service && uv run python -m procurawise.dev_seed

seed-reset:
	@if [ "$(CONFIRM)" != "yes" ]; then \
		echo "ADVERTENCIA: seed-reset borra tenants/users/memberships/vendor_organizations de desarrollo en la base local."; \
		echo "Vuelve a correr con 'make seed-reset CONFIRM=yes' si estas seguro."; \
		exit 1; \
	fi
	cd service && uv run python -m procurawise.dev_seed --reset

dev-up:
	docker compose up -d --wait

dev-down:
	docker compose down

dev-logs:
	docker compose logs -f mongo azurite

dev-status:
	docker compose ps

dev-reset:
	@if [ "$(CONFIRM)" != "yes" ]; then \
		echo "ADVERTENCIA: dev-reset borra los datos locales de Mongo/Azurite (volumenes nombrados)."; \
		echo "Vuelve a correr con 'make dev-reset CONFIRM=yes' si estas seguro."; \
		exit 1; \
	fi
	docker compose down -v

test-integration: dev-up
	cd service && uv run pytest -m docker

# Reproducible Playwright E2E run: infra -> deterministic seed -> API+Vite in
# background -> wait for real readiness (not a fixed sleep) -> tests ->
# guaranteed cleanup via trap, even on failure/Ctrl-C. Unlike the `dev`
# target's `trap 'kill 0'` (fine there - `dev` is meant to run until
# manually interrupted), `kill 0` here would also signal the very shell
# running this trap, turning a clean pass/fail exit into a signal-based one
# and re-entering the trap - kill the captured PIDs specifically instead.
# `kill $$WEB_PID` alone isn't enough: pnpm forks vite as a grandchild that
# doesn't share that PID, so it survives as an orphan on 5173 - confirmed by
# hand (`ps`/`lsof -i :5173` after a run) - hence the `pkill -f` regex
# safety net matched against the *actual* command line (`node
# .../vite/bin/vite.js --port 5173`, not the literal "vite --port 5173").
# `dev-up`/`seed-reset`/`seed-dev` are the same targets a human runs
# locally - this just composes them non-interactively.
test-e2e: dev-up
	$(MAKE) seed-reset CONFIRM=yes
	$(MAKE) seed-dev
	@trap 'kill $$API_PID $$WEB_PID 2>/dev/null; \
		pkill -f "uvicorn.*procurawise.api.main:app.*--port 8000" 2>/dev/null; \
		pkill -f "vite.*--port 5173" 2>/dev/null; \
		$(MAKE) dev-down' EXIT INT TERM; \
	(cd service && uv run uvicorn procurawise.api.main:app --port 8000 > /tmp/procurawise-e2e-api.log 2>&1) & API_PID=$$!; \
	(cd apps/web && pnpm dev --port 5173 > /tmp/procurawise-e2e-web.log 2>&1) & WEB_PID=$$!; \
	echo "Esperando a que la API este lista..."; \
	i=0; until curl -sf http://localhost:8000/health/ready > /dev/null 2>&1; do \
		i=$$((i + 1)); \
		if [ $$i -ge 60 ]; then echo "La API no respondio a tiempo"; cat /tmp/procurawise-e2e-api.log; exit 1; fi; \
		sleep 1; \
	done; \
	echo "Esperando a que el frontend este listo..."; \
	i=0; until curl -sf http://localhost:5173/ > /dev/null 2>&1; do \
		i=$$((i + 1)); \
		if [ $$i -ge 60 ]; then echo "El frontend no respondio a tiempo"; cat /tmp/procurawise-e2e-web.log; exit 1; fi; \
		sleep 1; \
	done; \
	(cd apps/web && pnpm exec playwright test)
