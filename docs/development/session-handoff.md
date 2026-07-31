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

### Sesión — 2026-07-31 — Fase 10 (E4): Wizard guiado estático + autosave

**Resumen:** Sesión de planeación en Plan Mode (2 rondas de agentes Explore en paralelo: documentación/roadmap/backlog primero para identificar la fase siguiente, luego código de `evaluations`/frontend existente para el inventario de reutilización) seguida de una única pregunta bloqueante resuelta explícitamente por el founder vía `AskUserQuestion` antes de implementar, y de implementación completa en 5 bloques incrementales (0-4), cada uno verificado antes de avanzar.

**Decisión bloqueante resuelta por el founder (2026-07-31):**
1. Mecanismo de "sin pérdida de datos al recargar": opción A — step-persisted, sin campo `version` en `Evaluation`. El wizard deriva su paso actual del estado real de la evaluación en cada carga, en vez de autosave real de campo con concurrencia optimista. Consecuencia: la fase completa quedó sin ningún cambio de backend.

**Contenido entregado (100% frontend, `apps/web/src/`) — ver detalle completo en `docs/development/current-phase.md`, sección Fase 10:**
- **Bloque 0**: housekeeping — `README.md`/`current-phase.md`/`session-handoff.md` corregidos (Fase 8/PR #21 y Fase 9/PR #22 ya estaban fusionadas a `main`, la documentación no lo reflejaba).
- **Bloque 1**: núcleo del wizard (`deriveWizardStep.ts`, `EvaluationWizard.tsx`, `WizardStepper.tsx`, `WizardStepMetadata.tsx`), rutas nuevas, `EvaluationCreatePage.tsx` eliminado (absorbido por el Paso 1).
- **Bloque 2**: `evaluationReadiness.ts` (extraído, compartido con `VendorsPage.tsx`), `WizardStepRequirements.tsx`/`WizardStepVendors.tsx`.
- **Bloque 3**: `WizardStepReview.tsx` (inicia recepción), afordancia "Continuar configuración" en `EvaluationListPage.tsx`.
- **Bloque 4**: `e2e/evaluation-wizard.spec.ts` (2 specs nuevos, cierra la brecha de cobertura de "crear evaluación end-to-end" documentada desde el cierre de VS-2C).

**Archivos tocados:** `apps/web/src/features/evaluations/wizard/*` (nuevo), `apps/web/src/features/evaluations/lib/evaluationReadiness.ts` (nuevo), `apps/web/src/features/evaluations/pages/{VendorsPage,EvaluationListPage}.tsx`, `apps/web/src/app/router.tsx`, `apps/web/e2e/evaluation-wizard.spec.ts` (nuevo), `apps/web/src/App.integration.test.tsx` (actualizado al nuevo flujo de creación). Tests nuevos: `deriveWizardStep.test.ts`, `evaluationReadiness.test.ts`, `WizardStepper.test.tsx`, `WizardStepMetadata.test.tsx` (15 tests). Ningún archivo bajo `service/` tocado.

**Resultado de pruebas de esta sesión (todas ejecutadas contra Docker real, ninguna asumida):**
- `make lint` → 0 errores. `make typecheck` → limpio.
- `make test` → **93 passed backend** (sin cambios) **+ 94 passed frontend**.
- `make test-integration` (Docker real) → **140 passed** (idéntico a Fase 9).
- `make test-e2e` (Docker + Playwright real) → **4 specs passed**.
- `make contracts` → sin diff (`git status` limpio sobre `openapi.json`/`client.ts`).
- `pnpm build` → build de producción exitoso.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):** ninguna. No se reabre monolito/DB/hosting/patrón de comunicación; la fase completa es orquestación frontend sobre endpoints ya existentes.

**Deuda técnica introducida:** ninguna nueva. El diferimiento de autosave de campo-por-campo (opción B/C) es alcance explícitamente descartado por el founder, no deuda.

**Estado final: Fase 10 cerrada formalmente.** El criterio de aceptación del backlog queda abierto en ningún punto — ver interpretación operacional acordada en `current-phase.md`.

**Instrucciones para la siguiente sesión:**
- Próxima fase según `backlog.md`: Fase 11 (`KnowledgeTemplate`, biblioteca de requerimientos, P1, depende de Fase 9) o Fase 12 (aprobación interna + publicación con snapshot, P0, depende de Fase 10) — ambas quedan disponibles; `roadmap.md`/`backlog.md` no fuerzan un orden estricto entre ellas más allá de sus propias dependencias.
- No tocar todavía: `Colaborador proveedor`/auth real de proveedor (Fase 15), consola `platform_admin`/`Administrador del cliente` (Fase 25), dimensión económica real (Fase 19-20).

### Sesión — 2026-07-30 — Fase 9 (E3): RBAC completo + `Assignment` por sección

**Resumen:** Sesión de planeación en Plan Mode (4 agentes Explore en paralelo: roadmap/backlog/handoff, arquitectura/ADRs/threat-model, estructura del código, y el detalle de roles del §4 de la spec + gap contra el código actual) seguida de implementación completa en 6 bloques incrementales, cada uno verificado contra Docker real antes de avanzar. Se presentaron 3 decisiones bloqueantes al founder (alcance de la fase, profundidad de `platform_admin`/`Administrador del cliente`, y si refactorizar "roles acumulables"), resueltas explícitamente antes de implementar.

**Decisiones bloqueantes resueltas por el founder (2026-07-30):**
1. Alcance de la fase: opción 3 — roles de comprador + `Assignment` en una sola rama/PR; `Colaborador proveedor` diferido a Fase 15, profundidad de `platform_admin`/`Administrador del cliente` diferida a Fase 25.
2. `platform_admin`/`Administrador del cliente`: opción 1 — rol + esqueleto mínimo auditado (`/api/v1/admin/*`, `find_across_tenants()`), sin consola/UI (Fase 25).
3. "Roles acumulables": cerrado — se mantiene el patrón de múltiples `Membership` por usuario/rol, sin migración ni ADR nuevo.

**Contenido entregado (backend, `service/procurawise/`) — ver detalle completo en `docs/development/current-phase.md`, sección Fase 9:**
- **Bloque 1**: `identity/models.py::Role` (3→8 valores), `shared/roles.py` (nuevo, centraliza tuplas de roles antes duplicadas en 5 routers), `dev_seed.py` (usuarios por rol nuevo, demostración de roles acumulables).
- **Bloque 2**: módulo `assignments/` nuevo (`Assignment` vincula evaluador↔sección↔dimensión, valida rol esperado y existencia real de la sección), `migrations/0005_assignments_indexes.py`, `audit/models.py` (+`assignment_created`/`assignment_removed`).
- **Bloque 3**: `scoring/service.py::_enforce_section_assignment` (sección sin asignar → cualquier evaluador del sub-rol puede calificarla; sección asignada → solo el evaluador asignado). Corrección real encontrada y aplicada: `SCORE_WRITE_ROLES` separado de `BUYER_READ_ROLES` — el Bloque 1 le había dado sin querer permiso de escritura de scores a `internal_collaborator`/`approver`.
- **Bloque 4**: módulo `admin/` nuevo, físicamente separado (`/api/v1/admin/*`), `PlatformAdminAccount` (no es una `Membership` — sin `tenant_id`), JWT con `token_use` distinto (verificado que un token no sirve para el otro router en ningún sentido), `find_across_tenants()` en `EvaluationRepository` auditado por evaluación tocada; `GET /api/v1/org/members` (`tenant_admin` + `evaluation_owner`).
- **Bloque 5 (frontend)**: `app/router.tsx::BUYER_ROLES` corregido (contenía `'evaluator'`, rol que ya no existe tras el Bloque 1 — regresión real que habría roto el login de todo evaluador), `AssignmentsPage.tsx` nuevo, `ScoringPage.tsx` (inputs de calificación ya no editables para roles sin permiso de escritura), `e2e/vertical-slice.spec.ts` (email de evaluador actualizado).

**Archivos tocados:** ver lista completa en `current-phase.md`, sección Fase 9. Tests nuevos: `tests/unit/test_platform_admin_models.py`, `tests/integration/{test_assignment_indexes,test_platform_admin_indexes}.py`, `tests/api/{test_assignments,test_section_scoped_scoring,test_admin_router,test_org_members}.py`, `tests/security/{test_role_permissions,test_assignment_isolation}.py`.

**Resultado de pruebas de esta sesión (todas ejecutadas contra Docker real, ninguna asumida):**
- `make lint` → 0 errores. `make typecheck` → limpio (mypy 80 archivos backend; `tsc -b` frontend).
- `make test` → **93 passed backend + 79 passed frontend**.
- `make test-integration` (Docker real) → **140 passed**.
- `make test-e2e` (Docker + Playwright real) → **2 passed**, teardown limpio.
- `make contracts` corrido dos veces consecutivas → idéntico byte a byte.
- `pnpm build` → build de producción exitoso.
- `git diff --check` → limpio.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):** ninguna reabre monolito/DB/hosting/patrón de comunicación. El módulo `admin` es un subpaquete estándar más, ya previsto conceptualmente en `architecture.md` §5 (`platform_admin`/`find_across_tenants()`) — implementarlo no es una decisión arquitectónica nueva, es completar un diseño ya aprobado.

**Deuda técnica introducida:**
- Ninguna nueva. Los diferimientos (Colaborador proveedor→Fase 15, consola admin→Fase 25, dimensión económica→Fase 19-20) son alcance explícitamente aprobado por el founder, no deuda.

**Estado final: Fase 9 cerrada formalmente.** Ningún criterio de aceptación del backlog queda abierto.

**Instrucciones para la siguiente sesión:**
- Próxima fase según `backlog.md`: Fase 10 (wizard guiado estático + autosave), depende de Fase 9 (ya cerrada).
- No tocar todavía: `Colaborador proveedor`/auth real de proveedor (Fase 15), consola `platform_admin`/`Administrador del cliente` (Fase 25), dimensión económica real (Fase 19-20).

### Actualización — merge confirmado a `main` (PR #21 Fase 8, PR #22 Fase 9) (2026-07-30)

**Fase 8 y Fase 9 están fusionadas a `main`.** El founder comiteó y mergeó ambos PRs fuera de una sesión de Claude Code documentada — `main` avanzó `f537f64` → `c786238 feat: add append-only audit trail (#21)` → `4154c49 feat: implement role-based access control and section assignments (#22)`. Esta nota reemplaza la afirmación anterior ("`main`/la rama de esta fase no están fusionadas entre sí todavía"), que había quedado desactualizada junto con `README.md`. Confirmado por lectura directa de `git log --oneline` sobre `main` al iniciar la sesión de planeación de Fase 10.

### Sesión — 2026-07-30 — Housekeeping (merge AUTH-PROD/JWT-fixes) + Fase 8 (E3, `audit`): implementación completa

