# ProcuraWise

SaaS B2B multi-tenant que convierte una necesidad de compra de software/tecnología en un proceso RFP riguroso, con IA que asiste pero nunca decide.

## Estado del proyecto

**Fase 1 — Fundación técnica: completa** (2026-07-18). El vertical slice de negocio (`VS-2A`/`VS-2B`/`VS-2C`: `identity`, `evaluations`, `proposals`, `scoring`, `vendor_portal`), `AUTH-PROD` (auth productiva de comprador — email+password + OIDC Microsoft/Google), Fase 8 (E3 — `audit`, `AuditEvent` append-only) y Fase 9 (E3 — RBAC completo + `Assignment` por sección) están completos y fusionados a `main` (PR #21 y PR #22 respectivamente). Ver [`docs/development/current-phase.md`](docs/development/current-phase.md) para el detalle de cada fase y [`docs/development/backlog.md`](docs/development/backlog.md) para el estado de todas las fases del MVP.

## Cómo correr el proyecto localmente

Requiere `uv`, `pnpm` y Docker instalados (ver `docs/development/current-phase.md` si faltan).

```
make dev-up          # levanta Mongo + Azurite vía Docker Compose (idempotente)
make dev             # levanta la API (http://localhost:8000) y el frontend (http://localhost:5173)
make test            # unit + integration sin Docker (backend) y tests de frontend
make test-integration  # levanta dependencias y corre las pruebas que sí requieren Mongo/Azurite
make lint            # ruff + mypy + eslint + prettier
make typecheck       # mypy + tsc
make contracts       # regenera apps/web/src/api/client.ts desde el openapi.json de la API
make migrate         # aplica migraciones pendientes de Mongo (no-op hasta que exista la primera)
make dev-down        # baja Mongo + Azurite (conserva los datos en volúmenes nombrados)
make dev-status       # muestra el estado de los contenedores locales
make dev-logs         # sigue los logs de Mongo + Azurite
make dev-reset CONFIRM=yes  # baja los contenedores y BORRA los datos locales (irreversible)
```

Con `make dev-up` arriba, `curl http://localhost:8000/health/ready` debe responder 200 con `{"status":"ok","checks":{"mongodb":true,"storage":true}}`.

## Integración continua

Cada pull request contra `main` (y cada push a `main`) dispara 3 workflows en `.github/workflows/`, todos con permisos mínimos (`contents: read`) y sin secretos:

- **`ci.yml`** — jobs `backend` (ruff, mypy, `pytest -m "not docker"` con cobertura), `frontend` (ESLint, Prettier, `tsc`, Vitest, build de producción) y `contracts` (regenera `openapi.json`/`apps/web/src/api/client.ts` y falla si queda desactualizado respecto a lo comiteado — ver [ADR 0007](docs/architecture/decisions/0007-contratos-openapi-orval.md)).
- **`integration.yml`** — levanta Mongo + Azurite reales vía `make test-integration` y corre las 5 pruebas marcadas `docker`; los contenedores se detienen siempre, incluso si las pruebas fallan.
- **`security.yml`** — `gitleaks` (secret scanning, bloqueante) + `pip-audit`/`pnpm audit` (dependencias, informativo por ahora — ver [`docs/security/threat-model.md`](docs/security/threat-model.md)).

Todos reutilizan exactamente los mismos comandos `make`/`pnpm` que se corren en local — no hay lógica duplicada entre CI y desarrollo local. `Dependabot` (`.github/dependabot.yml`) abre PRs semanales de actualización para `pip`, `npm` y las propias GitHub Actions (pinneadas por SHA completo).

## Organización del repositorio

```
apps/web/          # frontend React + TypeScript (Vite)
service/            # backend Python: paquete procurawise (api/ + worker/ + shared/)
docs/
  requirements/    # especificación de producto original (fuente, no se edita)
  planning/        # plan aprobado del MVP (fuente de verdad de decisiones)
  product/         # alcance y roadmap
  development/     # backlog, fase actual, handoff entre sesiones
  architecture/    # arquitectura y ADRs (decisiones que no se reabren sin ADR nuevo)
  security/        # modelo de amenazas
  operations/      # despliegue e infraestructura
docker-compose.yml  # Mongo + Azurite locales (make dev-up)
Makefile            # make dev/test/lint/typecheck/contracts/migrate/dev-up/dev-down/...
.github/            # workflows de CI (ci.yml, integration.yml, security.yml) + Dependabot
CLAUDE.md           # reglas operativas para trabajar en este repositorio
```

Los subpaquetes de dominio bajo `service/procurawise/` (`identity`, `evaluations`, `proposals`, `scoring`, `vendor_portal`, `audit`, ...) siguen todos el mismo patrón interno (`models/schemas/repository/service/router`) — ver [`docs/architecture/architecture.md`](docs/architecture/architecture.md). Pre-commit hooks locales quedaron explícitamente fuera de alcance (CI ya cubre lint/format/typecheck en cada PR vía branch protection).

## Por dónde empezar

- **Para entender el producto:** [`docs/product/mvp-scope.md`](docs/product/mvp-scope.md).
- **Para entender la arquitectura:** [`docs/architecture/architecture.md`](docs/architecture/architecture.md) y [`docs/architecture/decisions/`](docs/architecture/decisions/).
- **Para saber qué se está trabajando ahora:** [`docs/development/current-phase.md`](docs/development/current-phase.md).
- **Reglas operativas para Claude Code:** [`CLAUDE.md`](CLAUDE.md).
