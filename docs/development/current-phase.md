# Fase actual

## Fase 1 — Fundación técnica

**Estado: In Progress — sub-fase 0 (Bootstrap) parcialmente completada**

> Este documento se actualiza al cierre de cada sesión de Claude Code. Es, junto con `session-handoff.md`, el único mecanismo de continuidad entre sesiones sin memoria compartida.
>
> **Nota de numeración:** "Fase 1 — Fundación técnica" (este encabezado) es una fase de proyecto de alto nivel; equivale al **Bloque 0 — Fundación** del roadmap y a la épica **E1** de `backlog.md`. Internamente se divide en tres sub-fases técnicas numeradas 0, 1 y 2 (ver tabla E1 en [`docs/development/backlog.md`](backlog.md)).
>
> **Sub-división de la sub-fase 0 (Bootstrap):** la sesión del 2026-07-17 partió "Fase 0" en dos cortes más pequeños para reducir riesgo (1A/1B). Al planear la Fase 1B, esa misma sesión encontró que su alcance original (infra local + pre-commit + CI + 15 bounded contexts) seguía siendo demasiado grande para una sola sesión, y la volvió a acotar:
> - **Fase 1A — Estructura y herramientas** (✅ completada 2026-07-17): `apps/web` y `service/` ejecutables, con lint/format/typecheck/tests funcionando vía `Makefile`. Sin infraestructura local, sin CI, sin subpaquetes de dominio.
> - **Fase 1B — Infraestructura local de desarrollo** (✅ **Completed** 2026-07-17): `docker-compose.yml` (Mongo, Azurite — sin Redis/Mailhog, ver [ADR 0020](../architecture/decisions/0020-composicion-servicios-desarrollo-local.md)), configuración tipada por ambiente, adaptadores de Mongo/Blob/cola (`InMemoryMessageBus`), health checks (`/health/live`, `/health/ready`), logging estructurado, `make migrate` (scaffold sin migraciones reales), pruebas de integración. Verificación con Docker real completada por el founder en su Mac — ver historial de verificación abajo. Sin CI, sin pre-commit, sin bounded contexts de dominio (diferido a Fase 1C).
>
> **Historial de verificación de Fase 1B:**
> 1. **Sesión de implementación (2026-07-17, sin Docker disponible):** verificó todo lo que no requiere Docker (`make lint`, `make typecheck`, `make test`). No pudo correr `make dev-up`/`make test-integration`.
> 2. **Validación manual del founder en macOS con Docker (2026-07-17, ronda 1):** `make test-integration` → Mongo: 2/2 PASS. Blob Storage: 2/2 ERROR + `/health/ready` con dependencias arriba: FAIL (503). **Causa confirmada:** `azure-storage-blob` 12.30.0 usa por defecto la versión REST `2026-06-06`, que Azurite 3.33.0 rechaza (`InvalidHeaderValue: The API version 2026-06-06 is not supported by Azurite`). Mongo no tuvo ningún problema.
> 3. **Fix aplicado (2026-07-17, sesión sin Docker):** se fijó `AZURE_STORAGE_API_VERSION=2025-01-05` (versión verificada compatible con Azurite 3.33.0 y con Azure Storage real) como campo tipado de `Settings`, pasado explícitamente a `BlobServiceClient`. Re-verificado todo lo que no requiere Docker (`make lint/typecheck/test/contracts`, +6 tests unitarios nuevos sobre `storage_api_version`).
> 4. **Validación manual del founder en macOS con Docker (2026-07-17, ronda 2 — ✅ EXITOSA):** `docker version`/`docker compose version` → PASS. `make dev-up` → PASS, Mongo + Azurite healthy (`docker compose ps`). `make test-integration` → **PASS, las 5 pruebas Docker pasaron** (Mongo roundtrip 2/2, Blob Storage roundtrip 2/2, `/health/ready` con dependencias arriba → HTTP 200). `make lint`/`make typecheck` → PASS. `make test` → PASS, 19 passed + 5 pruebas Docker correctamente excluidas de la suite unitaria. `make contracts` → PASS. `make dev-down` → PASS, sin contenedores activos después. **`AZURE_STORAGE_API_VERSION=2025-01-05` confirmado como la solución.** **Fase 1B queda cerrada con estado Completed.**
> - **Fase 1C — Automatización y esqueleto de dominio** (**Planned / Not Started** — no ha comenzado ningún trabajo de esta sub-fase): pre-commit (ruff, mypy permisivo, eslint, prettier), CI (`lint.yml`, `test.yml`), y los 15 subpaquetes vacíos de bounded contexts en `service/procurawise/`.
>
> Después de 1C viene la sub-fase **Fase 1 — `identity`** tal como la describe la tabla E1 de `backlog.md` (el número "1" ahí es el de la sub-fase técnica, no el de este encabezado de bloque).

## Objetivo