**Resumen:** Sesión de planeación en Plan Mode (3 agentes Explore en paralelo: estado de git/docs, inventario de mutaciones VS-2A/VS-2B/VS-2C/AUTH-PROD, y patrones de test/migración/infra) seguida de implementación completa de la Fase 8 (`audit`: `AuditEvent` append-only) en 6 bloques incrementales, cada uno verificado contra Docker real antes de avanzar. Se presentaron 4 preguntas bloqueantes al founder, resueltas explícitamente antes de avanzar a implementación. Plan completo aprobado en `~/.claude/plans/dreamy-enchanting-seal.md` (fuera del repo). Housekeeping previo: se confirmó que AUTH-PROD (PR #17) y el fix de flakiness de JWT (PR #18) ya estaban fusionados a `main` sin que la documentación lo reflejara — misma clase de laguna de continuidad ya vista con VS-2C/PR #15.

**Decisiones bloqueantes resueltas por el founder (2026-07-30):**
1. Consistencia mutación↔`AuditEvent`: best-effort — nunca se revierte la mutación de negocio; fallo de auditoría → log `ERROR` estructurado, encapsulado en un único punto (`AuditEventService.record()`). Sin outbox/transacciones esta fase.
2. Autosave de `ProposalAnswer`: no se audita — solo `PROPOSAL_SUBMITTED` (evento terminal con referencia a snapshot).
3. Retención: 1 año (ADR 0016), vía `expires_at`/TTL index, duración centralizada en config, no configurable por tenant.
4. Rama pendiente `fix/tampered-token-test-flake-security` (`95c5ea7`): mergear primero, aislado, antes de tocar código de auditoría.

**Housekeeping ejecutado en esta sesión:**
- PR de `95c5ea7` (aplicaba el fix de tampering de JWT a `test_auth_tenant_isolation.py`, ya corregido en `test_jwt_provider.py` por PR #18) abierto y mergeado por el founder — landing como **PR #19 (`877559a`)**. Un **PR #20 (`f537f64`)** se mergeó también por duplicado accidental; diff vacío contra #19 (no-op, sin riesgo, no se revirtió — dejarlo así evita reescribir historia de `main` sin necesidad).
- `main` local actualizado por fast-forward a `origin/main` (`f537f64`).
- Rama `phase-8/audit` creada desde ese `main` actualizado.
- Ramas obsoletas eliminadas (local + remoto), verificadas sin commits únicos antes de borrar: `fix/jwt-tampered-signature-test-flake`, `phase-2/auth-prod`, `phase-2/vs-2c`, `phase-1/foundation`, y `fix/tampered-token-test-flake-security` (ya mergeada).

**Contenido entregado (backend, `service/procurawise/`) — ver detalle completo en `docs/development/current-phase.md`, sección Fase 8:**
- **Bloque 1**: `audit/models.py` (`AuditEvent`, enum cerrado `AuditAction` de 13 acciones), `audit/repository.py` (append-only, solo `record()`+lectura), `migrations/0004_audit_events_indexes.py` (3 índices de consulta + TTL sobre `expires_at`), `shared/config.py` (+`audit_event_retention_days`), `shared/request_context.py` (nuevo — `correlation_id` vía `ContextVar`, primer mecanismo de request-id de la app).
- **Bloque 2**: `audit/service.py` (`AuditEventService.record()` best-effort, `list_for_evaluation()` paginado por cursor), `audit/schemas.py`, `audit/router.py` (`GET /api/v1/evaluations/{evaluation_id}/audit-events`), `api/main.py` (+middleware de correlation-id, +registro del router `audit`).
- **Bloque 3**: `evaluations/service.py`/`router.py` — 9 acciones instrumentadas (create/update evaluation, add/update/delete requirement, link/unlink vendor, start-collection, start-evaluation).
- **Bloque 4**: `proposals/service.py`/`vendor_portal/service.py`/`router.py` — solo `submit` (`proposal_submitted`, referencia a snapshot, nunca contenido); autosave (`update_answer`) deliberadamente sin instrumentar.
- **Bloque 5**: `scoring/service.py`/`router.py` — `score_created`/`score_updated` (valor numérico + `requirement_id`, comentario excluido) y `evaluation_completed`.
- **Bloque 6**: contratos regenerados (`apps/web/openapi.json`/`client.ts`, +260 líneas), `docs/security/threat-model.md` (nueva sección "Auditoría (Fase 8, `audit`)" + fila en riesgos aceptados), `docs/development/backlog.md` (fila Fase 8 → Completed).
- Cada bloque de servicio mutador (`EvaluationService`/`ProposalService`/`ScoringService`) ganó un constructor param `audit: AuditEventService` y un param `actor: ActorContext` en sus métodos mutadores — los tests de concurrencia que instanciaban estos servicios directamente (`test_vendor_link_concurrency.py`, `test_proposal_version_concurrency.py`) se actualizaron para construir un `AuditEventService`/`ActorContext` real.

**Archivos tocados:** ver lista completa en `current-phase.md`, sección Fase 8. Nuevos tests: `tests/unit/test_audit_event_model.py`, `tests/integration/{test_audit_repository,test_audit_indexes,test_evaluations_audit_instrumentation,test_proposals_audit_instrumentation,test_scoring_audit_instrumentation}.py`, `tests/security/test_audit_isolation.py`.

**Resultado de pruebas de esta sesión (todas ejecutadas contra Docker real, ninguna asumida):**
- `make lint` → 0 errores. `make typecheck` → limpio (mypy 65 archivos backend; `tsc -b` frontend).
- `make test` → **82 passed backend + 79 passed frontend**.
- `make test-integration` (Docker real) → **109 passed** (27 nuevos de audit, incluyendo casos negativos de mutación rechazada sin evento espurio).
- `make contracts` corrido dos veces consecutivas → idéntico byte a byte.
- `git diff --check` → limpio.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):** ninguna — el bounded context `audit` ya estaba previsto en `architecture.md` como subpaquete estándar; ninguna decisión de esta sesión reabre monolito/DB/hosting/patrón de comunicación. El middleware de `correlation_id` es aditivo, no arquitectónico.

**Deuda técnica introducida:**
- `AuditEvent` con garantía best-effort (gap posible si el insert falla tras una mutación exitosa) y sin protección contra acceso admin directo a Mongo — aceptado explícitamente por el founder, documentado en `threat-model.md`.
- Sin UI de consulta de audit trail — el criterio de aceptación ("consultable") se satisface con el endpoint API; UI queda como extensión futura si se pide explícitamente.

**Estado final: Fase 8 cerrada formalmente.** Ningún criterio de aceptación del backlog queda abierto.

**Instrucciones para la siguiente sesión:**
- `main`/`phase-8/audit` no están fusionados entre sí todavía — el founder decide si comitea/abre PR (mismo patrón que fases anteriores).
- Próxima fase según `backlog.md`: Fase 9 (RBAC completo + `Assignment`), depende de Fase 8 (ya cerrada).
- No tocar todavía: RBAC completo, `Assignment`, consola `platform_admin` (Fase 25), UI de audit trail (no en alcance de Fase 8).

### Sesión — 2026-07-29 — AUTH-PROD: auth productiva de comprador (email+password + OIDC Microsoft/Google)

**Resumen:** Sesión de planeación (Plan Mode, con 3 agentes Explore en paralelo investigando backend/frontend/mecanismo de invitación de proveedores antes de diseñar) seguida de implementación completa en 5 bloques incrementales, cada uno verificado contra Docker real antes de avanzar. Reemplaza `DevelopmentIdentityProvider` como mecanismo de identidad para rutas de comprador (`evaluation_owner`/`evaluator`); `vendor_contact` se queda deliberadamente en el mecanismo interino hasta Fase 15.

**Alcance confirmado por el founder antes de diseñar (4 preguntas vía `AskUserQuestion`), no reabierto durante la implementación:**
1. Solo auth de comprador esta fase — `vendor_contact` se queda en `DevelopmentIdentityProvider` hasta Fase 15. Consecuencia aceptada: `/api/v1/vendor-portal/*` sigue devolviendo 404 en producción hasta esa fase.
2. JWT de acceso corto (30 min) en memoria, sin refresh token, sin cookies, sin persistencia (`localStorage`/`sessionStorage`).
3. Sin self-signup — provisión vía `dev_seed.py` (password conocida `dev-password-2026`) o `provisioning_cli.py`/`make provision-user` (cualquier ambiente, nunca vía HTTP).
4. Sin recuperación de contraseña — no se agregó Mailhog/SMTP.

**Archivos tocados (resumen — ver detalle completo en `docs/development/current-phase.md`, sección AUTH-PROD):**
- Backend nuevo: `service/procurawise/identity/{passwords,jwt_provider,oidc,auth_schemas,auth_router}.py`, `service/procurawise/provisioning_cli.py`, `service/migrations/0003_users_auth_indexes.py`, `service/tests/{unit/test_passwords,unit/test_jwt_provider,integration/test_user_auth_indexes,api/test_auth_router,security/test_auth_tenant_isolation}.py`, `service/tests/fakes/fake_oidc_provider.py`.
- Backend modificado: `identity/{models,repository,service,dev_provider,router}.py`, `shared/{config,context}.py`, `vendor_portal/router.py`, `api/main.py`, `dev_seed.py`, `pyproject.toml`, `.env.example`, `Makefile`; tests existentes actualizados para autenticar comprador vía JWT real en vez de `X-Dev-Membership-Id` (`tests/conftest.py` +`bearer_headers_for()`, `tests/api/{test_requirement_patch_validation,test_vendor_organizations,test_vertical_slice_happy_path}.py`, `tests/security/{test_tenant_isolation,test_vendor_isolation}.py`, `tests/unit/{test_config,test_dev_provider,test_identity_models}.py`).
- Frontend nuevo: `apps/web/src/auth/{AuthContext,LoginPage,AuthCallbackPage,SelectWorkspacePage,LoginPage.test}.tsx`.
- Frontend modificado: `lib/http.ts`, `actor/ActorContext.tsx`, `app/{guards,AppShell,router}.tsx`, `App.tsx`, las 7 páginas de `features/{evaluations,scoring,proposals}` que leían `useActor()` (migradas a `useAuth()`), `app/AppShell.test.tsx`, `App.test.tsx`, `App.integration.test.tsx`, `e2e/{vertical-slice,isolation}.spec.ts`.

**Decisiones técnicas tomadas durante la implementación (dentro de los ADRs ya aprobados, no requieren ADR nuevo):** `argon2-cffi` sobre `passlib` (sin mantenimiento activo); `PyJWT` sobre `python-jose`; HS256 sobre RS256 (monolito de un proceso); diseño "fat JWT" (embebe `ActorContext` completo, sin round-trip a Mongo); `joserfc` sobre `authlib.jose` (deprecado desde authlib 1.7, confirmado por warning propio de la librería); `authlib.integrations.httpx_client.AsyncOAuth2Client` en vez de `authlib.integrations.starlette_client.OAuth` (esa integración exige `SessionMiddleware`/cookies, incompatible con la decisión de alcance #2); state/nonce OIDC embebidos en un JWT propio de vida corta en vez de sesión server-side (no hay session store en este diseño).

**Bugs/hallazgos reales encontrados y corregidos (verificados contra Docker real, no hipotéticos):**
- Índice único multikey sobre `oidc_identities` sin `sparse=True` rompía con `DuplicateKeyError` entre dos usuarios sin identidad OIDC (Mongo indexa un array vacío como `{null, null}`, no como "sin clave") — corregido con `sparse=True`, verificado con inserciones reales.
- El fixture `seeded_actors` de otros tests borra (`.drop()`) la colección `users` en su teardown, destruyendo también los índices de la migración 0003 sin que `run_migrations()` lo detecte — `test_user_auth_indexes.py` corregido para llamar `apply()` de la migración directamente en cada test en vez de depender del tracking de migraciones ya aplicadas.
- 25 tests backend existentes rotos por el swap de `require_role` (autenticaban comprador vía `X-Dev-Membership-Id`, ya no válido) — corregidos con un helper `bearer_headers_for()` que emite un JWT real in-process; dos de ellos cambiaron su expectativa de 403 a 401 (ausencia total de credenciales de comprador falla en autenticación antes que en rol — aislamiento más fuerte, no más débil).
- Bug de test reintroducido: dos tests nuevos de `switch-tenant` asumieron que `tenant_ids()`'s etiqueta ordenada por UUID correspondía a un usuario específico — la misma clase de bug ya documentada y corregida en VS-2A para otro archivo. Corregido con `_membership_id_for(mongo_test_db, email, role)`.
- `page.goto()` de Playwright recarga la página completa, lo que borra el access token en memoria del comprador (consecuencia esperada de la decisión de alcance #2) — los specs e2e reescritos usan navegación SPA (tabs `NavLink`) dentro de una misma sesión y relogin explícito tras cualquier `page.goto()` intermedio. `isolation.spec.ts` también actualizado: `/` ya no redirige a `/dev/select-actor` (ahora prioriza `/login`), y un `vendor_contact` visitando una ruta de comprador ahora recibe 401 (sin credenciales) en vez de 403 (rol incorrecto).

**Resultado de pruebas de esta sesión (todas ejecutadas contra Docker real, ninguna asumida):**
- `make lint` → 0 errores (backend + frontend). `make typecheck` → limpio (mypy 58 archivos backend incl. stubs `types-authlib`; `tsc -b` frontend).
- `make test` → **76 passed backend + 79 passed frontend** (14 archivos).
- `make test-integration` (Docker real) → **89 passed**.
- `make test-e2e` (Docker + Playwright real) → **2 passed** (specs reescritos para login real de comprador), teardown limpio.
- `make contracts` corrido dos veces consecutivas → idéntico byte a byte (`shasum` comparado).
- `git diff --check` → limpio (exit 0).

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):** Ninguna nueva de arquitectura — todas las decisiones técnicas (librerías, HS256, fat JWT, `joserfc`) son elección de implementación dentro de ADR 0003 ya aprobado, no cambios de arquitectura (monolito/DB/hosting/comunicación) que `CLAUDE.md` §3 reserve para ADR nuevo.

**Deuda técnica introducida:**
- Verificación manual de OIDC contra Microsoft/Google reales pendiente (requiere apps OAuth de prueba registradas) — no bloqueante, la lógica está implementada/tipada y verificada vía fake en tests automatizados.
- Portal de proveedores inalcanzable en producción hasta Fase 15 — decisión de alcance documentada, no bug.

**Instrucciones para la siguiente sesión:**
- AUTH-PROD está completo y verificado, sin comitear — el founder decide si comitea/abre PR (mismo patrón que VS-2A/VS-2B/VS-2C).
- Al planear Fase 15 (NDA/COI real), recordar que ese es el momento de reemplazar `DevelopmentIdentityProvider` para `vendor_contact` por invitación real por token — no antes.
- Confirmar con el founder cuál es la siguiente fase de código después de AUTH-PROD (Fase 8/E3 parece desbloqueada, pero no se asume unilateralmente).
- No tocar todavía: invitación de proveedores, self-signup, recuperación de contraseña, refresh tokens — todos explícitamente fuera de alcance de esta fase por decisión del founder.

### Sesión — 2026-07-29 — Housekeeping: confirmación de merge real de VS-2C (PR #15) y actualización de continuidad

**Resumen:** Sesión de solo verificación y documentación (sin funcionalidad nueva, sin refactors, sin ADRs, sin commit de código), continuación directa de la sesión de cierre formal de VS-2C de este mismo día (ver entrada siguiente). Se detectó que, entre esa sesión de cierre y esta, el founder comiteó el trabajo y abrió/mergeó el PR #15 (`phase-2/vs-2c` → `main`) fuera de una sesión de Claude Code documentada — dejando `current-phase.md`/`session-handoff.md` desactualizados (seguían diciendo "sin comitear"). Esta sesión cierra esa laguna de continuidad.

**Verificación realizada (API pública de GitHub + git local, sin modificar código de producción):**
- `git fetch origin --prune` → `origin/main` avanzó de `3136626` a `0b38ef7`.
- `GET /repos/dreyser/ProcuraWise/pulls/15` → `state: closed`, `merged: true`, `merged_at: 2026-07-29T16:26:06Z`, `base: main` ← `head: phase-2/vs-2c`, `merge_commit_sha: 0b38ef7` (squash-merge, padre único `3136626`, consistente con `allow_squash_merge` como único método permitido en el repo).
- `GET /repos/dreyser/ProcuraWise/commits/0b38ef7/check-runs` → **15/15 en `success`**: `backend`, `frontend`, `contracts`, `integration`, `e2e`, `secret-scan`, `python-deps`, `frontend-deps`, más 7 checks de `Dependabot`. Ninguno en `failure`/`pending` en el commit final mergeado.
- `git diff` entre `main`(antiguo)/`origin/main`(nuevo) y entre `phase-2/vs-2c`/`origin/main` → vacíos/idénticos en conteo de archivos (100 archivos, +15321/-2238): el contenido fusionado es byte-idéntico al de la rama de trabajo, sin drift.
- `git checkout main && git merge --ff-only origin/main` → fast-forward limpio `3136626..0b38ef7`, sin conflictos. Rama local devuelta a `phase-2/vs-2c` al terminar.

**Hallazgo:** el check de "frontend" que el founder reportó como fallido durante el PR no aparece en la corrida final contra el commit que realmente se mergeó — o fue una corrida intermedia anterior a los commits de fix (`beadd6f`/`c1985ea`), o corresponde a una de las PRs de Dependabot abiertas para dependencias de `apps/web`, no relacionadas con PR #15. No bloqueó el merge; no se investigó más a fondo por ser un side-channel fuera del alcance de esta sesión.

**Archivos tocados:**
- `docs/development/current-phase.md` — sección VS-2C: nueva subsección "Actualización — merge confirmado a `main` (PR #15, 2026-07-29)"; "Último commit relevante", "Próximos pasos" (punto 1) y "Bloqueos" corregidos para reflejar el merge real.
- `docs/development/session-handoff.md` (este archivo) — esta entrada nueva. La entrada de cierre formal de VS-2C (siguiente, mismo día) no se edita — queda como registro histórico de lo que era cierto en el momento en que se escribió (regla de la plantilla: no editar entradas pasadas salvo corrección de un error factual, y no era un error en ese momento).

**Resultado de pruebas:** ninguna corrida nueva de `make test`/`lint`/`typecheck` — sesión de solo verificación de estado de git/GitHub y housekeeping documental, no de código.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):** ninguna.

**Deuda técnica introducida:** ninguna. Se cierra la deuda de continuidad detectada (documentación desactualizada respecto al merge real de VS-2C).

**Estado real de VS-2C: ✅ cerrado formalmente y fusionado a `main`** (PR #15, `0b38ef7`, 2026-07-29T16:26:06Z). Sin pendientes de esta fase.

**Próxima fase — sigue sin resolver, no es competencia de esta sesión:** `AUTH-PROD` vs. Fase 8/E3 — ver nota completa en la entrada siguiente y en `current-phase.md`, sección "Próximos pasos".

**Instrucciones para la siguiente sesión:**
- `main` local y remoto ya están sincronizados en `0b38ef7` — no repetir esta verificación.
- Antes de iniciar código nuevo, el founder debe decidir entre `AUTH-PROD` y Fase 8/E3 (pregunta abierta #2 de la entrada siguiente, sigue vigente).
- No tocar: identidad productiva ni `audit`/RBAC hasta que se resuelva esa decisión.

### Sesión — 2026-07-29 — VS-2C: cierre técnico formal (verificación, sin funcionalidad nueva)

**Rol de la sesión:** responsable de cierre técnico. Solo verificación, documentación y preparación de cierre — sin funcionalidad nueva, sin refactors no relacionados, sin iniciar la siguiente fase, sin commit (todo explícitamente pedido por el founder).

**Commit/base desde donde inició VS-2C:** `3136626 feat(evaluations): implement vendor evaluation backend slice (#14)` — mismo commit que `origin/main` y que `merge-base HEAD origin/main` en esta sesión. Todo el trabajo de VS-2C (Bloques 1-5, sesión anterior del 2026-07-28) vive sin comitear en el árbol de trabajo.

**Rama actual:** `phase-2/vs-2c` (coincide con `origin/phase-2/vs-2c`, que ya existe en el remoto en el mismo estado; 0 commits de diferencia respecto a `origin/main` — el diff completo es working-tree, no de historial).

**Funcionalidad implementada:** ninguna nueva en esta sesión — se verificó la ya implementada en la sesión del 2026-07-28 (ver esa entrada y la sección VS-2C de `current-phase.md` para el detalle completo: selector de actor dev, shell por rol, CRUD de evaluaciones/requirements, `VendorCatalogPicker`, portal de proveedor con autosave secuencial, scoring con `Score.version`, resultados por-propuesta, `make test-e2e`).

**Decisiones tomadas en esta sesión:** ninguna de diseño/arquitectura — sesión de auditoría. Única decisión operativa: cerrar el hallazgo de cobertura del E2E permanente (ver abajo) con una verificación suplementaria desechable en la misma sesión, en vez de dejarlo sin verificar o de ampliar la suite permanente sin autorización explícita (fuera del alcance pedido: "no agregues funcionalidad").

**Dependencias agregadas:** ninguna — sesión de solo verificación. Las dependencias del frontend (confirmadas por lectura de `apps/web/package.json`, ya agregadas en la sesión del 2026-07-28) son: `react-router-dom@^7.18.1`, `@tanstack/react-query@^5.101.4`, `tailwindcss@^4.3.3` + `@tailwindcss/vite@^4.3.3`, `radix-ui@^1.6.7` (paquete unificado de shadcn) + `class-variance-authority@^0.7.1` + `clsx@^2.1.1` + `tailwind-merge@^3.6.0` + `lucide-react@^1.27.0` + `@fontsource-variable/geist@^5.3.0` + `tw-animate-css@^1.4.0` + `shadcn@^4.16.0` (scaffolding de ADR 0006), `react-hook-form@^7.83.0` + `zod@^4.4.3` + `@hookform/resolvers@^5.5.7`, `@playwright/test@^1.62.0` (dev) + `@testing-library/user-event@^14.6.1` (dev). Todas justificadas en el plan aprobado (§8), ninguna fuera de ese alcance.

**Endpoints agregados (de la sesión anterior, confirmados por diff contra `origin/main` en esta sesión):** `GET /api/v1/vendor-organizations` (nuevo, `identity/router.py`); `RequirementScoreDetail.version`/`.comment` en `GET /api/v1/evaluations/{id}/results` (campos nuevos, mismo endpoint); `PATCH /api/v1/evaluations/{id}/requirements/{rid}` (endpoint existente, validación reforzada — ver hallazgo confirmado abajo).

**Tests y resultados exactos de esta sesión (todos ejecutados, ninguno asumido):**
- `git status` → 28 archivos modificados + 12 rutas nuevas (sin archivos fuera del alcance autorizado, revisado uno por uno contra el plan).
- `git diff --check` → limpio, exit 0.
- `make lint` → 0 errores (backend: ruff check + format limpio; frontend: eslint 0 errores/22 warnings preexistentes — 19 en `client.ts` generado por un quirk de plantilla de `orval`, 3 por la regla `react-refresh/only-export-components` en `ActorContext.tsx`/`badge.tsx`/`button.tsx`, ninguno de esta sesión; prettier limpio).
- `make typecheck` → limpio (mypy 52 archivos backend; `tsc -b` frontend).
- `make test` → **59 passed backend + 70 passed frontend** (13 archivos de test).
- `make test-integration` (Docker real, Mongo+Azurite) → **61 passed**.
- `make test-e2e` (Docker + Playwright real) → **2 passed** (`isolation.spec.ts`, `vertical-slice.spec.ts`); teardown limpio confirmado (`lsof -i :8000 -i :5173` vacío, `docker ps` sin contenedores).
- `make contracts` corrido dos veces consecutivas → segunda corrida sin cambios (diff byte a byte idéntico entre ambas).
- Verificación suplementaria no oficial (no listada en `CLAUDE.md` §9): `pnpm build` en `apps/web` → build de producción exitoso, único aviso no bloqueante de Rollup por tamaño de chunk (>500kB sin code-splitting).
- Verificación suplementaria ad-hoc: script Playwright desechable (creado y borrado en esta sesión) que crea una evaluación nueva vía UI, agrega 1 requirement funcional (peso 40) + 1 técnico (peso 20), vincula "Proveedor Uno (dev)" vía `VendorCatalogPicker`/`GET /vendor-organizations` real, e inicia la recepción de propuestas → **1/1 passed** contra backend real. Cierra el hallazgo de que el E2E permanente no cubre esos 3 pasos (ver "Deuda" abajo).

**Confirmaciones de código (lectura directa, no solo resultados de test) para el checklist pedido por el founder:**
- Backend gap `GET /vendor-organizations`: `require_role("evaluation_owner","evaluator")`, filtro `re.escape()` en búsqueda, cursor opaco base64 `(name, id)`, `TenantCollection` en el repositorio — aislamiento de tenant estructural, no por convención.
- `PATCH Requirement`: `evaluations/service.py::update_requirement` valida el documento **resultante** (merge existente+patch) antes de persistir, con la misma regla `single_choice`/`multi_choice`↔`options` que `create` — confirmado en el diff línea por línea contra `origin/main`.
- Concurrencia: `AnswerAutosaveController` serializa una escritura a la vez por Proposal (`processing` flag), limpia toda la cola y no reintenta ante un 409 real; botón "Enviar propuesta" deshabilitado mientras `pendingCount>0`; `ScoringPage` envía `Score.version` en cada `PUT` y muestra un banner con botón "Recargar" ante 409.
- Resultados: `ResultsPage` — funcional/40, técnico/20, económico siempre "No disponible" (nunca 0), parcial/60 sin normalizar a 100, leyenda "no es un ranking ni implica adjudicación", diálogo de completar reitera "No se declara ganador".
- Separación buyer/vendor: `router.tsx` usa `BuyerLayout`/`VendorLayout` físicamente distintos con `RequireRole`; `grep` confirma cero imports cruzados entre `features/vendor-portal` y `features/{evaluations,proposals,scoring}`; `vendor_portal/schemas.py` no expone `Score` ni datos de otros proveedores; `e2e/isolation.spec.ts` prueba un 403 real de backend, no solo el redirect de UI.

**Riesgos/deuda conocidos (nuevos de esta sesión + heredados, todos no bloqueantes):**
- **Nuevo:** `e2e/vertical-slice.spec.ts` no cubre "crear evaluación"/"crear requerimientos"/"vincular proveedor" contra backend real de forma reproducible (arranca de datos pre-sembrados). Verificado por otra vía en esta sesión; recomendado ampliar la suite permanente en una futura sesión.
- Heredados (sin cambios): `StarletteDeprecationWarning` de `httpx`/`starlette.testclient`; pre-commit hooks locales fuera de alcance (exclusión documentada, no deuda); bundle de producción sin code-splitting (advertencia de Rollup, no error).

**Estado real de VS-2C: ✅ cerrado formalmente.** Ningún criterio de aceptación abierto. Sin commit (pendiente de decisión del founder).

**Próxima fase según roadmap/backlog — discrepancia reportada, no resuelta unilateralmente:** `roadmap.md` agrupa `AUTH-PROD` bajo "Bloque 0 — Fundación" y dice que se pospuso "hasta después de cerrar VS-2C" (ya ocurrió); `backlog.md` confirma esa dependencia. Pero la Fase 8 (`E3`, inicio de "Bloque 2 — Colaboración y auditoría") también depende únicamente de `VS-2C` en `backlog.md`, sin que ningún documento ordene explícitamente una antes que la otra. El founder debe decidir entre `AUTH-PROD` y Fase 8/E3 — ver la nota completa en `current-phase.md`, sección "Próximos pasos".

**Archivos que debe leer la siguiente sesión:** `docs/development/current-phase.md` (sección VS-2C completa, incl. "Sesión de cierre formal de VS-2C"), esta entrada, `docs/development/backlog.md` (filas `AUTH-PROD` y Fase 8/E3 para decidir cuál sigue), `docs/product/roadmap.md` (nota de secuencia).

**Comandos oficiales para comenzar:** `make dev-up && make seed-dev && make dev` para levantar el entorno; `make test && make test-integration && make test-e2e` para reverificar antes de tocar código nuevo.

**Preguntas todavía abiertas:**
1. ¿El founder comitea VS-2C ahora (y en qué agrupación de commits/PR), o sigue esperando?
2. ¿Cuál es la siguiente fase — `AUTH-PROD` o Fase 8/E3 — dado que ambas solo dependen de VS-2C y ningún documento las ordena entre sí?
3. ¿Se justifica ampliar `vertical-slice.spec.ts` (o agregar un spec nuevo) para cubrir "crear evaluación/requerimientos/vincular proveedor" de forma reproducible, o se acepta el riesgo documentado como está?

### Sesión — 2026-07-28 — VS-2C: frontend del vertical slice de evaluación (cierre del vertical slice)

**Resumen:** Sesión de planeación (Plan Mode) seguida de implementación completa de VS-2C en 5 bloques incrementales, con aprobación explícita del founder para pasar de cada bloque al siguiente. El plan inicial fue rechazado con 11 correcciones concretas (identidad de dev nunca usada para resolver nombres de negocio; el gap de `PATCH Requirement` corregido en **backend**, no solo con validación cliente; estrategia de escritura secuencial explícita para `ProposalAnswer` dado que `Proposal.version` es global; contrato de `GET /vendor-organizations` cerrado con cursor desde el día uno; currency codes derivados del validador real del backend, no inventados; manejo detallado de infraestructura/procesos para `make test-e2e`; confirmar versión de Tailwind/shadcn antes de configurar; edición individual de `display_order` en vez de PATCH-en-cadena pretendiendo atomicidad; confirmaciones UX explícitas en las 4 transiciones irreversibles del flujo; `@hookform/resolvers` para que zod realmente valide vía react-hook-form; preservar el contrato de `/results` por-propuesta ya cerrado en VS-2B). El plan corregido fue aprobado y se implementó completo. Docker estuvo disponible en toda la sesión.

**Dos ajustes de backend, resueltos en Bloque 2/4 antes de construir la UI dependiente:**
1. `GET /api/v1/vendor-organizations` (nuevo endpoint, módulo `identity`) — catálogo de proveedores del tenant para el picker de vinculación, con paginación por cursor implementada desde el día uno (no diferida).
2. `PATCH Requirement` — `evaluations/service.py::update_requirement` ahora valida el documento **resultante** (merge existente+patch), no solo los campos enviados, para la regla `single_choice`/`multi_choice` ↔ `options` no vacío.
3. (Encontrado durante el Bloque 4, no en el plan original) `RequirementScoreDetail` ganó `version`/`comment` en `/results` — sin esto no había forma de leer el `Score.version` necesario para una actualización optimista desde el cliente.

**Archivos tocados (resumen — ver árbol completo en `git status` y en el plan):**
- Backend: `service/procurawise/{evaluations/service.py,evaluations/router.py,identity/{repository,service,router,schemas}.py,scoring/{schemas,service}.py}`; tests nuevos `tests/api/{test_requirement_patch_validation,test_vendor_organizations}.py`, `tests/security/test_tenant_isolation.py` (+1 caso), `tests/api/test_vertical_slice_happy_path.py` (+aserciones de `version`/`comment` en resultados).
- Frontend (nuevo, prácticamente todo `apps/web/src/` fuera de `api/client.ts` generado): `lib/{http,errors,enumLabels,queryClient,answerAutosaveController}.ts`, `actor/{ActorContext,SelectActorPage}.tsx`, `app/{AppShell,router,guards,roleHomePath,...}.tsx`, `components/*` (shadcn copiados + compuestos propios), `features/{evaluations,proposals,scoring,vendor-portal}/**`, `App.integration.test.tsx`, `e2e/{vertical-slice,isolation}.spec.ts`, `playwright.config.ts`, `testUtils/mockFetchRouter.ts`.
- Infraestructura: `apps/web/{orval.config.ts,vite.config.ts,tsconfig*.json,.gitignore}`, `Makefile` (+`test-e2e`), `.github/workflows/integration.yml` (+job `e2e`).

**Resultado de pruebas (verificación final):**
- Frontend: `CI=true pnpm test` → **70 passed** (13 archivos). `pnpm typecheck` → limpio. `pnpm lint` → 0 errores. `pnpm format` → limpio.
- Backend: `make test-backend` → **59 passed**. `make test-integration` (Docker real) → **61 passed**.
- `make test-e2e` → **2 specs Playwright passed**, teardown limpio verificado (`lsof`/`docker ps` vacíos tras la corrida).
- Demo manual de los 13 pasos verificada repetidamente vía Playwright contra backend real; E2E negativo confirma un 403 real de servidor, no solo un redirect de guard de ruta.

**Bugs reales encontrados y corregidos (todos vía verificación contra Docker real o corridas reales de Vitest/Playwright, no por inspección):**
1. Deep-link `?next=` sobrevivía a un cambio de actor hacia un rol incompatible → `isNextPathAllowedForRole`.
2. Respuesta de vendor recién guardada no se reflejaba en UI (el controller no empujaba la respuesta del servidor al cache de React Query) → callback `onDetail` en `AnswerAutosaveController`.
3. Controles de `ScoreInput`/`AnswerField` "rebotaban" entre click y confirmación del servidor → estado de draft local optimista en todos los controles, no solo continuos.
4. 409 auto-infligido al recargar la página de vendor (versión del controller sembrada con placeholder antes de que la query real resolviera) → `useEffect` de resincronización solo cuando el controller está idle sin escrituras pendientes.
5. `make test-e2e` inicialmente usaba `trap 'kill 0'`, matando el propio proceso de `make` (exit 144, `dev-down` corriendo 5 veces) → PIDs capturados + `pkill -f` con regex correcta.
6. Proceso Vite huérfano sobreviviendo en el puerto 5173 tras `make test-e2e` (el patrón `pkill -f` original no matcheaba el comando real) → corregido y re-verificado con `lsof`/`docker ps` limpios.
7. Falta de auto-cleanup de Testing Library entre tests (Vitest no tiene `test.globals`) → `afterEach(() => cleanup())` en `setupTests.ts`, con valor repo-wide.
8. `new Response(...)` colgaba indefinidamente en jsdom dentro del mock de `fetch` → `mockFetchRouter.ts` devuelve objetos planos, no `Response` real.
9. `tenant_ids()` en tests de backend etiqueta tenants por orden alfabético de UUID, sin relación con el slug del seed → tests de `vendor-organizations` corregidos para no asumir esa correspondencia.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):** Ninguna nueva de arquitectura (CLAUDE.md §3 solo exige ADR para monolito/DB/hosting/comunicación) — todas las decisiones de este bloque son de implementación bajo ADRs ya aprobados (0006 shadcn/Tailwind, 0007 orval+react-query, 0017 SPA React).

**Deuda técnica introducida:** Ninguna nueva. Se **cerró** deuda previa: `orval.config.ts` ahora genera hooks de React Query (ya no `client: 'fetch'`), tal como especificaba ADR 0007 desde Fase 1A.

**Instrucciones para la siguiente sesión:**
- **El vertical slice queda cerrado end-to-end.** No repetir VS-2A/VS-2B/VS-2C.
- Decidir si se comitea VS-2C (ningún commit se hizo en esta sesión) — mismo patrón que sesiones anteriores, se espera aprobación explícita del founder.
- Siguiente paso de código sugerido: `AUTH-PROD` (sustituye `DevelopmentIdentityProvider`) o E3 (`audit`/RBAC completo) — ver `docs/development/backlog.md` para el orden de dependencias.
- No tocar: IA (E5), billing (E11), infraestructura Azure real (Fase 27) — todas muy posteriores en el roadmap.

### Sesión — 2026-07-27 — VS-2B: núcleo backend de evaluaciones, proveedores, propuestas y scoring

**Resumen:** Sesión de planeación (Plan Mode) seguida de implementación completa de VS-2B, ambas en la misma sesión con aprobación explícita del founder para pasar de una a otra. El plan inicial fue rechazado por el founder con 8 correcciones concretas de arquitectura/concurrencia (ver detalle abajo); el plan corregido fue aprobado y se implementó en los 5 bloques planeados. Docker estuvo disponible, así que se verificó contra Mongo real en la misma sesión (no quedó pendiente para una sesión futura, a diferencia de VS-2A).

**Rechazo del plan inicial y correcciones del founder (antes de escribir código):**
1. Eliminar `evaluation_vendors` como colección independiente — `Proposal` es la asociación Evaluation↔VendorOrganization.
2. Resolver la carrera del límite de 6 proveedores con protección atómica (no `count_documents`+insert).
3. Agregar optimistic concurrency (`version`/`expected_version`) a `Proposal`, no solo a `Score`.
4. Corregir el umbral de `mandatory_alert` de "score 0-1" a "score<5".
5. Definir validación concreta por `response_type`, incluyendo `currency`, excluyendo `file`/`structured_table`.
6. `start-collection` debe exigir al menos un requirement `functional` y uno `technical`, no solo pesos correctos.
7. `GET /results` debe separar propuestas `draft`/`submitted` y funcionar en `evaluating`+`completed`.
8. Matriz de pruebas ampliada con casos específicos de concurrencia (vinculación de vendors, versión de Proposal).

Las 8 correcciones se incorporaron al plan, que fue re-presentado y aprobado.

**Decisión tomada durante la implementación, no en el plan — ✅ aprobada explícitamente por el founder en el turno siguiente de esta misma sesión:** el shape de `GET /results` aprobado por el founder en la sesión de planeación anterior tenía `functional`/`technical`/`economic`/`partial_result` como un único objeto a nivel de evaluación. Al implementar se detectó que esto es matemáticamente incoherente en cuanto hay más de una `Proposal` — cada vendor tiene su propio conjunto de `Score`, sumarlos cruzando propuestas no representa nada válido. Se movieron esos campos, junto con el detalle de scores por requirement, a **dentro de cada entrada de `proposals[]`** en vez de a nivel de evaluación, sin cambiar nombres/unidades de los campos. El founder confirmó: *"functional, technical, economic, partial_result y requirement_scores deben existir dentro de cada proposal, porque cada proveedor tiene su propio resultado"*. Contrato cerrado, sin acción pendiente.

**Archivos tocados (resumen — ver árbol completo en el plan y en `git status`):**
- Nuevos: `service/procurawise/{evaluations,proposals,vendor_portal,scoring}/*`, `service/migrations/0002_evaluations_proposals_scoring_indexes.py`, `service/tests/{unit/test_evaluation_models,unit/test_proposal_models,unit/test_score_model,unit/test_answer_validators,integration/test_vendor_link_concurrency,integration/test_proposal_version_concurrency,security/test_vendor_isolation,api/test_vertical_slice_happy_path}.py`.
- Modificados: `service/procurawise/api/main.py` (4 routers nuevos montados), `service/procurawise/dev_seed.py` (evaluación+propuesta de ejemplo), `service/procurawise/identity/repository.py` (`VendorOrganizationRepository.find_by_id` agregado), `service/procurawise/shared/context.py` (`require_role` nuevo), `service/tests/conftest.py` (fixtures `seeded_actors`/`client` y helpers movidos aquí desde `test_tenant_isolation.py` para reutilizarse en los archivos de test nuevos), `service/tests/security/test_tenant_isolation.py` (imports ajustados a los helpers movidos, sin cambios de comportamiento), `apps/web/openapi.json`, `apps/web/src/api/client.ts`.

**Resultado de pruebas (primera corrida, antes del fix de whitespace descrito abajo):**
- `make lint` → verde.
- `make typecheck` → verde (mypy 0 errores, `tsc -b` sin errores).
- `make test-backend` → 59 passed, 47 deselected.
- `make test-integration` (Docker real) → **47 passed**, incluye concurrencia real con threads (límite de 6 proveedores bajo 10 intentos concurrentes, edición de `Proposal` concurrente con misma `expected_version`).
- `make test` (backend+frontend) → verde.
- `make contracts` → regenerado sin errores; `git diff --check` señalaba trailing whitespace en `client.ts` — investigado y corregido en el mismo turno de sesión, ver subsección siguiente.

#### Corrección del trailing whitespace en `apps/web/src/api/client.ts` (mismo día, a pedido explícito del founder)

El founder pidió no aceptar `git diff --check` fallando como estado final y determinar la causa raíz antes de cerrar VS-2B.

**Diagnóstico:** corriendo `make contracts` dos veces seguidas y comparando el archivo resultante byte a byte, se confirmó que el trailing whitespace **es regenerado de forma determinista en cada corrida** por el propio template del cliente `fetch` de `orval` 7.21.0 (no es un artefacto congelado de una corrida anterior, no depende del `openapi.json` de entrada, no es aleatorio). `.prettierignore` excluía `src/api`, así que nunca se limpiaba.

**Solución:** se activó la opción nativa `output.prettier: true` de `orval` (confirmada leyendo el código fuente del paquete instalado — ejecuta `prettier --write` sobre cada archivo generado inmediatamente después de escribirlo) en `apps/web/orval.config.ts`, y se quitó `src/api` de `apps/web/.prettierignore` para que Prettier deje de ignorarlo. Es el mecanismo oficial de integración prettier↔orval, no un postproceso ad-hoc — se prefirió sobre escribir un script de limpieza manual porque además deja a `pnpm format`/`make lint-frontend` vigilando el archivo generado en cada PR futuro, no solo en el momento de generarlo.

**Verificación de reproducibilidad (pedida explícitamente):**
- `make contracts` → `git diff --check` → verde (exit 0).
- `make contracts` (2ª corrida consecutiva) → archivo idéntico byte a byte a la 1ª corrida → `git diff --check` → verde (exit 0).
- `make lint` → verde (incluye `pnpm format` ahora cubriendo `src/api/client.ts`).
- `make typecheck` → verde.
- `make test` → verde (59 passed backend + 1 passed frontend).
- `make test-integration` → **47 passed** (Docker real).

**Archivos tocados por esta corrección:** `apps/web/orval.config.ts`, `apps/web/.prettierignore`, `apps/web/src/api/client.ts` (regenerado). Ningún contrato de API ni lógica de VS-2B cambió.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):** la desviación de `/results` (por-propuesta vs. agregado único), ✅ aprobada por el founder — candidata a documentarse formalmente como ADR corto si se quiere dejar registro fuera de este handoff. El resto de decisiones (reserva atómica de vendors, `version` optimista en Proposal, catálogo de `response_type`, `output.prettier: true` en orval) ya fueron decisiones explícitas del founder o correcciones directamente pedidas durante la sesión, no ad-hoc silenciosas.

**Deuda técnica introducida:** Ninguna nueva. La ventana de inconsistencia aceptada en `linked_vendor_count` tras un fallo entre `delete_one` y el `$inc` de liberación (documentada en el plan, riesgo aceptado explícitamente para VS-2B) es un riesgo de diseño conocido, no deuda no documentada.

**Instrucciones para la siguiente sesión:**
- Contrato de `GET /results` cerrado — sin acción pendiente.
- `git diff --check` queda verde de forma reproducible (mecanismo `output.prettier: true` de orval, no un parche puntual) — no debería volver a fallar tras futuras corridas de `make contracts`, pero si algún día orval deja de respetar esa opción, revisar primero `orval.config.ts` antes de tocar `client.ts` a mano.
- Decidir si se comitea VS-2B (y VS-2A, que tampoco está comiteado todavía) — ningún commit se hizo en esta sesión, instrucción implícita de esperar aprobación del founder como en sesiones anteriores.
- Siguiente paso de código: **VS-2C — Frontend del vertical slice**, en una sesión separada.
- No tocar: auth productiva (`AUTH-PROD`).

### Sesión — 2026-07-27 — VS-2A: fix de prueba no determinista detectada por el workflow Integration del PR

**✅ Corrección puntual, sin tocar código de producción.** Alcance acotado por el founder: corregir exclusivamente el fallo no determinista que el workflow `Integration` de GitHub Actions detectó en el PR de VS-2A (commit `93c4e43`, ya comiteado y pusheado por el founder entre sesiones), sin iniciar VS-2B ni comitear.

**Fallo encontrado (exclusivo de CI):** `tests/security/test_tenant_isolation.py::test_vendor_contact_me_resolves_vendor_org_id` falló con `KeyError` en el workflow `Integration` del PR — no reproducía siempre en local porque depende del orden relativo de dos UUID aleatorios generados en cada corrida.

**Causa raíz:** el helper `_tenant_ids()` etiqueta "tenant_a"/"tenant_b" según el **orden alfabético de sus UUID aleatorios** (`sorted(tenants)`), una etiqueta sin significado semántico — no corresponde a cuál tenant es `dev-tenant-a` vs `dev-tenant-b` en `dev_seed.py`. La prueba `test_vendor_contact_me_resolves_vendor_org_id` asumía incorrectamente que "tenant_a" (el que ordena primero por UUID) es siempre el tenant que tiene la membership `vendor_contact` — pero esa membership solo existe en el tenant semántico `dev-tenant-a` del seed, cuyo UUID puede ordenar antes o después del de `dev-tenant-b` en cada corrida. Cuando `dev-tenant-b` resultaba ser el que ordenaba primero, `seeded_actors[(tenant_a, "vendor_contact")]` no existía → `KeyError`. Se revisaron los otros 3 usos de `_tenant_ids()` (`test_owner_me_resolves_own_tenant_and_role`, `test_dev_actor_from_tenant_a_and_tenant_b_resolve_to_different_tenants`, `test_dev_identity_disabled_outside_development`): todos seleccionan el rol `evaluation_owner`, presente en **ambos** tenants del seed, por lo que no tienen la misma falla — no requirieron cambios.

**Corrección aplicada:** nuevo helper `_unique_actor_by_role(seeded_actors, role)` en `test_tenant_isolation.py` que busca directamente, por rol, la(s) entrada(s) de `seeded_actors` y afirma que existe exactamente una — falla ruidosamente (con `assert` explícito) en vez de escoger un actor arbitrario si el seed cambiara. `test_vendor_contact_me_resolves_vendor_org_id` ahora usa este helper para resolver `(tenant_id, membership_id)` del `vendor_contact` sin depender de orden de UUID, orden de inserción de diccionario, ni orden de Mongo. Se aprovechó para además afirmar `body["tenant_id"] == vendor_tenant_id` (aserción nueva, no se debilitó ninguna existente). No se fijaron UUID estáticos ni se tocó `dev_seed.py` ni ningún código de producción — la evidencia apuntaba únicamente a un defecto en la prueba.

**Archivos tocados:**
- `service/tests/security/test_tenant_isolation.py` — nuevo helper `_unique_actor_by_role`, docstring aclaratorio en `_tenant_ids()`, `test_vendor_contact_me_resolves_vendor_org_id` reescrita para seleccionar por rol.
- `docs/development/session-handoff.md` (este archivo) — nueva entrada.
- `docs/development/current-phase.md` — nota agregada sobre el hallazgo real de CI (ver su propia entrada).

**Resultado de pruebas:**
- `make lint` → verde (ruff check + format tras `ruff format .`; ESLint/Prettier frontend).
- `make typecheck` → verde (mypy 0 errores; `tsc -b` sin errores).
- `make test` → verde, 27 passed backend + 1 passed frontend.
- `make test-integration` → verde, **32 passed**, 0 fallos (Docker disponible en esta sesión).
- Prueba afectada corrida 5 veces seguidas para demostrar ausencia de flakiness: `cd service && for i in 1 2 3 4 5; do uv run pytest tests/security/test_tenant_isolation.py -m docker -x -q; done` → **5/5 corridas, 8/8 casos cada una, todas en verde** (`8 passed` en cada corrida).
- `make contracts` → regenerado sin diff (el working tree ya reflejaba el commit `93c4e43`; `git diff --stat` solo muestra el archivo de test tocado en esta sesión).
- `git diff --check` → limpio (exit 0). El hallazgo de whitespace en `client.ts` reportado en la sesión anterior ya forma parte del commit `93c4e43` (baseline actual), no aparece como diff nuevo en esta sesión.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):** Ninguna.

