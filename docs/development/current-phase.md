# Fase actual

## Fase 1 — Fundación técnica

**Estado: ✅ Completed** (2026-07-18) — las 3 sub-fases técnicas (1A, 1B, 1C) están cerradas. Sigue la sub-fase `identity` (ver tabla E1 de `backlog.md`).

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
> - **Fase 1C — Integración continua y seguridad de pipeline** (✅ **Completed** 2026-07-18): al planear esta sub-fase se redefinió su alcance — la sesión de planeación encontró que la definición original (pre-commit + CI + 15 subpaquetes de bounded contexts) mezclaba automatización de pipeline con esqueleto de dominio sin necesidad, y el founder confirmó vía `AskUserQuestion` acotarla a **solo CI/CD + seguridad de pipeline**. Entregado: `.github/workflows/ci.yml` (jobs `backend`/`frontend`/`contracts`, reutilizando `make lint-backend/frontend`, `make typecheck-backend/frontend`, `make test-backend/frontend` — el `Makefile` se descompuso en targets granulares sin cambiar el comportamiento de `make lint/typecheck/test`), `.github/workflows/integration.yml` (`make test-integration` contra Mongo+Azurite reales, con `make dev-down` garantizado incluso si las pruebas fallan), `.github/workflows/security.yml` (`gitleaks` como secret scanning bloqueante, `pip-audit`+`pnpm audit` como dependency scanning informativo — repo privado sin GitHub Advanced Security, ver detalle en `threat-model.md`), `.github/dependabot.yml` (`pip`, `npm`, `github-actions`, todas las Actions pinneadas por SHA completo), `pytest-cov` con cobertura medida y mostrada (sin umbral global). **Pre-commit hooks locales y los 15 subpaquetes vacíos de bounded contexts se mueven fuera de Fase 1C** — se retoman al inicio de la sub-fase `identity`, junto con el primer código de dominio real, en vez de mantener una sub-fase separada solo para esqueleto vacío.
>
> Después de 1C viene la sub-fase **Fase 1 — `identity`** tal como la describe la tabla E1 de `backlog.md` (el número "1" ahí es el de la sub-fase técnica, no el de este encabezado de bloque).

## Objetivo

Dejar el repositorio en un estado ejecutable y verificable (Bloque 0: Fases 0-2) donde cualquier sesión futura de Claude Code pueda arrancar sin fricción: bootstrap del entorno local, aislamiento multi-tenant estructural (`identity`), y autenticación básica funcionando.

## Alcance

- **Fase 1A — Estructura y herramientas (✅ completada):** `service/pyproject.toml` (uv) con paquete `procurawise` (`shared/config.py`, `api/main.py` con `/health`, `worker/main.py`); `apps/web` Vite+React+TS con página mínima que consulta `/health`; ESLint+Prettier (frontend) y Ruff+mypy (backend); Vitest+RTL y pytest; `Makefile` con `make dev/test/lint/typecheck/contracts`; pipeline OpenAPI→orval mínimo. Sin Docker, sin Mongo, sin CI, sin bounded contexts de dominio, sin Tailwind/shadcn, sin pre-commit. Detalle completo en el plan de sesión y en la entrada correspondiente de `session-handoff.md`.
- **Fase 1B — Infraestructura local de desarrollo (✅ Completed, verificada con Docker real):** `docker-compose.yml` con Mongo Community + Azurite (Blob), volúmenes nombrados, healthchecks, versiones pineadas; `Settings` tipada ampliada (Mongo/Storage/cola, valida `queue_backend=memory` prohibido en `production`; `storage_api_version` fijada a `2025-01-05` vía `AZURE_STORAGE_API_VERSION`, ver historial de verificación arriba); `shared/mongo.py`, `shared/storage.py` (`BlobStorage` Protocol + `AzureBlobStorage`, `api_version` explícito propagado a los clientes de servicio/contenedor/blob), `shared/messaging.py` (`MessageBus` Protocol + `InMemoryMessageBus`, default local — ver [ADR 0020](../architecture/decisions/0020-composicion-servicios-desarrollo-local.md)); `GET /health/live` y `GET /health/ready` (reemplazan el `/health` plano de 1A); logging estructurado JSON (`shared/logging.py`, sin secretos); `shared/migrations.py` + `service/migrations/` (scaffold idempotente, sin migraciones de dominio reales); `make dev-up/down/logs/status/reset`, `make test-integration`, `make migrate`. Sin CI, sin pre-commit, sin bounded contexts de dominio.
- **Fase 1C — Integración continua y seguridad de pipeline (✅ Completed, redefinida):** `.github/workflows/ci.yml` (backend/frontend/contracts), `.github/workflows/integration.yml` (Mongo+Azurite reales), `.github/workflows/security.yml` (secret + dependency scanning), `.github/dependabot.yml`, `.gitleaks.toml`, `Makefile` con targets granulares por lado, `pytest-cov`. Pre-commit y los 15 subpaquetes de bounded contexts **no forman parte de esta sub-fase** — se retoman en `identity`.
- **Fase 1 — `identity`**: Tenant/User/Membership + `TenantCollection` + middleware que extrae `tenant_id` del JWT.
- **Fase 2 — Auth local**: email+password + OIDC Microsoft/Google (authlib) + JWT propio + login/logout en frontend.

