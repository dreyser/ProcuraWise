# Fase actual

## Fase 1 — Fundación técnica

**Estado: In Progress — sub-fase 0 (Bootstrap) parcialmente completada**

> Este documento se actualiza al cierre de cada sesión de Claude Code. Es, junto con `session-handoff.md`, el único mecanismo de continuidad entre sesiones sin memoria compartida.
>
> **Nota de numeración:** "Fase 1 — Fundación técnica" (este encabezado) es una fase de proyecto de alto nivel; equivale al **Bloque 0 — Fundación** del roadmap y a la épica **E1** de `backlog.md`. Internamente se divide en tres sub-fases técnicas numeradas 0, 1 y 2 (ver tabla E1 en [`docs/development/backlog.md`](backlog.md)).
>
> **Sub-división de la sub-fase 0 (Bootstrap):** la sesión del 2026-07-17 partió "Fase 0" en dos cortes más pequeños para reducir riesgo:
> - **Fase 1A — Estructura y herramientas** (✅ completada 2026-07-17): `apps/web` y `service/` ejecutables, con lint/format/typecheck/tests funcionando vía `Makefile`. Sin infraestructura local, sin CI, sin subpaquetes de dominio.
> - **Fase 1B — Infraestructura local y automatización** (pendiente, próxima sesión): `docker-compose.yml` (Mongo, Azurite, Redis, Mailhog), pre-commit, CI (`lint.yml`, `test.yml`), y los 15 subpaquetes vacíos de bounded contexts en `service/procurawise/`.
>
> Después de 1B viene la sub-fase **Fase 1 — `identity`** tal como la describe la tabla E1 de `backlog.md` (el número "1" ahí es el de la sub-fase técnica, no el de este encabezado de bloque).

## Objetivo

Dejar el repositorio en un estado ejecutable y verificable (Bloque 0: Fases 0-2) donde cualquier sesión futura de Claude Code pueda arrancar sin fricción: bootstrap del entorno local, aislamiento multi-tenant estructural (`identity`), y autenticación básica funcionando.

## Alcance

- **Fase 1A — Estructura y herramientas (✅ completada):** `service/pyproject.toml` (uv) con paquete `procurawise` (`shared/config.py`, `api/main.py` con `/health`, `worker/main.py`); `apps/web` Vite+React+TS con página mínima que consulta `/health`; ESLint+Prettier (frontend) y Ruff+mypy (backend); Vitest+RTL y pytest; `Makefile` con `make dev/test/lint/typecheck/contracts`; pipeline OpenAPI→orval mínimo. Sin Docker, sin Mongo, sin CI, sin bounded contexts de dominio, sin Tailwind/shadcn, sin pre-commit. Detalle completo en el plan de sesión y en la entrada correspondiente de `session-handoff.md`.
- **Fase 1B — Infraestructura local y automatización (pendiente):** `docker-compose.yml` (Mongo, Azurite, Redis, Mailhog); subpaquetes vacíos (`__init__.py`) para los 15 bounded contexts; pre-commit (ruff, mypy permisivo, eslint, prettier); CI (`lint.yml`, `test.yml`) corriendo contra un smoke test de `/health`; `make migrate` (cuando exista Mongo).
- **Fase 1 — `identity`**: Tenant/User/Membership + `TenantCollection` + middleware que extrae `tenant_id` del JWT.
- **Fase 2 — Auth local**: email+password + OIDC Microsoft/Google (authlib) + JWT propio + login/logout en frontend.

## Fuera de alcance

Cualquier lógica de dominio de negocio (evaluations, vendors, proposals, scoring, etc.), MFA, Azure real, IA, pagos, notificaciones reales, infraestructura Bicep, CI/CD de despliegue.

## Entregables

- ✅ Entorno local ejecutable sin Docker: `make dev` levanta API y web simultáneamente (Fase 1A).
- Entorno local reproducible con `docker compose up` (Fase 1B, pendiente).
- Esqueleto de los 15 bounded contexts en `service/procurawise/` (Fase 1B, pendiente).
- `identity` funcional con aislamiento de tenant probado (Fase 1, pendiente).
- Login funcional (local + OIDC) sin MFA (Fase 2, pendiente).

## Criterios de aceptación

- ✅ `make dev` levanta API y web simultáneamente (verificado manualmente el 2026-07-17).
- ✅ `GET /health` responde 200 con `{"status": "ok", "environment": "local"}`.
- `docker compose up` levanta Mongo, Azurite, Redis y Mailhog sin errores — pendiente (Fase 1B).
- CI queda verde en un PR vacío/inicial — pendiente (Fase 1B, no existe CI todavía).
- Crear tenant + usuario vía API funciona; test negativo confirma que un token de tenant A no puede leer datos de tenant B — pendiente (Fase 1).
- Login exitoso vía email+password y vía OIDC; el JWT emitido contiene el `tenant_id` correcto — pendiente (Fase 2).

## Pruebas requeridas

- ✅ Smoke test de `/health` (`service/tests/integration/test_health.py`) y test de `Settings` (`service/tests/unit/test_config.py`).
- ✅ Test mínimo de frontend (`apps/web/src/App.test.tsx`).
- Verificación de que `pre-commit` bloquea código mal formateado — pendiente (Fase 1B, no existe pre-commit todavía).
- `tests/security/test_tenant_isolation.py` (introducido en Fase 1, corre en cada PR desde entonces) — no aplica aún, `/health` no toca datos de negocio ni tenant.

## Decisiones pendientes de aprobación

- Arranque del engagement con el abogado externo para la revisión de web-grounding, antes de iniciar la Fase 1 (workstream paralelo del founder, no bloquea el desarrollo — ver nota transversal en `docs/product/roadmap.md`).

## Condiciones para iniciar Fase 1B

1. Este plan (`docs/planning/approved-mvp-plan.md`) aprobado en su totalidad — ✅ cumplido (2026-07-16).
2. Fase 1A completada y verificada — ✅ cumplido (2026-07-17).
3. Ninguna otra dependencia técnica pendiente: no hay gaps bloqueantes registrados en `docs/product/mvp-scope.md`.

## Último commit relevante

`d740972 docs: establish ProcuraWise MVP plan and architecture`, rama `phase-1/foundation`. **Corrección respecto a versiones anteriores de este documento:** el repositorio ya tenía `.git` inicializado y este commit ya existía al comenzar la sesión de Fase 1A (2026-07-17) — la afirmación previa de que "`git init` se inicializaría en la Fase 0" estaba desactualizada. Los archivos de Fase 1A (`apps/web/`, `service/`, `Makefile`, `.env.example`, `.gitignore`) quedaron creados en el working tree; el commit de esos cambios queda a criterio explícito del founder en la sesión correspondiente.

## Próximos pasos

Abrir una nueva sesión de Claude Code con instrucción explícita de ejecutar la **Fase 1B (Infraestructura local y automatización)**: `docker-compose.yml`, pre-commit, CI, y los 15 subpaquetes vacíos de bounded contexts — ver sección "Alcance" de este documento. No repetir el trabajo de Fase 1A (ya completado y verificado).

## Bloqueos

Ninguno.