**Deuda técnica introducida:** Ninguna.

**Instrucciones para la siguiente sesión:**
- Este fix queda sin comitear (instrucción explícita del founder) — decide si lo comitea antes o junto con el siguiente trabajo.
- Siguiente paso de código: **VS-2B — Flujo backend del vertical slice**, en una sesión separada.
- No tocar: frontend (VS-2C), auth productiva (`AUTH-PROD`).
- La advertencia `StarletteDeprecationWarning` (httpx/Starlette) sigue fuera de alcance, no se tocó.

### Sesión — 2026-07-27 — VS-2A: corrección de bug real encontrado en validación con Docker

**✅ VS-2A queda verificado con Docker real tras corregir un bug encontrado en la primera corrida de `make test-integration`.** Sesión de alcance estrictamente acotado por el founder: corregir exclusivamente el fallo observado, sin iniciar VS-2B ni hacer commit.

**Resumen:** `make test-integration` (con Docker real, Mongo+Azurite) falló en `test_update_one_replacement_forces_resolved_tenant_id`: PyMongo rechaza `Collection.update_one()` cuando el documento de actualización no tiene operadores `$` (un reemplazo completo debe ir por `Collection.replace_one()`). `TenantCollection.update_one` no distinguía esto — enviaba tanto operaciones `$set`/`$unset` como reemplazos completos al mismo método del driver. Se corrigió detectando la forma del `update` recibido (operador, reemplazo, o mezcla de ambos —rechazada como caso nuevo) y enrutando cada uno al método correcto de PyMongo, preservando intactas todas las protecciones de tenant ya existentes (filtro siempre resuelto, `tenant_id` nunca alterable, documento del caller nunca mutado).