Dejar el repositorio en un estado ejecutable y verificable (Bloque 0: Fases 0-2) donde cualquier sesión futura de Claude Code pueda arrancar sin fricción: bootstrap del entorno local, aislamiento multi-tenant estructural (`identity`), y autenticación básica funcionando.

## Alcance

- **Fase 1A — Estructura y herramientas (✅ completada):** `service/pyproject.toml` (uv) con paquete `procurawise` (`shared/config.py`, `api/main.py` con `/health`, `worker/main.py`); `apps/web` Vite+React+TS con página mínima que consulta `/health`; ESLint+Prettier (frontend) y Ruff+mypy (backend); Vitest+RTL y pytest; `Makefile` con `make dev/test/lint/typecheck/contracts`; pipeline OpenAPI→orval mínimo. Sin Docker, sin Mongo, sin CI, sin bounded contexts de dominio, sin Tailwind/shadcn, sin pre-commit. Detalle completo en el plan de sesión y en la entrada correspondiente de `session-handoff.md`.
- **Fase 1B — Infraestructura local de desarrollo (✅ Completed, verificada con Docker real):** `docker-compose.yml` con Mongo Community + Azurite (Blob), volúmenes nombrados, healthchecks, versiones pineadas; `Settings` tipada ampliada (Mongo/Storage/cola, valida `queue_backend=memory` prohibido en `production`; `storage_api_version` fijada a `2025-01-05` vía `AZURE_STORAGE_API_VERSION`, ver historial de verificación arriba); `shared/mongo.py`, `shared/storage.py` (`BlobStorage` Protocol + `AzureBlobStorage`, `api_version` explícito propagado a los clientes de servicio/contenedor/blob), `shared/messaging.py` (`MessageBus` Protocol + `InMemoryMessageBus`, default local — ver [ADR 0020](../architecture/decisions/0020-composicion-servicios-desarrollo-local.md)); `GET /health/live` y `GET /health/ready` (reemplazan el `/health` plano de 1A); logging estructurado JSON (`shared/logging.py`, sin secretos); `shared/migrations.py` + `service/migrations/` (scaffold idempotente, sin migraciones de dominio reales); `make dev-up/down/logs/status/reset`, `make test-integration`, `make migrate`. Sin CI, sin pre-commit, sin bounded contexts de dominio.
- **Fase 1C — Automatización y esqueleto de dominio (Planned / Not Started):** subpaquetes vacíos (`__init__.py`) para los 15 bounded contexts; pre-commit (ruff, mypy permisivo, eslint, prettier); CI (`lint.yml`, `test.yml`) corriendo contra `make lint`/`make test` (sin Docker) y, si aplica, `make test-integration` en un runner con Docker disponible. **No ha comenzado ningún trabajo de esta sub-fase.**
- **Fase 1 — `identity`**: Tenant/User/Membership + `TenantCollection` + middleware que extrae `tenant_id` del JWT.
- **Fase 2 — Auth local**: email+password + OIDC Microsoft/Google (authlib) + JWT propio + login/logout en frontend.

## Fuera de alcance

Cualquier lógica de dominio de negocio (evaluations, vendors, proposals, scoring, etc.), MFA, Azure real, IA, pagos, notificaciones reales, infraestructura Bicep, CI/CD de despliegue, Redis, Mailhog, Service Bus Emulator (documentado para el futuro, no implementado).

## Entregables

- ✅ Entorno local ejecutable sin Docker: `make dev` levanta API y web simultáneamente (Fase 1A).
- ✅ Entorno local reproducible con `make dev-up` (Mongo + Azurite vía Docker Compose) — verificado con Docker real por el founder, ambos servicios healthy (Fase 1B).
- ✅ Configuración tipada por ambiente, health checks de dependencias, logging estructurado, `make migrate` (scaffold) — verificado (Fase 1B).
- Esqueleto de los 15 bounded contexts, pre-commit y CI (Fase 1C, Planned / Not Started).
- `identity` funcional con aislamiento de tenant probado (Fase 1, pendiente).
- Login funcional (local + OIDC) sin MFA (Fase 2, pendiente).

## Criterios de aceptación

- ✅ `make dev` levanta API y web simultáneamente (verificado manualmente en Fase 1A).
- ✅ `make dev-up` levanta Mongo y Azurite sin errores, de forma idempotente — verificado con Docker real (`docker compose ps` → ambos `healthy`).
- ✅ `GET /health/live` responde 200 sin depender de Mongo/Azurite — verificado. ✅ `GET /health/ready` responde 503 si Mongo está caído, sin exponer connection strings — verificado sin Docker. ✅ `GET /health/ready` responde 200 con Mongo+Azurite realmente arriba — verificado con Docker real (HTTP 200).
- ✅ `make test` (sin Docker) en verde: 19 passed, 5 deselected (`docker`). ✅ `make test-integration` (con Docker) en verde: 5/5 pruebas Docker pasaron (Mongo roundtrip 2/2, Blob Storage roundtrip 2/2, `/health/ready` con dependencias arriba).
- ✅ `make migrate` — scaffold idempotente, no-op sin migraciones de dominio todavía; código y tipado verificados (`mypy`/`ruff`); ejecución contra Mongo real confirmada indirectamente por el roundtrip de `test_mongo_client.py` en la misma sesión de Docker.
- ✅ `make dev-down` limpia los contenedores correctamente — verificado (`docker compose ps` sin contenedores activos después).
- CI queda verde en un PR vacío/inicial — pendiente (Fase 1C, Planned / Not Started, no existe CI todavía).
- Crear tenant + usuario vía API funciona; test negativo confirma que un token de tenant A no puede leer datos de tenant B — pendiente (Fase 1).
- Login exitoso vía email+password y vía OIDC; el JWT emitido contiene el `tenant_id` correcto — pendiente (Fase 2).

