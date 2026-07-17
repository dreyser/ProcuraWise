# Session Handoff

Plantilla de cierre de sesión. Cada sesión de Claude Code que trabaje en Fase 0 en adelante debe añadir una entrada nueva **arriba** de las anteriores (orden cronológico inverso), siguiendo exactamente esta estructura. No editar entradas de sesiones pasadas salvo corrección de un error factual.

---

## Plantilla (copiar para cada sesión nueva)

```
## Sesión — <fecha ISO> — <fase trabajada>

**Resumen:** <2-3 líneas: qué se hizo y por qué>

**Archivos tocados:**
- <ruta> — <qué cambió>

**Resultado de pruebas:**
- <comando ejecutado> → <pass/fail, resumen>

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):**
- <decisión> — <requiere ADR nuevo? sí/no, número si aplica>

**Deuda técnica introducida:**
- <ítem> — <por qué se aceptó, cuándo debe resolverse>

**Instrucciones para la siguiente sesión:**
- <qué hacer primero>
- <qué NO tocar todavía>
```

---

## Historial de sesiones

### Sesión — 2026-07-17 — Fase 1A: Estructura y herramientas

**Resumen:** Ejecutada la Fase 1A (planeada y aprobada en la misma sesión): estructura mínima ejecutable de `apps/web` (Vite+React+TS) y `service/` (FastAPI+worker sobre el paquete compartido `procurawise`), con lint/format/typecheck/tests funcionando vía `Makefile`. Docker, Mongo, CI, pre-commit y los 15 bounded contexts de dominio quedaron explícitamente diferidos a una sub-fase 1B nueva (ver `current-phase.md`).

**Archivos tocados:**
- `service/pyproject.toml`, `service/procurawise/{__init__.py,shared/config.py,api/main.py,api/export_openapi.py,worker/main.py}` — nuevo paquete backend, `Settings` compartida, FastAPI `/health`, worker entrypoint, export de `openapi.json`.
- `service/tests/{unit/test_config.py,integration/test_health.py}` — nuevo.
- `apps/web/` — scaffold Vite+React+TS (vía `pnpm create vite`), con contenido del template por defecto removido y reemplazado por página mínima de ProcuraWise que consulta `/health`; Vitest+RTL, ESLint flat config, Prettier, `orval.config.ts`.
- `Makefile`, `.env.example`, `.gitignore` (nuevos, raíz del repo).
- `docs/development/current-phase.md` — reescrito: sub-división 1A/1B de la sub-fase Bootstrap, corrección del estado de `.git`, criterios de aceptación marcados según lo verificado.
- `docs/development/session-handoff.md` (este archivo) — nueva entrada.
- `README.md` — actualizado "Estado del proyecto" y añadida sección "Cómo correr el proyecto localmente".

**Resultado de pruebas:**
- `make test` (backend `uv run pytest` + frontend `pnpm test`) → pass, 3 tests backend + 1 test frontend.
- `make lint` (ruff check + ruff format --check + eslint + prettier --check) → pass.
- `make typecheck` (mypy + tsc -b) → pass.
- `make contracts` (export `openapi.json` + `orval`) → pass, genera `apps/web/src/api/client.ts`.
- `make dev` (smoke manual) → `GET http://localhost:8000/health` → `{"status":"ok","environment":"local"}`; `http://localhost:5173/` sirve `<title>ProcuraWise</title>`. Procesos detenidos limpiamente al finalizar la verificación.
- `uv run python -m procurawise.worker.main` → loguea `worker ready (environment=local)...` y sale con código 0, sin tocar servicios externos.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):**
- Ninguna decisión arquitectónica nueva — todo el herramental usado ya estaba aprobado en `approved-mvp-plan.md` §4 y en ADRs `Accepted` (0001, 0005, 0006, 0007, 0017). No requiere ADR.
- Sub-división de la sub-fase "Fase 0 (Bootstrap)" en 1A/1B — decisión operativa de secuenciación de sesiones, no arquitectónica; documentada en `current-phase.md`, no requiere ADR.