**Archivos tocados:**
- `service/procurawise/shared/tenant_collection.py` — `update_one` ahora distingue actualización por operador (vía `Collection.update_one`) de reemplazo completo (vía `Collection.replace_one`); rechaza documentos que mezclan claves `$` con campos planos.
- `service/tests/integration/test_tenant_collection.py` — ampliado de 9 a 19 casos: `$set` válido, reemplazo válido con/sin `tenant_id` explícito coincidente, reemplazo con `tenant_id` distinto rechazado, documento mixto rechazado sin tocar la base, documento de entrada no mutado, filtro con colisión de `tenant_id` rechazado (vía `update_one`), intento cross-tenant sin efecto tanto por operador como por reemplazo, `upsert` sin escape de tenant tanto por operador como por reemplazo.
- `docs/development/current-phase.md` — estado de VS-2A actualizado a verificado con Docker real; nueva sub-sección "Fallo real encontrado y corregido".
- `docs/development/session-handoff.md` (este archivo) — nueva entrada.

**Resultado de pruebas:**
- `make lint` → verde (ruff check + format, backend y frontend).
- `make typecheck` → verde (mypy 0 errores; `tsc -b` sin errores).
- `make test` → verde, 27 passed backend + 1 passed frontend.
- `make test-integration` → verde, **32 passed** (0 fallos) — incluye las 19 pruebas nuevas/ampliadas de `test_tenant_collection.py` y las 8 de `test_tenant_isolation.py` (sin cambios, ya pasaban).
- `make contracts` → regenerado sin diff de contenido (`git diff --exit-code` sobre `apps/web/src/api/client.ts` limpio, que es el gate real de `ci/contracts`).
- `git diff --check` → reporta trailing whitespace dentro de comentarios JSDoc autogenerados por `orval` en `apps/web/src/api/client.ts` (14 líneas ya presentes en `HEAD` antes de esta sesión, ahora 28 por los nuevos endpoints de VS-2A con docstring multilínea). **No corregido deliberadamente**: es un archivo generado (se sobreescribiría en el próximo `make contracts`), no forma parte del bug corregido, y CI no usa `git diff --check` para este archivo — usa `git diff --exit-code`, que sí pasa limpio.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):** Ninguna.

