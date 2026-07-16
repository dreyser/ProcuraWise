# Fase actual

## Fase 1 — Fundación técnica

**Estado: Planned — Not Started**

> Este documento se actualiza al cierre de cada sesión de Claude Code. Es, junto con `session-handoff.md`, el único mecanismo de continuidad entre sesiones sin memoria compartida.
>
> **Nota de numeración:** "Fase 1 — Fundación técnica" (este encabezado) es una fase de proyecto de alto nivel; equivale al **Bloque 0 — Fundación** del roadmap y a la épica **E1** de `backlog.md`. Internamente se divide en tres sub-fases técnicas numeradas 0, 1 y 2 (ver tabla E1 en [`docs/development/backlog.md`](backlog.md)). La sesión que debe abrirse a continuación es la **sub-fase Fase 0 (Bootstrap)** — su alcance exacto está en la sección "Alcance" de este documento y en la fila "Fase 0" de la tabla E1.

## Objetivo

Dejar el repositorio en un estado ejecutable y verificable (Bloque 0: Fases 0-2) donde cualquier sesión futura de Claude Code pueda arrancar sin fricción: bootstrap del entorno local, aislamiento multi-tenant estructural (`identity`), y autenticación básica funcionando.

## Alcance

- **Fase 0 — Bootstrap**: `docker-compose.yml` (Mongo, Azurite, Redis, Mailhog); `service/pyproject.toml` (uv) con subpaquetes vacíos (`__init__.py`) para los 15 bounded contexts; FastAPI `main.py` con `/health`; `apps/web` Vite+React+TS hello-world con cliente apuntando a `/health`; pre-commit (ruff, mypy permisivo, eslint, prettier); CI (`lint.yml`, `test.yml`) corriendo contra un smoke test de `/health`; `Makefile` con `make dev/test/lint`; `git init` + primer commit (a confirmar explícitamente al inicio de esa sesión).
- **Fase 1 — `identity`**: Tenant/User/Membership + `TenantCollection` + middleware que extrae `tenant_id` del JWT.
- **Fase 2 — Auth local**: email+password + OIDC Microsoft/Google (authlib) + JWT propio + login/logout en frontend.

## Fuera de alcance

Cualquier lógica de dominio de negocio (evaluations, vendors, proposals, scoring, etc.), MFA, Azure real, IA, pagos, notificaciones reales, infraestructura Bicep, CI/CD de despliegue.

## Entregables

- Entorno local reproducible (`docker compose up` + `make dev`).
- Esqueleto de los 15 bounded contexts en `service/procurawise/`.
- `identity` funcional con aislamiento de tenant probado.
- Login funcional (local + OIDC) sin MFA.

## Criterios de aceptación

- `docker compose up` levanta Mongo, Azurite, Redis y Mailhog sin errores.
- `make dev` levanta API y web simultáneamente.
- `GET /health` responde 200.
- CI queda verde en un PR vacío/inicial.
- Crear tenant + usuario vía API funciona; test negativo confirma que un token de tenant A no puede leer datos de tenant B.
- Login exitoso vía email+password y vía OIDC; el JWT emitido contiene el `tenant_id` correcto.

## Pruebas requeridas

- Smoke test de `/health`.
- Verificación de que `pre-commit` bloquea código mal formateado.
- `tests/security/test_tenant_isolation.py` (introducido en Fase 1, corre en cada PR desde entonces).

## Decisiones pendientes de aprobación

- Confirmación explícita del founder para ejecutar `git init` + primer commit al inicio de la sesión de Fase 0 (el repositorio no tiene `.git` todavía).
- Arranque del engagement con el abogado externo para la revisión de web-grounding, antes de iniciar la Fase 1 (workstream paralelo del founder, no bloquea el desarrollo — ver nota transversal en `docs/product/roadmap.md`).

## Condiciones para iniciar

1. Este plan (`docs/planning/approved-mvp-plan.md`) aprobado en su totalidad — ✅ cumplido (2026-07-16).
2. Confirmación explícita de `git init` al inicio de la sesión de Fase 0 — pendiente, se solicita en esa misma sesión.
3. Ninguna otra dependencia técnica pendiente: no hay gaps bloqueantes registrados en `docs/product/mvp-scope.md`.

## Último commit relevante

Ninguno — el repositorio no tiene `.git` todavía. Se inicializará en la Fase 0.

## Próximos pasos

Abrir una nueva sesión de Claude Code con instrucción explícita de ejecutar la Fase 0 según el alcance de esta ficha y de `docs/development/backlog.md` (tabla E1, fila "Fase 0"). Confirmar `git init` al inicio de esa sesión.

## Bloqueos

Ninguno.