**Deuda técnica introducida:**
- **Vite fijado en `^6.3.5`, no en la última versión mayor (8.x).** `pnpm create vite` instaló Vite 8 por defecto, que usa Rolldown (bundler nativo en Rust) como motor; el binding nativo `@rolldown/binding-darwin-arm64` no se resolvió en esta máquina (`pnpm install` lo omitió silenciosamente pese a ser una dependencia opcional declarada), rompiendo `vite`/`vitest` con `Cannot find native binding`. Se bajó a Vite 6.x (basado en esbuild, sin este problema) para no bloquear la Fase 1A en un problema de entorno ajeno al alcance de la sesión. Revisar cuando el ecosistema Rolldown madure o cuando se disponga de otra máquina/CI donde probar el binding nativo.
- **`orval.config.ts` genera cliente `fetch`, no `react-query`.** `architecture.md` §8 menciona hooks de React Query como objetivo del pipeline de contratos, pero instalar `@tanstack/react-query` sin ningún componente que lo consuma todavía habría sido una dependencia sin uso real. Se difiere a la fase que introduzca el primer fetch de datos real desde un componente.
- **`make migrate` no existe todavía** — no hay MongoDB en el alcance de Fase 1A; se agrega en Fase 1B junto con `docker-compose.yml`.
- **Pre-commit no configurado todavía** — diferido a Fase 1B junto con CI, para agrupar toda la automatización de calidad en una sola sub-fase.

**Instrucciones para la siguiente sesión:**
- Ejecutar **Fase 1B (Infraestructura local y automatización)**: `docker-compose.yml` (Mongo, Azurite, Redis, Mailhog), pre-commit (ruff, mypy permisivo, eslint, prettier), CI (`lint.yml`, `test.yml`), y los 15 subpaquetes vacíos de bounded contexts en `service/procurawise/`. Ver alcance exacto en `docs/development/current-phase.md`.
- No repetir el trabajo de Fase 1A — `apps/web`, `service/`, `Makefile`, `.env.example` y `.gitignore` ya existen y están verificados.
- No tocar todavía: lógica de dominio (`evaluations`, `vendors`, etc.), auth real, IA, pagos — siguen fuera de alcance hasta las fases correspondientes del backlog.
- Ningún archivo de esta sesión fue comiteado a git — el founder debe confirmar explícitamente si quiere commitear el resultado de Fase 1A antes o junto con el trabajo de Fase 1B.

---

### Sesión — 2026-07-16 — Materialización documental del plan aprobado

**Resumen:** Se convirtió el plan aprobado (`act-a-como-arquitecto-de-mutable-curry.md`, aprobado por el founder el 2026-07-16) en documentación persistente del repositorio, para que las sesiones futuras no dependan del historial de conversación. No se escribió código, no se instalaron dependencias, no se creó infraestructura ni configuración ejecutable.

**Archivos tocados:**
- `CLAUDE.md` — reescrito, operativo y corto.
- `README.md` — actualizado para explicar la organización del proyecto.
- `docs/planning/approved-mvp-plan.md` — nuevo, plan aprobado materializado.
- `docs/product/mvp-scope.md`, `docs/product/roadmap.md` — nuevos.
- `docs/development/backlog.md`, `current-phase.md`, `session-handoff.md` (este archivo) — nuevos.
- `docs/architecture/architecture.md` — nuevo.
- `docs/architecture/decisions/0001-*.md` a `0019-*.md` — nuevos, 19 ADRs.
- `docs/security/threat-model.md` — nuevo.
- `docs/operations/deployment.md` — nuevo.

**Resultado de pruebas:** No aplica — sesión puramente documental, sin código ejecutable que probar.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):**
- Ninguna decisión arquitectónica nueva. Se formalizaron en ADRs decisiones ya tomadas en sesiones de planeación previas (2026-07-15 y 2026-07-16), sin añadir alcance nuevo.
- Se adoptó la jerarquía de documentación `docs/{planning,product,development,architecture,security,operations}/` en lugar de la estructura plana `docs/*.md` que proponía la sección F del plan original — decisión operativa de organización de archivos, no arquitectónica; no requiere ADR.
- Se crearon 3 ADRs (0017 Frontend React+TS, 0018 MongoDB Atlas como datastore, 0019 Azure Container Apps) que no tenían número propio en la sección M del plan original, para dar trazabilidad individual a decisiones ya bloqueadas por la spec §27.

**Deuda técnica introducida:** Ninguna — no hay código.

**Instrucciones para la siguiente sesión:**
- La siguiente sesión debe ejecutar la **Fase 0 (Bootstrap)** exactamente según el alcance descrito en `docs/development/current-phase.md` y la fila "Fase 0" de la tabla E1 en `docs/development/backlog.md`.
- Antes de tocar el repositorio, esa sesión debe confirmar explícitamente con el usuario la ejecución de `git init` + primer commit (el repositorio no tiene `.git` todavía).
- No iniciar lógica de dominio, Azure real, IA ni pagos — están explícitamente fuera de alcance de la Fase 0.
- Verificar que los comandos `make dev/test/lint/contracts/migrate` referenciados en `CLAUDE.md` como "interfaz de comandos objetivo" existan antes de asumir que están implementados; si no existen, la Fase 0 es responsable de crearlos.
