# ProcuraWise

SaaS B2B multi-tenant que convierte una necesidad de compra de software/tecnología en un proceso RFP riguroso, con IA que asiste pero nunca decide.

## Estado del proyecto

Fase 1A (Estructura y herramientas) completada el 2026-07-17: `apps/web` (React+TS+Vite) y `service/` (FastAPI+worker sobre el paquete compartido `procurawise`) arrancan localmente y pasan `make test/lint/typecheck`. Sin Docker, sin Mongo, sin CI y sin lógica de dominio todavía — ver [`docs/development/current-phase.md`](docs/development/current-phase.md) para el alcance exacto y la próxima sub-fase (1B).

## Cómo correr el proyecto localmente

Requiere `uv` y `pnpm` instalados (ver `docs/development/current-phase.md` si faltan).

```
make dev         # levanta la API (http://localhost:8000) y el frontend (http://localhost:5173)
make test        # unit + integration (backend) y tests de frontend
make lint        # ruff + mypy + eslint + prettier
make typecheck   # mypy + tsc
make contracts   # regenera apps/web/src/api/client.ts desde el openapi.json de la API
```

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
Makefile           # make dev/test/lint/typecheck/contracts
CLAUDE.md          # reglas operativas para trabajar en este repositorio
```

Infraestructura local (Docker Compose para Mongo/Azurite/Redis/Mailhog), CI y los subpaquetes de dominio (`identity`, `evaluations`, ...) llegan en la Fase 1B, según lo descrito en [`docs/architecture/architecture.md`](docs/architecture/architecture.md).

## Por dónde empezar

- **Para entender el producto:** [`docs/product/mvp-scope.md`](docs/product/mvp-scope.md).
- **Para entender la arquitectura:** [`docs/architecture/architecture.md`](docs/architecture/architecture.md) y [`docs/architecture/decisions/`](docs/architecture/decisions/).
- **Para saber qué se está trabajando ahora:** [`docs/development/current-phase.md`](docs/development/current-phase.md).
- **Reglas operativas para Claude Code:** [`CLAUDE.md`](CLAUDE.md).