**Ningún criterio de aceptación de Fase 1B queda pendiente.**

## Pruebas requeridas

- ✅ `/health/live`, `/health/ready` (caso dependencia caída, sin Docker) y test de `Settings` (`service/tests/unit/`) — verificado, `make test` en verde (19 passed).
- ✅ `storage_api_version` (default `2025-01-05`, override vía `AZURE_STORAGE_API_VERSION`, propagación a `BlobServiceClient`/`ContainerClient`/`BlobClient`, error sin fuga de connection string) — `service/tests/unit/test_storage.py` + casos en `test_config.py`, verificado sin Docker.
- ✅ Pruebas con Docker (`service/tests/integration/`, marcadas `@pytest.mark.docker`): roundtrip Mongo, roundtrip Blob (Azurite), `/health/ready` con ambas dependencias arriba — **las 5 pasaron** en la validación del founder con Docker real (`make test-integration`).
- ✅ `InMemoryMessageBus` publish/consume, formato de logging JSON, ausencia de secretos en logs (`service/tests/unit/`) — verificado.
- ✅ Test mínimo de frontend (`apps/web/src/App.test.tsx`).
- Verificación de que `pre-commit` bloquea código mal formateado — pendiente (Fase 1C, Planned / Not Started, no existe pre-commit todavía).
- `tests/security/test_tenant_isolation.py` (introducido en Fase 1, corre en cada PR desde entonces) — no aplica aún, no hay datos de negocio ni tenant todavía.

## Decisiones pendientes de aprobación

- Arranque del engagement con el abogado externo para la revisión de web-grounding, antes de iniciar la Fase 1 (workstream paralelo del founder, no bloquea el desarrollo — ver nota transversal en `docs/product/roadmap.md`).

## Condiciones para iniciar Fase 1C

1. Este plan (`docs/planning/approved-mvp-plan.md`) aprobado en su totalidad — ✅ cumplido (2026-07-16).
2. Fase 1A completada y verificada — ✅ cumplido (2026-07-17).
3. Fase 1B completada y verificada, incluyendo Docker real — ✅ cumplido (2026-07-17). `make dev-up`, `make test-integration` (5/5 PASS) y `make dev-down` confirmados por el founder en su Mac.
4. Ninguna otra dependencia técnica pendiente: no hay gaps bloqueantes registrados en `docs/product/mvp-scope.md`.

**Todas las condiciones para iniciar Fase 1C están cumplidas. Fase 1C sigue en estado Planned / Not Started — no se ha iniciado ningún trabajo de esa sub-fase en esta sesión ni en ninguna anterior.**

## Último commit relevante

`76543b7 build: establish ProcuraWise project foundation`, rama `phase-1/foundation` (incluye el trabajo de Fase 1A). Los archivos de Fase 1B (`docker-compose.yml`, módulos `shared/mongo.py`/`storage.py`/`messaging.py`/`health.py`/`logging.py`/`migrations.py`, routers de health, Makefile ampliado, ADR 0020, documentación actualizada) quedaron creados y verificados en el working tree; el commit de esos cambios queda a criterio explícito del founder (ver recomendación en `session-handoff.md`).

## Próximos pasos

1. **Founder:** decidir si comitea el resultado de Fase 1B (código completo y verificado, incluyendo Docker real) antes de abrir la siguiente sesión.
2. Abrir una nueva sesión de Claude Code con instrucción explícita de ejecutar la **Fase 1C (Automatización y esqueleto de dominio)**: pre-commit, CI (`lint.yml`, `test.yml`), y los 15 subpaquetes vacíos de bounded contexts — ver sección "Alcance" de este documento. No repetir el trabajo de Fase 1A/1B.

## Bloqueos

Ninguno.

## Deuda técnica no bloqueante

- **Advertencia de deprecación `StarletteDeprecationWarning`** al correr `service/tests/integration/test_health.py` (y otros tests que usan `fastapi.testclient.TestClient`): "Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead." No falla ningún test, no afecta comportamiento en runtime (solo aparece en la suite de tests). No bloquea Fase 1C. Revisar cuando FastAPI/Starlette publiquen una migración estable a `httpx2`, o al tocar de nuevo las dependencias de testing del backend.