## Fuera de alcance

Cualquier lógica de dominio de negocio (evaluations, vendors, proposals, scoring, etc.), MFA, Azure real, IA, pagos, notificaciones reales, infraestructura Bicep, CI/CD de despliegue, Redis, Mailhog, Service Bus Emulator (documentado para el futuro, no implementado).

## Entregables

- ✅ Entorno local ejecutable sin Docker: `make dev` levanta API y web simultáneamente (Fase 1A).
- ✅ Entorno local reproducible con `make dev-up` (Mongo + Azurite vía Docker Compose) — verificado con Docker real por el founder, ambos servicios healthy (Fase 1B).
- ✅ Configuración tipada por ambiente, health checks de dependencias, logging estructurado, `make migrate` (scaffold) — verificado (Fase 1B).
- ✅ CI en GitHub Actions (`ci.yml`, `integration.yml`, `security.yml`), secret + dependency scanning, Dependabot — verificado localmente (`actionlint`, `gitleaks`, `pip-audit`, `pnpm audit`, `make lint/typecheck/test/contracts/test-integration`); verificación contra un run real en GitHub pendiente de que el founder autorice el push (Fase 1C).
- Esqueleto de los 15 bounded contexts, pre-commit hooks locales (Fase `identity`, pendiente).
- `identity` funcional con aislamiento de tenant probado (Fase 1, pendiente).
- Login funcional (local + OIDC) sin MFA (Fase 2, pendiente).

## Criterios de aceptación

- ✅ `make dev` levanta API y web simultáneamente (verificado manualmente en Fase 1A).
- ✅ `make dev-up` levanta Mongo y Azurite sin errores, de forma idempotente — verificado con Docker real (`docker compose ps` → ambos `healthy`).
- ✅ `GET /health/live` responde 200 sin depender de Mongo/Azurite — verificado. ✅ `GET /health/ready` responde 503 si Mongo está caído, sin exponer connection strings — verificado sin Docker. ✅ `GET /health/ready` responde 200 con Mongo+Azurite realmente arriba — verificado con Docker real (HTTP 200).
- ✅ `make test` (sin Docker) en verde: 19 passed, 5 deselected (`docker`). ✅ `make test-integration` (con Docker) en verde: 5/5 pruebas Docker pasaron (Mongo roundtrip 2/2, Blob Storage roundtrip 2/2, `/health/ready` con dependencias arriba).
- ✅ `make migrate` — scaffold idempotente, no-op sin migraciones de dominio todavía; código y tipado verificados (`mypy`/`ruff`); ejecución contra Mongo real confirmada indirectamente por el roundtrip de `test_mongo_client.py` en la misma sesión de Docker.
- ✅ `make dev-down` limpia los contenedores correctamente — verificado (`docker compose ps` sin contenedores activos después).
- ✅ `ci.yml`/`integration.yml`/`security.yml` sintácticamente válidos (`actionlint` en verde) y reproducen exactamente `make lint`/`make typecheck`/`make test`/`make contracts`/`make test-integration` — verificado localmente. **Pendiente:** confirmar en un PR real de GitHub (los 5 checks bloqueantes en verde) una vez el founder autorice el primer push de esta sub-fase — ver "Próximos pasos".
- ✅ `security / secret-scan` (`gitleaks` + `.gitleaks.toml`) corrido localmente contra el repo completo: cero hallazgos, con y sin el allowlist (las reglas default no marcan `UseDevelopmentStorage=true` ni la clave pública de Azurite, el allowlist queda como protección documentada a futuro).
- ✅ `security / python-deps` (`pip-audit`) y `security / frontend-deps` (`pnpm audit`) corridos localmente — `pip-audit`: sin hallazgos; `pnpm audit`: 3 hallazgos transitivos en la cadena de dependencias de `orval` (herramienta de build, no código de producción), confirman que la política "informativo, no bloqueante" definida para esta fase es la correcta.
- Crear tenant + usuario vía API funciona; test negativo confirma que un token de tenant A no puede leer datos de tenant B — pendiente (Fase 1).
- Login exitoso vía email+password y vía OIDC; el JWT emitido contiene el `tenant_id` correcto — pendiente (Fase 2).