**Deuda técnica introducida:** Ninguna. El whitespace de `client.ts` es preexistente al proyecto (característica del generador `orval`), no deuda nueva.

**Instrucciones para la siguiente sesión:**
- VS-2A está completo y verificado. El founder decide si comitea (no se hizo ningún commit en esta sesión ni en la anterior).
- Siguiente paso de código: **VS-2B — Flujo backend del vertical slice**, en una sesión separada.
- No tocar: frontend (VS-2C), auth productiva (`AUTH-PROD`).

### Sesión — 2026-07-27 — VS-2A: Dominio, identidad de desarrollo y aislamiento

**🔄 VS-2A — Implementado, pendiente de verificación con Docker (no disponible en esta sesión).** Precedida por una sesión de planeación en Plan Mode (mismo día) que dividió el vertical slice de Fase 2 en `VS-2A`/`VS-2B`/`VS-2C` (más `AUTH-PROD` pospuesto) y resolvió 10 ajustes de diseño exigidos por el founder tras revisar el plan: identidad de desarrollo por `Membership` (no `user_id`), reglas estrictas de `TenantCollection`, mass assignment con `extra="forbid"`, separación física estricta del router de proveedor, IDs de backlog no ambiguos, enums internos en inglés, reglas de estado explícitas, snapshot como fuente de verdad del scoring, pre-commit fuera de alcance, y estrategia de IDs UUID string consistente. Esta sesión implementó exactamente ese plan ya ajustado.

