.PHONY: dev test lint typecheck contracts

dev:
	@trap 'kill 0' EXIT INT TERM; \
	(cd service && uv run uvicorn procurawise.api.main:app --reload --port 8000) & \
	(cd apps/web && pnpm dev) & \
	wait

test:
	cd service && uv run pytest
	cd apps/web && pnpm test

lint:
	cd service && uv run ruff check . && uv run ruff format --check .
	cd apps/web && pnpm lint && pnpm format

typecheck:
	cd service && uv run mypy procurawise
	cd apps/web && pnpm typecheck

contracts:
	cd service && uv run python -m procurawise.api.export_openapi
	cd apps/web && pnpm contracts