**Ningún criterio de aceptación de Fase 1B o Fase 1C queda pendiente de implementación** (la única verificación pendiente de Fase 1C es correrla contra GitHub real, fuera del alcance de esta sesión hasta que el founder autorice el push — ver "Próximos pasos").

## Pruebas requeridas

- ✅ `/health/live`, `/health/ready` (caso dependencia caída, sin Docker) y test de `Settings` (`service/tests/unit/`) — verificado, `make test` en verde (19 passed).
- ✅ `storage_api_version` (default `2025-01-05`, override vía `AZURE_STORAGE_API_VERSION`, propagación a `BlobServiceClient`/`ContainerClient`/`BlobClient`, error sin fuga de connection string) — `service/tests/unit/test_storage.py` + casos en `test_config.py`, verificado sin Docker.
- ✅ Pruebas con Docker (`service/tests/integration/`, marcadas `@pytest.mark.docker`): roundtrip Mongo, roundtrip Blob (Azurite), `/health/ready` con ambas dependencias arriba — **las 5 pasaron** en la validación del founder con Docker real (`make test-integration`).
- ✅ `InMemoryMessageBus` publish/consume, formato de logging JSON, ausencia de secretos en logs (`service/tests/unit/`) — verificado.
- ✅ Test mínimo de frontend (`apps/web/src/App.test.tsx`).
- ✅ Cobertura medida (`pytest-cov`, `--cov-report=term-missing`/`xml`, sin umbral global — ver justificación en el plan de Fase 1C) — 19 tests, 64-65% sobre `procurawise` (esperable sin lógica de dominio todavía).
- Verificación de que `pre-commit` bloquea código mal formateado — pendiente (sub-fase `identity`, no existe pre-commit todavía; movido fuera de Fase 1C, ver nota de redefinición arriba).
- `tests/security/test_tenant_isolation.py` (introducido en Fase 1, corre en cada PR desde entonces) — no aplica aún, no hay datos de negocio ni tenant todavía.

## Decisiones pendientes de aprobación

- Arranque del engagement con el abogado externo para la revisión de web-grounding, antes de iniciar la Fase 1 (workstream paralelo del founder, no bloquea el desarrollo — ver nota transversal en `docs/product/roadmap.md`).

## Cierre de Fase 1C (redefinida) y de Fase 1 — Fundación técnica

