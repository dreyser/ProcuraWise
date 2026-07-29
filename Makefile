# Pin bash explicitly so every recipe runs under the same shell locally
# (macOS's /bin/sh is bash-derived) and in CI (ubuntu-latest's /bin/sh is
# dash) - keeps behavior consistent even though, per the note on test-e2e
# below, dash alone wasn't the cause of the segfault seen there.
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
# guaranteed cleanup, even on failure/Ctrl-C. The cleanup/wait/run logic
# lives in scripts/test-e2e.sh, not inline here - a previous inline version
# (single `trap '...' EXIT INT TERM` one-liner, backslash-continued across
# the whole recipe, calling `$(MAKE) dev-down` recursively from *inside*
# the trap) segfaulted in CI (GitHub Actions ubuntu-latest) right after both
# specs printed "passed", during that trap's cleanup - never reproduced
# locally. Pinning SHELL to bash (above) didn't fix it, which rules out a
# plain dash-vs-bash difference and points at the recursive-make-inside-a-
# trap nesting itself. Extracting to a real script removes that nesting
# (calls `docker compose down` directly, not through `make`) and is
# independently testable/shellcheck-able, unlike an inline Make recipe
# string. `dev-up`/`seed-reset`/`seed-dev` stay here since a human runs
# those same targets locally too - only the fragile part moved out.
test-e2e: dev-up
	$(MAKE) seed-reset CONFIRM=yes
	$(MAKE) seed-dev
	bash scripts/test-e2e.sh