**Resumen:** Primer código de dominio real del proyecto. Se creó el bounded context `identity` (`Tenant`/`User`/`Membership`/`VendorOrganization`), el wrapper `TenantCollection` con reglas de rechazo estrictas (nunca solo un filtro por convención — se prueban 9 casos negativos), el `DevelopmentIdentityProvider` (header `X-Dev-Membership-Id`, gateado a `environment in (local, test)`), `make seed-dev`/`seed-reset`, y la primera migración real de índices. Se montaron 2 endpoints nuevos bajo `/api/v1` (`/dev/actors`, `/me`) y se regeneraron los contratos OpenAPI/orval. No se implementó VS-2B ni VS-2C — quedan para sesiones futuras separadas, tal como exige el plan.

**Archivos tocados:**
- `service/procurawise/identity/` (nuevo paquete) — `models.py`, `repository.py`, `service.py`, `dev_provider.py`, `router.py`, `schemas.py`.
- `service/procurawise/shared/tenant_collection.py` (nuevo) — `TenantCollection`/`TenantScopeError`.
- `service/procurawise/shared/context.py` (nuevo) — `ActorContext`.
- `service/procurawise/shared/api_models.py` (nuevo) — `APIModel` (`extra="forbid"`, base de todo schema de escritura futuro).
- `service/procurawise/shared/mongo.py` — agrega `get_database(settings)`.
- `service/procurawise/api/main.py` — monta `identity_router` bajo `/api/v1`.
- `service/procurawise/dev_seed.py` (nuevo) — `seed()`/`reset()`, invocado por `make seed-dev`/`make seed-reset`.
- `service/migrations/0001_identity_indexes.py` (nuevo) — primera migración real (antes el runner era no-op).
- `Makefile` — targets `seed-dev`, `seed-reset` (patrón `CONFIRM=yes` igual que `dev-reset`).
- `service/pyproject.toml` — `[tool.ruff.lint.flake8-bugbear] extend-immutable-calls = ["fastapi.Depends", "fastapi.Header"]` (evita falso positivo B008 de ruff contra el patrón de inyección de dependencias de FastAPI, ya usado en `identity/dev_provider.py` y `identity/router.py`).
- `service/tests/unit/test_identity_models.py`, `service/tests/unit/test_dev_provider.py` (nuevos, verificados en verde).
- `service/tests/integration/test_tenant_collection.py` (nuevo, 9 casos, `@pytest.mark.docker`).
- `service/tests/security/` (paquete nuevo) `test_tenant_isolation.py` (nuevo, 8 casos, `@pytest.mark.docker`).
- `apps/web/openapi.json` (no versionado, gitignored) y `apps/web/src/api/client.ts` — regenerados vía `make contracts`.
- `docs/development/current-phase.md`, `docs/development/session-handoff.md` (este archivo), `docs/development/backlog.md`, `docs/product/roadmap.md` — actualizados con la restructuración de IDs (`VS-2A`/`VS-2B`/`VS-2C`/`AUTH-PROD`) y el estado de VS-2A.

**Resultado de pruebas:**
- `uv run ruff check .` → verde. `uv run ruff format --check .` → verde (tras agregar `extend-immutable-calls`).
- `uv run mypy procurawise` → verde, 0 errores (27 archivos).
- `uv run pytest -m "not docker"` → **27 passed**, 23 deselected (marcador `docker`). Incluye los tests nuevos de `identity`/`dev_provider`.
- `python -m procurawise.api.export_openapi` + `pnpm contracts` (orval) → regenerado sin errores; `pnpm lint`/`pnpm typecheck`/`pnpm format` en `apps/web` → verdes tras la regeneración.
- **No ejecutado en esta sesión** (Docker no disponible en el entorno): `make test-integration` — cubre `tests/integration/test_tenant_collection.py` (9 casos) y `tests/security/test_tenant_isolation.py` (8 casos), además de `make seed-dev`/`make migrate` contra Mongo real. Queda como verificación pendiente, mismo patrón que la Fase 1B (verificación en dos rondas).

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):**
- Ninguna nueva — todas las decisiones de diseño de VS-2A ya habían sido resueltas explícitamente en la sesión de planeación previa (10 ajustes del founder) y no tocan ninguna de las áreas que `CLAUDE.md` §3 reserva para ADR (monolito, DB, hosting, patrón de comunicación).

**Deuda técnica introducida:**
- Ninguna nueva. Pre-commit sigue fuera de alcance (exclusión de alcance documentada, no deuda). La verificación con Docker real queda pendiente (ver "Resultado de pruebas") — no es deuda, es el siguiente paso obligatorio antes de considerar VS-2A formalmente cerrado.

**Instrucciones para la siguiente sesión:**
- Primero: correr `make dev-up && make migrate && make seed-dev && make test-integration` y confirmar en verde las 17 pruebas Docker nuevas (9 de `test_tenant_collection.py` + 8 de `test_tenant_isolation.py`). Revisar la tabla de actores que imprime `seed-dev`.
- Si todo pasa, el founder decide si comitea VS-2A (no se comiteó nada en esta sesión) y luego abre una sesión nueva para **VS-2B — Flujo backend del vertical slice**.
- No tocar todavía: frontend (VS-2C), auth productiva (`AUTH-PROD`), ni ninguna lógica de `evaluations`/`vendors`/`proposals`/`scoring` (eso es VS-2B).

### Sesión — 2026-07-18 — Fase 1C: Integración continua y seguridad de pipeline (cierre de Fase 1 — Fundación técnica)