1. Plan de Fase 1C planeado en Plan Mode y aprobado por el founder (2026-07-18), incluyendo 2 preguntas bloqueantes resueltas vía `AskUserQuestion` (alcance redefinido a CI/CD + seguridad de pipeline; repo asumido privado sin GHAS) — ✅ cumplido.
2. Implementación completa: `Makefile` con targets granulares, `pytest-cov`, `apps/web/package.json` con `packageManager`/`engines` pinneados, `.github/workflows/{ci,integration,security}.yml`, `.gitleaks.toml`, `.github/dependabot.yml`, Actions pinneadas por SHA completo (verificadas contra la API de GitHub, no inventadas) — ✅ cumplido.
3. Validación local completa (sin Docker: `make lint`, `make typecheck`, `make test` con cobertura, `make contracts` sin diff; con Docker: `make test-integration` 5/5 PASS, `make dev-down` limpio; sintaxis: `actionlint` en verde; seguridad: `gitleaks detect` sin hallazgos, `pip-audit` sin hallazgos, `pnpm audit` con 3 hallazgos transitivos informativos en `orval`) — ✅ cumplido, ver detalle en "Criterios de aceptación".
4. Verificación contra runs reales de GitHub Actions — ✅ cumplido. Push inicial (`bfe6626`) reveló un bug real: `pnpm/action-setup` busca `packageManager` en el `package.json` de la raíz del repo por defecto, pero el frontend vive en `apps/web/`, así que "Install pnpm" fallaba en `ci/frontend`, `ci/contracts` y `security/frontend-deps`. Corregido en `d59fb40` (`package_json_file: apps/web/package.json` explícito) — los 3 workflows quedaron en verde contra `main`. Después, un PR de prueba (#10, cerrado sin mergear) con un error inducido por cada uno de los 5 checks bloqueantes confirmó que **los 5 fallan correctamente**: `ci/backend` (ruff), `ci/frontend` (eslint/prettier), `ci/contracts` (diff de cliente OpenAPI), `integration/integration` (Mongo/Azurite), `security/secret-scan` (gitleaks — detectó una AWS Access Key ID sintética tras corregir su charset al formato base32-like `A-Z2-7` que usa el ruleset por defecto). Los checks informativos (`python-deps`, `frontend-deps`) se mantuvieron en verde/warning sin bloquear, como se diseñó.
5. Aplicación manual de la branch protection recomendada en GitHub — ✅ cumplido y verificado vía API (`GET /repos/dreyser/ProcuraWise/branches/main/protection`): `required_status_checks.contexts = [backend, frontend, contracts, integration, secret-scan]` con `strict: true` (rama actualizada antes de merge); `required_approving_review_count: 0`; `enforce_admins: true`; `required_linear_history: true`; `allow_force_pushes: false`; `allow_deletions: false`; `required_conversation_resolution: true`. Método de merge a nivel de repo: `allow_squash_merge: true`, `allow_merge_commit: false`, `allow_rebase_merge: false` — coincide exactamente con la recomendación documentada. El repositorio además se hizo público durante esta sub-fase (decisión del founder, no de esta sesión).

**Fase 1C queda completamente cerrada: código comiteado (`bfe6626`, `d59fb40`), verificado contra GitHub Actions real, y con branch protection aplicada y confirmada. Fase 1 — Fundación técnica cierra formalmente.**

## Último commit relevante

`d59fb40 fix(ci): point pnpm/action-setup at apps/web/package.json`, rama `main`, precedido por `bfe6626 feat(ci): add GitHub Actions CI/CD and pipeline security (Fase 1C)`. Ambos comiteados y pusheados; los 3 workflows corren en verde contra `main`.

## Próximos pasos

1. Abrir una nueva sesión de Claude Code con instrucción explícita de ejecutar la sub-fase **`identity`**: `Tenant`/`User`/`Membership` + `TenantCollection` + middleware que extrae `tenant_id` del JWT — incluye, al inicio, pre-commit hooks locales y los 15 subpaquetes vacíos de bounded contexts (movidos aquí desde la Fase 1C original). No repetir el trabajo de Fase 1A/1B/1C.
2. A partir de `identity`, todo cambio pasa por PR real contra `main` — la branch protection ya exige los 5 checks en verde y rama actualizada antes de mergear.

## Bloqueos

Ninguno. Fase 1 — Fundación técnica está formalmente cerrada.

## Deuda técnica no bloqueante

- **Advertencia de deprecación `StarletteDeprecationWarning`** al correr `service/tests/integration/test_health.py` (y otros tests que usan `fastapi.testclient.TestClient`): "Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead." No falla ningún test, no afecta comportamiento en runtime (solo aparece en la suite de tests). No bloquea Fase 1C. Revisar cuando FastAPI/Starlette publiquen una migración estable a `httpx2`, o al tocar de nuevo las dependencias de testing del backend.
