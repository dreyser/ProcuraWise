.PHONY: dev test test-backend test-frontend lint lint-backend lint-frontend typecheck typecheck-backend typecheck-frontend contracts migrate dev-up dev-down dev-logs dev-status dev-reset test-integration

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