**✅ Fase 1C — Completed (redefinida).** Planeada en Plan Mode (2 preguntas bloqueantes resueltas vía `AskUserQuestion`: alcance acotado a CI/CD + seguridad de pipeline, sin pre-commit ni bounded contexts; repo asumido privado sin GitHub Advanced Security) y aprobada por el founder. Implementada y verificada localmente en la misma sesión. **Fase 1 — Fundación técnica queda formalmente cerrada** a nivel de código local; falta únicamente que el founder autorice el primer push para verificar los workflows contra GitHub real.

**Resumen:** Se agregaron 3 workflows de GitHub Actions (`ci.yml`, `integration.yml`, `security.yml`) que reutilizan exactamente los comandos `make`/`pnpm` ya existentes — para eso el `Makefile` se descompuso en targets granulares por lado (backend/frontend) sin cambiar el comportamiento de los targets compuestos. Se agregó `pytest-cov` (cobertura medida y mostrada, sin umbral global). Seguridad de pipeline: `gitleaks` (secret scanning, bloqueante) corriendo como binario descargado y verificado por checksum (no la Action wrapper, por ambigüedad de licenciamiento en repos privados), `pip-audit`+`pnpm audit` (dependency scanning, informativo por ahora) y `Dependabot` para `pip`/`npm`/`github-actions`. Todas las Actions de terceros quedaron pinneadas por SHA completo, obtenido y verificado contra la API de GitHub (no inventado). Nada de esto se comiteó ni se hizo push — queda en el working tree a criterio del founder.

**Archivos tocados:**
- `.github/workflows/ci.yml` (nuevo) — jobs `backend` (ruff, mypy, `pytest -m "not docker"` con cobertura), `frontend` (ESLint, Prettier, `tsc`, Vitest, `vite build`), `contracts` (regenera y verifica que `apps/web/src/api/client.ts` no esté desactualizado, ver ADR 0007).
- `.github/workflows/integration.yml` (nuevo) — `make test-integration` contra Mongo+Azurite reales; diagnóstico de Docker solo si falla; `make dev-down` con `if: always()`.
- `.github/workflows/security.yml` (nuevo) — `secret-scan` (gitleaks, bloqueante), `python-deps` (pip-audit, informativo), `frontend-deps` (pnpm audit, informativo); trigger `schedule` semanal además de PR/push/`workflow_dispatch`.
- `.gitleaks.toml` (nuevo) — allowlist para `UseDevelopmentStorage=true` y la clave pública conocida de Azurite (verificado que gitleaks no los marca ni con ni sin el allowlist — queda como protección documentada a futuro).
- `.github/dependabot.yml` (nuevo) — ecosistemas `pip` (`/service`), `npm` (`/apps/web`), `github-actions` (`/`), semanal, agrupando actualizaciones menores/patch.
- `Makefile` — nuevos targets granulares `lint-backend`/`lint-frontend`, `typecheck-backend`/`typecheck-frontend`, `test-backend`/`test-frontend`; `lint`/`typecheck`/`test` ahora los invocan en secuencia (comportamiento idéntico, verificado).
- `service/pyproject.toml` — `pytest-cov>=6.0` en `dependency-groups.dev`; `addopts` con `--cov=procurawise --cov-report=term-missing --cov-report=xml`; `[tool.coverage.run] source = ["procurawise"]`.
- `service/uv.lock` — regenerado vía `uv sync` (agrega `pytest-cov` y `coverage`).
- `apps/web/package.json` — `packageManager: "pnpm@9.15.9"` (coincide con `lockfileVersion: '9.0'` de `pnpm-lock.yaml`), `engines.node: ">=22 <23"` (confirmado `node -v` → v22.11.0 en esta sesión). **Nota:** el `pnpm` de corepack en esta máquina falló (error de verificación de firma al intentar instalar 9.x, error de import dinámico con la 11.x cacheada) — se usó `npx pnpm@9.15.9` como workaround para validar localmente; el founder debería revisar por qué corepack está roto en su entorno, aunque no bloquea el CI (que instala pnpm de forma independiente vía `pnpm/action-setup`).
- `.gitignore` — agrega `.coverage`, `coverage.xml`.
- `README.md` — nueva sección "Integración continua"; "Estado del proyecto" actualizado a Fase 1 completa; nota de reubicación de pre-commit/bounded contexts a `identity`.
- `docs/development/current-phase.md` — Fase 1 marcada `✅ Completed`; Fase 1C redefinida y cerrada; criterios de aceptación/pruebas actualizados con los resultados de esta sesión; nueva sección "Cierre de Fase 1C" reemplaza "Condiciones para iniciar Fase 1C".
- `docs/development/session-handoff.md` (este archivo) — nueva entrada.
- `docs/security/threat-model.md`, `docs/operations/deployment.md`, `docs/development/backlog.md` — actualizados, ver sus propias entradas de esta sesión más abajo en cada archivo si aplica (o el resumen en `current-phase.md`).

**Resultado de pruebas:**
- `make lint-backend` → verde (ruff check + format). `make typecheck-backend` → verde (mypy, 16 archivos).
- `make lint-frontend` (vía `npx pnpm@9.15.9`) → verde (ESLint + Prettier). `make typecheck-frontend` → verde (`tsc -b`).
- `make test-backend` → verde, **19 passed, 5 deselected**, cobertura 64% mostrada en log + `coverage.xml` generado.
- `make test-frontend` → verde, 1 passed. `pnpm build` → verde, build de producción generado sin problemas de binding nativo de Rolldown (Vite resolvió a 6.4.3, esbuild-based).
- `make contracts` → verde, sin diff en `apps/web/src/api/client.ts` (ya estaba al día).
- `make test-integration` (Docker real) → verde, **5/5 pruebas Docker pasaron** (Mongo 2/2, Blob 2/2, `/health/ready` arriba). `make dev-down` → verde, sin contenedores activos después.
- `actionlint .github/workflows/*.yml` → sin errores.
- `gitleaks detect --source . --config .gitleaks.toml --redact` → **sin hallazgos** (ídem sin el allowlist — las reglas default no marcan los valores conocidos de Azurite).
- `pip-audit` (vía `uv export` + `uvx pip-audit@2.10.1`) → **sin vulnerabilidades conocidas**.
- `pnpm audit` → **3 hallazgos** (1 high, 2 moderate), todos transitivos dentro de la cadena de `orval` (herramienta de generación de código, no código de producción) sin fix disponible todavía — confirma en la práctica que la política "informativo, no bloqueante" definida para esta fase es la correcta.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):**
- Ninguna decisión arquitectónica — elección de herramientas de CI/seguridad de pipeline, no de arquitectura (CLAUDE.md §3 solo exige ADR para monolito/DB/hosting/comunicación). No requiere ADR.
- Redefinición del alcance de Fase 1C (solo CI/CD + seguridad de pipeline, sin pre-commit ni bounded contexts) — decisión operativa de secuenciación, resuelta vía `AskUserQuestion` con el founder antes de planear, documentada en `current-phase.md`.
- Repo asumido privado sin GitHub Advanced Security (no se pudo verificar con `gh` CLI, no instalado en el entorno) — decisión de diseño de seguridad conservadora, resuelta vía `AskUserQuestion`, revisitar si cambia la visibilidad del repo o se adquiere GHAS.
- `gitleaks` como binario descargado directo (con verificación de checksum SHA-256) en vez de la Action wrapper `gitleaks/gitleaks-action`, para evitar cualquier ambigüedad de licenciamiento de esa Action en repos privados.

**Deuda técnica introducida:**
- **`security / python-deps` y `security / frontend-deps` son informativos, no bloqueantes** — aceptado deliberadamente para esta fase (ver `threat-model.md`); revisar política de bloqueo en Fase 26 (Hardening), cuando haya bandwidth para triage regular de CVEs transitivos.
- **CodeQL no implementado** — repo privado sin GHAS no lo soporta gratis; documentado en `threat-model.md` como mejora disponible si el repo se hace público o se adquiere GHAS.
- **`corepack` roto en la máquina de esta sesión** para instalar pnpm 9.x/11.x (error de firma / import dinámico) — no bloqueó el trabajo (se usó `npx pnpm@9.15.9`), pero el founder debería investigarlo si le ocurre lo mismo en su entorno habitual de desarrollo.
- **Verificación contra GitHub real pendiente** — todo lo de esta sesión está validado localmente (`actionlint`, `gitleaks`, `pip-audit`, `pnpm audit`, todos los `make` relevantes) pero no se ha hecho push ni abierto un PR real; eso es intencional (acción con efectos externos que requiere autorización explícita del founder, fuera del alcance que esta sesión toma por sí sola) y queda como el paso inmediato de la próxima sesión/acción del founder.

**Instrucciones para la siguiente sesión / founder:**
- Revisar el diff completo de esta sesión (`git status`/`git diff`), decidir si comitea y hace push.
- Al hacer push, confirmar en GitHub que los 5 checks bloqueantes (`ci / backend`, `ci / frontend`, `ci / contracts`, `integration / integration`, `security / secret-scan`) quedan en verde en un PR real, y aplicar manualmente la branch protection recomendada en el plan de Fase 1C.
- Ejecutar la sub-fase **`identity`**: `Tenant`/`User`/`Membership` + `TenantCollection` + middleware de `tenant_id`, incluyendo al inicio pre-commit hooks locales y los 15 subpaquetes vacíos de bounded contexts (movidos aquí desde la Fase 1C original). No repetir el trabajo de Fase 1A/1B/1C.
- No tocar todavía: lógica de dominio más allá de los subpaquetes vacíos, auth real, IA, pagos, despliegue a Azure.

---

### Sesión — 2026-07-17 — Fase 1B: Infraestructura local de desarrollo

**✅ Fase 1B — Completed.** Código completo y verificado, incluyendo validación con Docker real del founder en dos rondas: la primera encontró un defecto real (incompatibilidad de versión de API de Blob Storage), la segunda —tras el fix— confirmó las 5 pruebas Docker en verde. Ver "Actualización — ronda 1" y "Actualización — ronda 2 (✅ éxito, cierre de fase)" al final de esta entrada.

**Resumen:** Ejecutada la Fase 1B (planeada en Plan Mode y aprobada en la misma sesión, tras resolver 3 contradicciones con la documentación previa vía `AskUserQuestion`): entorno local reproducible para API y worker con MongoDB Community + Azurite vía Docker Compose, configuración tipada por ambiente, adaptadores de Mongo/Blob/cola, health checks de dependencias, logging estructurado, y pruebas de integración. El alcance original de "Fase 1B" en `current-phase.md` (que incluía además pre-commit, CI y 15 bounded contexts) se acotó explícitamente por el founder a una **Fase 1C** nueva — ver nota de sub-división en `current-phase.md`.

**Archivos tocados:**
- `docker-compose.yml` (nuevo) — Mongo Community `7.0.14` + Azurite `3.33.0` (blob), volúmenes nombrados, healthchecks, sin Redis/Mailhog.
- `service/procurawise/shared/config.py` — `Settings` ampliada (Mongo/Storage/`queue_backend`), valida `queue_backend=memory` prohibido en `production`.
- `service/procurawise/shared/{logging,mongo,storage,messaging,health,migrations}.py` (nuevos) — logging JSON estructurado, cliente Mongo, adaptador `AzureBlobStorage`, `InMemoryMessageBus` (`MessageBus` Protocol), health checks, runner de migraciones idempotente.
- `service/migrations/` (nuevo, vacío) — scaffold para migraciones numeradas futuras.
- `service/procurawise/api/routers/health.py` (nuevo) + `api/main.py` — `GET /health/live` y `GET /health/ready` reemplazan el `/health` plano de Fase 1A.
- `service/procurawise/worker/main.py` — logging estructurado + `InMemoryMessageBus` instanciado (sin dispatch table real todavía).
- `service/tests/conftest.py` (nuevo) — fixtures `mongo_test_db`/`blob_test_storage` con limpieza.
- `service/tests/unit/{test_config,test_logging,test_messaging,test_storage}.py` — nuevos/ampliados (`test_storage.py` y los casos de `storage_api_version` en `test_config.py` se agregaron en la actualización posterior a la validación con Docker del founder, ver abajo).
- `service/tests/integration/{test_health,test_health_ready_down,test_health_ready_up,test_mongo_client,test_blob_storage}.py` — nuevos/ajustados; los 3 últimos marcados `@pytest.mark.docker`.
- `service/pyproject.toml` — deps `pymongo`, `azure-storage-blob`; marker `docker` registrado.
- `Makefile` — `make dev-up/down/logs/status/reset`, `make test-integration`, `make migrate`; `make test` ahora filtra `-m "not docker"`.
- `.env.example` — variables no sensibles nuevas (`MONGODB_URI`, `STORAGE_CONNECTION_STRING=UseDevelopmentStorage=true`, `QUEUE_BACKEND=memory`, etc.).
- `docs/architecture/decisions/0020-composicion-servicios-desarrollo-local.md` (nuevo ADR).
- `docs/architecture/decisions/0005-worker-asincrono-service-bus.md` — nota de referencia a ADR 0020 (sin cambiar `Estado`).
- `docs/architecture/architecture.md` (§4, §7, §9) — cola local `InMemoryMessageBus`, compose sin Redis/Mailhog.
- `docs/operations/deployment.md` — fila "Local" y línea de Service Bus actualizadas.
- `docs/development/current-phase.md` — cierre de Fase 1B (estado final `Completed` tras validación con Docker real, ver actualizaciones abajo) + Fase 1C en `Planned / Not Started`.
- `README.md` — instrucciones locales, comandos y endpoints de health actualizados.
- `apps/web/src/App.tsx` — `fetch('/health')` → `fetch('/health/live')` (el `/health` plano dejó de existir).
- `apps/web/openapi.json`, `apps/web/src/api/client.ts` — regenerados vía `make contracts` para reflejar `/health/live`/`/health/ready`.

**Resultado de pruebas:**
- `uv sync` (nuevas deps `pymongo`, `azure-storage-blob`) → ok.
- `make lint` → verde (ruff check/format, eslint, prettier).
- `make typecheck` → verde (mypy, tsc -b).
- `make test` → verde, 13 passed (backend, sin Docker) + 1 passed (frontend).
- `make contracts` → ok, regenerado sin errores.
- **`make dev-up` y `make test-integration` NO se ejecutaron** — el entorno de esta sesión no tiene Docker disponible (Docker Desktop no instalado/en ejecución; se verificó que no hay alternativa como Colima/OrbStack/Podman tampoco). Las pruebas marcadas `@pytest.mark.docker` (`test_mongo_client.py`, `test_blob_storage.py`, `test_health_ready_up.py`) quedaron escritas pero sin ejecutar. **Pendiente que el founder las corra en una máquina con Docker** antes de dar Fase 1B por cerrada en firme.
- Bug encontrado y corregido durante la verificación: `check_storage_ready`/`AzureBlobStorage.ping()` no pasaba `retry_total=0` al SDK de Azure, por lo que el chequeo de `/health/ready` con Azurite caído tardaba ~87s (reintentos con backoff exponencial de azure-core) en vez de fallar rápido. Corregido antes de cerrar la sesión; el test `test_health_ready_down.py` ahora corre en <2s.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):**
- Cola local por defecto cambia de Redis (documentado previamente) a `InMemoryMessageBus` — **formalizada en ADR 0020**, no queda como ad-hoc.
- Re-corte de "Fase 1B" en 1B (infra local) + 1C (automatización/dominio) — decisión operativa de secuenciación de sesiones, no arquitectónica; documentada en `current-phase.md`, no requiere ADR.
- `/health` plano de Fase 1A se reemplaza por `/health/live` + `/health/ready` — consecuencia directa del alcance pedido para esta fase, no una decisión arquitectónica nueva.

**Deuda técnica introducida:**
- **`InMemoryMessageBus` no cruza procesos** — API y worker cada uno instancia la suya; no hay todavía un flujo real de publicación desde la API que el worker consuma. Se resuelve cuando exista el primer job asíncrono real (Fase 13), momento en que también se evalúa el adaptador de Service Bus.
- **`make migrate` es un no-op** — el runner y la colección `_migrations` existen, pero no hay ninguna migración de dominio real todavía; se agregará junto con el primer índice/colección de negocio (Fase 1, `identity`).
- **Mongo Community local sin autenticación** — aceptado por ser solo local, nunca expuesto; no aplica a producción (Atlas usa auth + IP allowlist).
- **Sin CI ni pre-commit todavía** — diferido a Fase 1C junto con los 15 bounded contexts vacíos, para agrupar automatización de calidad y esqueleto de dominio en una sola sub-fase.

---

**Actualización — ronda 1 — 2026-07-17 (misma sesión, tras primera validación manual del founder con Docker):**

El founder corrió `make test-integration` en macOS con Docker real. Resultado:

- 5 pruebas Docker seleccionadas.
- Mongo (`test_mongo_client.py`): **2/2 PASS**.
- Blob Storage (`test_blob_storage.py`): **2/2 ERROR**.
- `/health/ready` con dependencias arriba (`test_health_ready_up.py`): **FAIL** (503, no 200).

**Causa confirmada:** `azure-storage-blob` 12.30.0 envía por defecto el header `x-ms-version: 2026-06-06` (el último valor de su lista interna `_SUPPORTED_API_VERSIONS`). Azurite 3.33.0 no soporta esa versión y responde `InvalidHeaderValue: The API version 2026-06-06 is not supported by Azurite`. El 503 de `/health/ready` es consecuencia directa del mismo error en `check_storage_ready`. Mongo no tuvo ningún problema — el error es específico del cliente de Blob Storage.

**Decisión aprobada por el founder:** mantener `azure-storage-blob==12.30.0` y Azurite `3.33.0` (sin bajar versiones, sin `latest`, sin `--skipApiVersionCheck`), y fijar explícitamente la versión REST de la API vía un campo tipado — no dejarla en el default del SDK.

**Fix implementado (verificado en el código fuente instalado de `azure-storage-blob`: `2025-01-05` está en `_SUPPORTED_API_VERSIONS`, confirmado compatible con Azurite 3.33.0 y con Azure Storage real):**
- `service/procurawise/shared/config.py` — nuevo campo `Settings.storage_api_version: str`, default `"2025-01-05"`, override vía env var `AZURE_STORAGE_API_VERSION` (alias explícito, no el nombre por convención `STORAGE_API_VERSION`); `model_config` gana `populate_by_name=True` para que la construcción directa por nombre de campo (usada en tests/fixtures) siga funcionando junto con el alias.
- `service/procurawise/shared/storage.py` — `AzureBlobStorage.__init__` acepta `api_version` y lo pasa explícitamente a `BlobServiceClient.from_connection_string(..., api_version=api_version)`; `from_settings()` lo puebla desde `settings.storage_api_version`. Confirmado en el código del SDK (`get_container_client`/`get_blob_client`) que los clientes derivados (`ContainerClient`, `BlobClient`) heredan automáticamente el mismo `api_version` del cliente de servicio — no hace falta pasarlo en cada punto.
- `.env.example` — `AZURE_STORAGE_API_VERSION=2025-01-05` con comentario explicando por qué está fijada y que no debe quitarse solo porque el SDK tenga un default más nuevo.
- `service/tests/unit/test_storage.py` (nuevo) — 4 tests: default `2025-01-05` propagado a `BlobServiceClient`/`ContainerClient`; override por env var; `BlobClient` derivado también hereda la versión; un `api_version` inválido produce `ValueError` sin la connection string ni `AccountKey` en el mensaje. Todos construyen el cliente offline (sin red), no requieren Docker.
- `service/tests/unit/test_config.py` — 2 casos nuevos: default de `storage_api_version` y override vía `AZURE_STORAGE_API_VERSION`.

**Resultado de pruebas tras el fix (sin Docker, mismo entorno sin Docker de esta sesión):**
- `make lint` → verde.
- `make typecheck` → verde.
- `make test` → verde, **19 passed** (antes 13; +4 `test_storage.py` +2 `test_config.py`), 5 deselected (`docker`).
- `make contracts` → ok.
- **`make dev-up`/`make test-integration` NO se re-ejecutaron** — este entorno sigue sin Docker. El fix está verificado por lectura del código fuente del SDK instalado (confirmando que `2025-01-05` es una versión soportada y que se propaga a los clientes derivados) y por los 6 tests unitarios nuevos, pero **no está confirmado contra Azurite real todavía**.

---

**Actualización — ronda 2 (✅ éxito, cierre de fase) — 2026-07-17:**

El founder re-corrió la validación completa en su Mac con Docker Desktop, con el fix de `AZURE_STORAGE_API_VERSION=2025-01-05` aplicado:

- `docker version` / `docker compose version` → PASS.
- `make dev-up` → PASS.
- `make dev-status` / `docker compose ps` → Mongo y Azurite `healthy`.
- `make test-integration` → **PASS, las 5 pruebas Docker pasaron**: roundtrip Mongo (2/2), roundtrip Blob Storage contra Azurite (2/2), `/health/ready` con dependencias disponibles → HTTP 200.
- `make lint` → PASS. `make typecheck` → PASS.
- `make test` → PASS, 19 passed, 5 pruebas Docker correctamente excluidas de la suite unitaria (`-m "not docker"`).
- `make contracts` → PASS.
- `make dev-down` → PASS; `docker compose ps` después, sin contenedores activos.

**Confirmado: `AZURE_STORAGE_API_VERSION=2025-01-05` resolvió la incompatibilidad con Azurite 3.33.0.** No se hizo ningún cambio de código ni de dependencias en esta actualización — únicamente se registra el resultado de la validación y se cierra la fase.

**Fase 1B queda formalmente Completed.** Todos los criterios de aceptación de la fase están cumplidos — ver `current-phase.md` para el detalle punto por punto. Las condiciones para iniciar Fase 1C están cumplidas, pero **Fase 1C sigue en estado Planned / Not Started: no se ha iniciado ningún trabajo de esa sub-fase.**

**Deuda técnica registrada (no bloqueante para Fase 1C):**
- `StarletteDeprecationWarning` al usar `fastapi.testclient.TestClient` con `httpx` ("install `httpx2` instead"). Solo aparece en la suite de tests, no afecta runtime ni falla ningún test. Revisar cuando FastAPI/Starlette estabilicen la migración a `httpx2`, o la próxima vez que se toquen las dependencias de testing del backend.

**Instrucciones para la siguiente sesión / founder:**
- Fase 1B está cerrada — no repetir su trabajo ni volver a pedir validación de Docker salvo que se toque de nuevo la infraestructura local.
- Decidir si se comitea el resultado de Fase 1B antes de continuar (ver recomendación de commit más abajo en el reporte de esta sesión).
- Ejecutar **Fase 1C (Automatización y esqueleto de dominio)**: pre-commit (ruff, mypy permisivo, eslint, prettier), CI (`lint.yml`, `test.yml`), y los 15 subpaquetes vacíos de bounded contexts en `service/procurawise/`. Ver alcance exacto en `docs/development/current-phase.md`.
- No tocar todavía: lógica de dominio (`evaluations`, `vendors`, etc. — más allá de crear los subpaquetes vacíos en 1C), auth real, IA, pagos.
- Ningún archivo de esta sesión fue comiteado a git — el founder debe confirmar explícitamente si quiere commitear el resultado de Fase 1B antes o junto con el trabajo de Fase 1C.

---

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
