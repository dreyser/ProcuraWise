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

### Sesión — 2026-08-10 — Fase 27 (E11, Bloque 6 "Hardening y despliegue"): Infra Azure real (Bicep) + CI/CD GitHub Actions OIDC staging→prod

**Resumen:** Sesión que comenzó en Plan Mode exclusivo de solo lectura: confirmó el cierre formal de Fase 26 (`origin/main@9c44d63`, PR #43) y del hotfix posterior (`origin/main@491a27a`, PR #44) vía Git/GitHub, identificó Fase 27 por evidencia documental cruzada de `backlog.md`/`roadmap.md`/`deployment.md`/`architecture.md` (dependencia declarada Fase 26 ✅, única fase restante 100% infraestructura antes del piloto), y produjo un plan técnico completo con 2 preguntas genuinamente bloqueantes (representación de "staging" en `Settings.environment`, sin cuarto valor hasta ahora; alcance de verificación real dado que este entorno no tiene acceso a una suscripción Azure/Atlas real). El founder resolvió las 2 con la opción recomendada en cada caso vía `AskUserQuestion`. Tras la autorización ("Autorizo iniciar la implementacion"), ejecución completa en 8 bloques incrementales (housekeeping documental del hotfix, contenerización, `environment=staging`, Bicep fundación, Bicep datos, Bicep Container Apps, OIDC+workflows, documentación de cierre), cada bloque verificado al máximo nivel posible en este entorno (sin suscripción Azure real disponible).

**Decisiones bloqueantes resueltas por el founder (plan §10):**
1. Representación de "staging": **Opción A** — `Settings.environment` gana un cuarto valor (`Literal["local", "test", "staging", "production"]`), con una nueva `@property is_production_like` que agrupa `staging`/`production` para 5 de los 7 validadores fail-closed (OIDC/Azure OpenAI/notificaciones-si-activas real, sin cola en memoria, sin JWT default) — deliberadamente **sin** incluir el validador que rechaza claves Stripe live fuera de producción, así que staging nunca puede aceptar una clave `sk_live_...` (siempre `sk_test_`, evitando cobros reales durante UAT).
2. Alcance de verificación real: **Opción A** — implementar y verificar todo lo posible en este entorno (sin acceso a Azure/Atlas reales); el primer deploy real queda como acción manual del founder, documentada en `infra/scripts/bootstrap-oidc.md`, mismo patrón ya usado en Fases 15 (OIDC real)/25 (Stripe Test Mode real).

**Hallazgo real durante la implementación (no un bug, una consecuencia de diseño detectada antes de comitear):** el default inicial de `container-app.bicep` (`maxReplicas: 3`, siguiendo el patrón estándar de autoscaling de Container Apps) habría invalidado silenciosamente el riesgo aceptado de Fase 26 ("rate limiting in-process irrelevante mientras corra una sola réplica") en cuanto se ejecutara un deploy real. Corregido fijando `maxReplicas: 1` deliberadamente, con un comentario explicando la dependencia — subir ese límite requiere primero coordinar `shared/rate_limit.py` entre réplicas, no es un ajuste aislado. `docs/security/threat-model.md` actualizado para reflejar esta salvaguarda en vez de solo "revisar en Fase 27".

**Diseño técnico central (no bloqueante, resuelto por evidencia):** `main.bicep` despliega a scope de *resource group* (`az deployment group create`), no de suscripción — el resource group se crea una única vez, manualmente, durante el bootstrap, precisamente para que la identidad OIDC del pipeline recurrente nunca necesite más que `Contributor` acotado a ese resource group ya existente (mínimo privilegio, plan §14) en vez de un permiso de suscripción completa para poder "crear" el resource group en cada corrida. Migraciones ejecutadas vía `az containerapp exec` contra el contenedor api ya desplegado (reutiliza la `Settings` real que Bicep ya inyectó vía Key Vault/env vars) en vez de reconstruir esa configuración en el runner de GitHub Actions, que habría duplicado innecesariamente toda la validación fail-closed de `shared/config.py`. Módulo `container-app.bicep` genérico, reusado para api/worker (misma forma de recurso, solo difieren en ingress/imagen) en vez de dos archivos casi idénticos.

**Decisiones no bloqueantes resueltas por evidencia (ninguna requirió al founder):**
1. Azure Service Bus namespace tier Standard, no Premium (NFR-003 no lo justifica).
2. MongoDB Atlas se aprovisiona manualmente (Atlas no es un recurso Azure, Bicep no puede cubrirlo; ADR 0004 restringe la IaC del proyecto a Bicep/Azure-only, sin justificación para introducir Terraform solo por este recurso externo) — documentado como runbook manual, no como código.
3. Sin dominio personalizado para staging — el FQDN autogenerado de Container Apps es suficiente, candidato a Fase 28 si se expone a clientes reales.
4. `deploy-staging.yml`/`deploy-prod.yml` como dos workflows separados (no uno parametrizado), aprovechando las reglas de protección nativas de GitHub Environments en vez de reconstruirlas en código.
5. Las 4 colas reales de Service Bus (no solo las 2 que `docker/servicebus-emulator/config.json` define, desactualizado desde las Fases 23/24) — descubierto revisando qué topics despacha realmente el worker antes de escribir el módulo Bicep, no asumido del archivo del emulador local.

**Archivos tocados:** `service/Dockerfile.api`/`Dockerfile.worker`/`.dockerignore` (nuevos); `service/procurawise/shared/config.py` (+`staging`, +`is_production_like`, 5 validadores ajustados); `service/procurawise/api/main.py` (HSTS vía `is_production_like`); `service/tests/unit/test_config.py` (+11 tests); `infra/bicep/main.bicep` (nuevo, orquestador) + `infra/bicep/modules/{log-analytics,container-registry,key-vault,container-apps-env,storage-account,service-bus,managed-identity,container-app}.bicep` (nuevos); `infra/params/{staging,production}.bicepparam` (nuevos); `infra/scripts/bootstrap-oidc.md` (nuevo); `.github/workflows/deploy-staging.yml`/`deploy-prod.yml` (nuevos); `docs/operations/deployment.md` (secciones completadas); `docs/security/threat-model.md` (2 referencias actualizadas); `docs/development/current-phase.md`/`session-handoff.md` (esta entrada + la retroactiva del hotfix, Bloque 0).

**Resultado de pruebas:**
- `make lint`/`make typecheck` → limpio (backend + frontend, 0 errores).
- Backend unit (`make test-backend`) → 300 passed (+11 sobre la base de Fase 26).
- `az bicep build`/`az bicep lint` (9 archivos `.bicep`) → sin errores/warnings.
- `az bicep build-params` (2 `.bicepparam`) → sin errores.
- `docker build` de ambas imágenes → exitoso; smoke test real contra Mongo/Azurite locales → `/health/live`/`/health/ready` en 200, worker despachando 4 colas.
- `git diff --check` → limpio.
- Backend integración Docker/frontend/E2E → sin cambios de alcance esta fase, verificados sin regresión.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):**
- Ninguna requiere ADR — todas las decisiones son sobre arquitectura de despliegue ya aprobada (ADR 0004/0005/0015/0019), sin nueva infraestructura conceptual, sin cambio de patrón de comunicación ni de datastore.

**Deuda técnica introducida:**
- Ninguna material nueva — la limitación de rate limiting no-coordinado ya era deuda conocida de Fase 26; esta sesión la preserva deliberadamente (`maxReplicas: 1`) en vez de introducirla sin darse cuenta.
- Firma/escaneo de imágenes ACR no implementado (no solicitado por el criterio de aceptación textual) — candidato a hardening posterior.

**Instrucciones para la siguiente sesión:**
- Acción pendiente inmediata (no una "siguiente fase" de código): el founder debe ejecutar `infra/scripts/bootstrap-oidc.md` (resource group, App Registration OIDC, secrets del repo, Key Vault, cluster Atlas, primer deploy real) para completar la mitad de ejecución real del criterio de aceptación de Fase 27. Registrar el resultado en `current-phase.md` cuando ocurra.
- Próxima fase de código según `backlog.md`: **Fase 28**, UAT piloto 1-3 empresas — depende de Fase 27; no iniciar su planeación hasta que el deploy real de Fase 27 esté confirmado (el piloto necesita un ambiente real funcionando).
- No tocar todavía: firma/escaneo de imágenes ACR; dominio personalizado; coordinación de rate limiting entre réplicas (sigue fijado a `maxReplicas: 1`); aprovisionar Azure OpenAI/ACS como recursos Bicep (siguen tratados como servicios externos vía Key Vault).
- Housekeeping pendiente heredado, sin cambios: ramas `phase-14` a `phase-26` siguen sin borrarse; rama local `main` sigue detrás de `origin/main` (requiere `git pull`/fast-forward explícito).

### Sesión — 2026-08-10 — Hotfix (post-Fase 26, pre-Fase 27): `eslint-plugin-react-hooks` 5.2.0→7.1.1 (Dependabot) + bug real de re-suscripción en `useSyncExternalStore`

**Resumen:** Sesión disparada por un check `frontend` fallido en el PR de Dependabot que sube `eslint-plugin-react-hooks` a 7.1.1, contra un bug real (`react-hooks/refs`) en `useReportJobStatus.ts`. El founder autorizó investigar/corregir; el alcance real resultó ser 88 errores en 15 archivos (3 reglas nuevas de la v7). El founder, vía `AskUserQuestion`, eligió "corregir todo ahora en esta rama" sobre las alternativas (unblock mínimo, o no subir la versión todavía). Ejecutado como una serie de fixes puntuales verificados individualmente, no por bloques de plan — sin sesión de Plan Mode dedicada (a diferencia de toda fase numerada).

**Bug real encontrado y corregido durante la propia corrección (no solo lint):** los 4 hooks de polling migrados a `useSyncExternalStore` (`useReportJobStatus`, `useAiSuggestionJobStatus`, `useAiScoreSuggestionJobStatus`, `usePurchaseStatus`) memoizaban su función `subscribe` con deps `[]`. Para un id que empieza `null` (caso común: `reportId`/`jobId`), React invoca `subscribe` una única vez en el montaje, capturando `controllerRef.current === null` permanentemente — cuando el controller real se construye después (en un efecto separado, tras el id volverse no-nulo), `subscribe` nunca se vuelve a invocar (su identidad no cambió) y el polling queda silenciosamente sin ningún listener. Diagnosticado comparando `ReportsPage.test.tsx` contra el código pre-fix vía `git stash` (4/4 pasaba antes, confirmando regresión real, no flaky preexistente). Corregido dando a `subscribe` las mismas deps que el efecto de construcción del controller.

**Decisiones no bloqueantes resueltas por evidencia (ninguna requirió al founder salvo la autorización inicial de alcance):**
1. `src/api/client.ts` (generado por orval) exento de `react-hooks/refs`/`react-hooks/immutability` vía override en `eslint.config.js`, no editado a mano.
2. `useQnaPolling`/`useNotificationsPolling`: ref de callback sincronizado en su propio efecto sin deps, no escrito directamente durante el render (idioma nuevo requerido por `react-hooks/refs` v7).
3. `useAnswerAutosave`/`EconomicWeightsForm`/`EvaluationWizard`/`EconomicAssessmentPanel`: patrón "adjust state during render" (React docs) en vez de `setState` síncrono dentro de un efecto.
4. `AuthCallbackPage.tsx`: `eslint-disable` puntual y documentado (el side-effect impuro de `history.replaceState` no es apto para un inicializador perezoso de `useState` bajo el doble-invocado de Strict Mode).
5. `AuthContext.tsx`: bug real de orden de declaración — `proceedFromPreSessionToken` capturaba `switchTenant` por closure antes de su propia declaración, con `react-hooks/exhaustive-deps` deshabilitado ocultando el riesgo de closure obsoleto. Corregido reordenando y con el array de dependencias real.

**Archivos tocados:** `eslint.config.js` (+override `client.ts`), `src/features/reports/hooks/useReportJobStatus.ts`, `src/features/evaluations/hooks/{useAiSuggestionJobStatus,useAiScoreSuggestionJobStatus,useQnaPolling}.ts`, `src/features/notifications/hooks/useNotificationsPolling.ts`, `src/features/billing/hooks/usePurchaseStatus.ts`, `src/features/vendor-portal/hooks/useAnswerAutosave.ts`, `src/actor/ActorContext.tsx`, `src/auth/{AuthCallbackPage,AuthContext}.tsx`, `src/features/evaluations/wizard/{EconomicWeightsForm,EvaluationWizard}.tsx`, `src/features/scoring/components/EconomicAssessmentPanel.tsx`.

**Resultado de pruebas:**
- `pnpm lint` → 0 errores, 86 warnings (línea base sin cambio respecto a Fase 26).
- `pnpm typecheck` → limpio.
- `pnpm test` → 212/212 (6 fallaban antes de corregir el bug de `subscribe`, en `ReportsPage.test.tsx`/`ScoringPage.test.tsx`/`AiSuggestRequirementsDialog.test.tsx`).
- `make test-e2e` → 20/20 (incluye `report-generation.spec.ts`/`ai-score-suggestions.spec.ts`, que ejercitan los hooks corregidos).
- `pnpm format` (prettier) → 1 fallo post-PR (CI, `EconomicAssessmentPanel.tsx`) corregido en un segundo commit dentro del mismo PR antes de fusionar.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):**
- Ninguna requiere ADR — todos los fixes son correcciones de un patrón de hooks ya establecido (`useSyncExternalStore`/ADR implícito de Fase 23), sin tocar arquitectura, base de datos, ni patrón de comunicación.

**Deuda técnica introducida:**
- Ninguna nueva. Deuda pre-existente corregida (el bug de `subscribe` afectaba a 4 hooks ya en producción desde Fases 23/25).

**Deuda documental encontrada (no introducida por esta sesión, pero solo detectada durante la planeación de Fase 27):** esta sesión no actualizó `current-phase.md`/`session-handoff.md` en su momento — incumple CLAUDE.md §10 literalmente ("Al cerrar cualquier sesión de trabajo en código... añade una entrada en `session-handoff.md`"). Esta entrada y la sección correspondiente de `current-phase.md` son retroactivas, agregadas como Bloque 0 de la sesión de implementación de Fase 27.

**Instrucciones para la siguiente sesión:**
- Próxima fase según `backlog.md` (columna "Depende de"): **Fase 27**, Infra Azure real (Bicep) + CI/CD GitHub Actions OIDC staging→prod — depende de Fase 26 (✅ cerrada, sin dependencia de este hotfix).
- No tocar todavía: nada específico de este hotfix queda pendiente — cierre completo.
- Housekeeping pendiente heredado, sin cambios: ramas `phase-14` a `phase-26` siguen sin borrarse; rama local `main` quedó 1 commit detrás de `origin/main` tras este PR (requiere `git pull`/fast-forward).

### Sesión — 2026-08-09 — Fase 26 (E11, Bloque 6 "Hardening y despliegue"): Hardening (rate limiting, CSRF, headers, dependency/secret scanning, WCAG 2.1 AA, performance, backup/restore) + cierre formal de `threat-model.md`

**Resumen:** Sesión que comenzó en Plan Mode exclusivo de solo lectura: confirmó el cierre formal de Fase 25 con evidencia de Git/GitHub (`origin/main` en `befa5f9`, squash-merge de PR #39), identificó Fase 26 por evidencia documental cruzada de `backlog.md`/`roadmap.md`/`threat-model.md` (dependencia declarada Fase 24, no Fase 25), y produjo un plan técnico completo con 2 preguntas genuinamente bloqueantes (nivel de verificación de backup/restore dado que Atlas M0 no soporta backups gestionados; alcance de la auditoría WCAG 2.1 AA sobre 35 rutas/3 portales). El founder resolvió las 2 con la opción recomendada en cada caso. Tras la autorización ("Autorizo avanzar con la implementacion del plan"), ejecución completa en 8 bloques incrementales (CORS+headers, rate limiting, CSRF/documentación, dependency scanning+SBOM, WCAG 2.1 AA, performance k6, backup/restore, cierre de `threat-model.md`), cada uno verificado contra Docker/E2E real antes de avanzar.

**Decisiones bloqueantes resueltas por el founder (plan §9):**
1. Backup/restore: **Opción A** — verificación de nivel MVP vía `mongodump`/`mongorestore` contra Mongo local (`scripts/backup_restore_demo.sh`, `make backup-demo`), documentada explícitamente como no equivalente a un backup gestionado de Atlas (M0 no lo soporta); no reabre ADR 0015.
2. Alcance WCAG 2.1 AA: **Opción A** — automatizado (`jsx-a11y`+`axe-core`) al 100% de la SPA + auditoría manual (Playwright-driven) en los 2 journeys core (comprador dueño de evaluación, proveedor respondiendo propuesta); consola admin con cobertura solo automatizada, deuda documentada.

**5 bugs reales detectados y corregidos durante la propia sesión de implementación (expuestos por la suite E2E real y por los propios scripts nuevos, no por tests unitarios preexistentes):**
1. **Rate limiting de login contaba también los intentos exitosos** — la primera versión (per-IP, todo intento cuenta) provocó una cascada real de hasta 11/18 specs E2E fallando en cuanto la suite superó el umbral con logins legítimos repetidos hacia el mismo roster fijo de cuentas sembradas. Corregido con keying `(IP, email)` + solo-fallos-cuentan (`enforce_login_not_locked_out`/`record_login_failure`), aplicado simétricamente a `/auth/login` y `/vendor-auth/login`.
2. **Contraste insuficiente del badge `destructive`** (axe-core, `impact: serious`, 6 specs) — corregido en `index.css` (`--destructive` más oscuro, mismo matiz/croma).
3. **Controles de formulario sin nombre accesible** (axe-core, `impact: critical`, 3 specs) — inputs de archivo ocultos y 6 de 10 tipos de control de `AnswerField.tsx` sin ninguna forma de label; corregido con `aria-label`/`aria-labelledby`.
4. **Colisión de accessible name** tras el fix anterior — el `aria-label` del input de archivo oculto (rol ARIA implícito `button`) coincidía por subcadena con el botón visible de disparo, rompiendo un locator de Playwright; corregido con texto sin solapamiento.
5. **`mongorestore --dir` apuntando al subdirectorio incorrecto** — fallaba silenciosamente (sin error fatal) restaurando 0 documentos; corregido apuntando al directorio padre del dump.

**Decisiones no bloqueantes resueltas por evidencia (ninguna requirió al founder):**
1. Rate limiting in-process, sin Redis (ADR 0020 ya lo excluyó del diseño; NFR-003 no justifica reabrirlo).
2. CSRF mitigado estructuralmente (sin cookies de sesión en toda la app, confirmado por búsqueda exhaustiva), sin tokens anti-CSRF construidos.
3. Dependency scanning bloqueante solo en `high`/`critical`, no todo hallazgo (evita bloquear por CVEs transitivos sin fix disponible).
4. `k6` sobre `locust` para performance (menor huella de dependencias, sin runtime Python adicional).
5. Único hallazgo real de `pip-audit` (`cryptography` HIGH) corregido con un bump de versión en vez de documentado como excepción — un fix disponible existía.

**Archivos tocados:** ver el detalle completo por bloque en `current-phase.md` — resumen: `shared/rate_limit.py` (nuevo), `identity/auth_router.py`/`vendor_auth_router.py` (login solo-fallos), `ai/router.py`/`billing/router.py` (rate limit por tenant), `api/main.py` (CORS+headers middleware), `shared/config.py` (+7 settings), `pyproject.toml`/`uv.lock` (`cryptography` 49→50), `tests/unit/test_security_headers.py`/`test_rate_limit.py` (nuevos), `tests/security/test_rate_limiting.py` (nuevo), `tests/conftest.py` (+reset del limiter); frontend: `eslint.config.js` (+jsx-a11y), `e2e/support/a11y.ts` (nuevo), los 18 specs E2E existentes (+`checkA11y`), `index.css`, `RequirementEvidenceUpload.tsx`/`ProposalDocumentsPanel.tsx`/`AnswerField.tsx`/`VendorProposalDetailPage.tsx` (fixes de accesibilidad), `package.json`/`pnpm-lock.yaml` (+2 deps, +`pnpm.overrides` para `lodash`/`js-yaml`); CI: `.github/workflows/security.yml` (bloqueante high/critical + job `sbom`); operación: `scripts/perf/rfp-read-load.js` (nuevo), `scripts/backup_restore_demo.sh` (nuevo), `Makefile` (+`backup-demo`), `.env.example` (+variables nuevas); docs: `docs/security/threat-model.md` (cierre formal), `docs/operations/deployment.md` (+secciones Performance/Backup con evidencia real).

**Resultado de pruebas:**
- `make lint`/`make typecheck` → limpio (backend + frontend, 0 errores).
- Backend unit (`pytest -m "not docker..."`) → 289 passed (+12 sobre la base de Fase 25).
- Backend integración/API/seguridad Docker (`make test-integration`) → 439 passed (+6 sobre la base de Fase 25; una corrida intermedia tuvo 1 fallo transitorio de `test_documents_storage.py` no relacionado con esta fase, confirmado flaky preexistente — pasa en aislamiento y en re-corrida completa limpia).
- Frontend (`pnpm test`) → 212 passed (sin cambio respecto a Fase 25).
- `make test-e2e` → 20/20 tests en verde (18 specs) en la corrida final, tras corregir los 5 bugs reales descritos arriba.
- `make contracts` corrido dos veces seguidas → sin diff (esta fase no cambia contratos OpenAPI).
- `git diff --check` → limpio.
- `k6 run scripts/perf/rfp-read-load.js` → p95=127.46ms (umbral <500ms), 0.00% error rate (umbral <1%), 2610 iteraciones, 50 VUs pico sostenido.
- `make backup-demo` → 26 colecciones / 9025 documentos, conteo idéntico origen↔restaurada.
- `shellcheck scripts/backup_restore_demo.sh` → limpio.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):**
- Ninguna requiere ADR — todas las decisiones de esta fase son hardening/tooling sobre arquitectura ya aprobada (sin nueva infraestructura, sin nuevo bounded context, sin cambio de patrón de comunicación).

**Deuda técnica introducida:**
- `GET /api/v1/me` sigue cableado al mecanismo de identidad pre-AUTH-PROD (`X-Dev-Membership-Id`) en vez del JWT real — descubierto por el script de k6, fuera del alcance de esta fase (no es rate limiting/CSRF/headers/WCAG/performance/backup), candidato a una fase futura que toque `identity/router.py`.
- Sin `Content-Security-Policy` — requeriría inventariar cada origen de recurso del SPA, decisión de alcance documentada, candidato a hardening posterior si se necesita.
- Auditoría manual WCAG de la consola `platform_admin`/`tenant_admin` no realizada (cobertura solo automatizada) — decisión explícita del founder, mismo patrón "opción mínima" de Fase 25.
- Backup/restore verificado solo a nivel MVP (Mongo local), no contra Atlas real — Atlas M0 no lo soporta; requiere upgrade de tier post-MVP sin gatillo numérico (ADR 0015) para cerrar completamente.
- Rate limiting in-process no coordina entre réplicas múltiples de la API — irrelevante mientras no exista infraestructura real desplegada (Fase 27).

**Instrucciones para la siguiente sesión:**
- Próxima fase según `backlog.md` (columna "Depende de"): **Fase 27**, Infra Azure real (Bicep) + CI/CD GitHub Actions OIDC staging→prod — depende de Fase 26 (✅ cerrada).
- No tocar todavía: `GET /api/v1/me` (deuda documentada, no bloqueante); `Content-Security-Policy`; auditoría manual WCAG de la consola admin; backup/restore contra Atlas real (requiere infraestructura de Fase 27 primero, y potencialmente un upgrade de tier fuera del alcance de esa fase también).
- Housekeeping pendiente heredado, sin cambios: ramas `phase-14` a `phase-25` siguen sin borrarse (requiere confirmación explícita del founder); rama local `main` requiere `git pull`/fast-forward tras fusionar esta fase.

### Sesión — 2026-08-08 — Fase 25 (E11, Bloque 6 "Hardening y despliegue"): Billing/Admin básico P1 (Stripe Checkout hospedado + consola `platform_admin` cross-tenant auditada)

**Resumen:** Sesión que comenzó en Plan Mode exclusivo de solo-lectura: verificó el cierre formal de Fase 24 con evidencia de Git/GitHub (PR #38 fusionado a `main`, merge commit `2120553`, 8/8 checks verdes), identificó Fase 25 por evidencia documental cruzada de `backlog.md`/`roadmap.md`/`session-handoff.md` (dependencia declarada: Fase 9, no Fase 24), y produjo un plan técnico completo con 3 preguntas genuinamente bloqueantes (ver abajo). El founder resolvió las 3 explícitamente, siguiendo en los 3 casos la opción recomendada por el plan. Tras esa autorización, ejecución completa en 5 bloques incrementales (fundación de billing sin superficie HTTP, checkout+webhook+auditoría+notificación, UI `tenant_admin`, consola `platform_admin`, E2E+sandbox+documentación), cada uno verificado contra Docker real antes de avanzar.

**Decisiones bloqueantes resueltas por el founder (plan §10):**
1. Modelo comercial: **Opción A** — compra única por-evaluación (`mode="payment"`), sin suscripción ni híbrido en esta fase; el diseño (`PaymentProvider`, `BillingAccount` como ancla delgada de `stripe_customer_id`) queda abierto a suscripciones futuras sin romper compatibilidad.
2. Alcance de la consola admin: **Opción b (mínima)** — reutilizar la infraestructura admin existente (Fase 9), agregando solo la UI sobre los endpoints ya existentes más el único endpoint de lectura de billing cross-tenant estrictamente necesario (`GET /admin/purchases`); sin la consola completa de la spec §12.2 (gestión de usuarios/roles, activación manual, salud operativa).
3. Verificación del "cobro de prueba en modo sandbox": **Nivel 3** — demostración manual en Stripe Test Mode (Checkout hospedado real + Stripe CLI reenviando el webhook), con CI permaneciendo 100% determinística sin dependencia de Stripe; instrucciones de provisión (API Keys, Product, Price, Webhook Secret) documentadas en `deployment.md`.

**Bugs reales detectados y corregidos durante la propia sesión de implementación (expuestos por el E2E real, no por los tests unitarios existentes):** (1) `LoginPage.tsx` navegaba con `roleHomePath('evaluation_owner')` hardcodeado en el atajo de login de una sola membresía — inofensivo antes de esta fase (todo rol comprador compartía `/evaluations`), pero rompía a `tenant_admin` (su propio home nuevo, `/billing`) enviándolo a `/unauthorized`. Corregido propagando el rol real resuelto por `AuthContext.switchTenant()` hasta `LoginPage.tsx` (nuevo campo `AuthResult.role`), con test de regresión. (2) `usePurchaseStatus.ts` (hook de polling de compra, calcado de `useReportJobStatus.ts` de Fase 23) construía su `PollingController` durante el render en vez de dentro de un `useEffect` — bajo React StrictMode (dev-only), el desmontaje+remontaje simulado solo re-ejecuta efectos, no el cuerpo de render, así que el controller quedaba disponible pero la ref permanentemente `null`, dejando la página de éxito de checkout congelada en "Confirmando tu pago…" con el pago ya confirmado en el backend. Diagnosticado deshabilitando StrictMode temporalmente para confirmar la hipótesis, corregido moviendo la construcción del controller dentro de `useEffect` (patrón idiomático para sobrevivir el doble-invocado de StrictMode). `useReportJobStatus.ts` comparte la misma forma vulnerable pero no se tocó (fuera del alcance autorizado de esta fase) — queda como deuda técnica conocida, no confirmada como manifestada en producción.

**Hallazgo de arquitectura, no un bug**: la sesión del comprador (JWT solo en memoria, AUTH-PROD) se pierde al volver de un Checkout hospedado real, porque esa ida-y-vuelta es una navegación de página completa del navegador, no del router de React. `RequireAuth` ya lo maneja correctamente (`/login?next=...`), pero implica que el comprador debe reautenticarse para ver la confirmación de su propio pago. Documentado como fricción de producto conocida en `threat-model.md` (sección Billing) — no se resuelve sin reabrir la decisión de no-persistencia de sesión de AUTH-PROD.

**Archivos tocados:** ver el detalle completo por bloque en `current-phase.md` — resumen: nuevo módulo `procurawise/billing/` (`models.py`/`exceptions.py`/`repository.py`/`provider.py`/`stripe_payment_provider.py`/`service.py`/`schemas.py`/`router.py`/`webhook_router.py`/`dependencies.py`), `admin/service.py`/`admin/router.py` (+`AdminPurchaseService`, +`GET /admin/purchases`, +`tenant_name` resuelto), `shared/config.py` (+6 settings, +2 validadores), `shared/roles.py` (+`BILLING_WRITE_ROLES`/`BILLING_READ_ROLES`), `audit/models.py` (+1 `AuditResourceType`, +3 `AuditAction`), `notifications/models.py` (+1 `NotificationEvent`), `api/main.py` (routers montados), `migrations/0022_billing_indexes.py` (nuevo), `pyproject.toml` (+`stripe`, +marcador `stripe_sandbox`), `dev_seed.py` (+2 colecciones), ADR 0025 (nuevo), `Makefile` (`test-backend` excluye `stripe_sandbox`); `tests/integration/test_stripe_sandbox_checkout.py` (nuevo, opt-in); frontend: `features/billing/` (nuevo, `BillingPage`/`CheckoutSuccessPage`/`CheckoutCancelledPage`/`usePurchaseStatus`), `admin-auth/` (nuevo), `features/admin/` (nuevo, `CrossTenantReasonGate`/`AdminEvaluationsPage`/`AdminBillingPage`), `app/router.tsx` (`AdminLayout`, nuevas rutas, `BuyerLayout` con prop `roles`), `app/AppShell.tsx` (`tenant_name` opcional, nav condicional), `app/roleHomePath.ts`, `lib/http.ts` (+tercer slot de token), `lib/enumLabels.ts` (+`platform_admin`, +`purchaseStatusLabels`), `auth/AuthContext.tsx`/`auth/LoginPage.tsx` (fix del bug de rol hardcodeado, ver arriba), `App.tsx` (+`AdminAuthProvider`); `e2e/billing-checkout.spec.ts`/`e2e/admin-console.spec.ts` (nuevos); `docs/architecture/decisions/0025-pagos-stripe-checkout-hospedado.md` (nuevo), `docs/operations/deployment.md` (+sección Stripe/billing con procedimiento de demo manual), `docs/security/threat-model.md` (+sección Billing Fase 25, re-alcance de la fila de riesgo `platform_admin`).

**Resultado de pruebas:**
- `make lint`/`make typecheck` → limpio (backend + frontend, 0 errores).
- Backend unit (`pytest -m "not docker"`) → 277 passed (+17 sobre la base de Fase 24).
- Backend integración/API/seguridad Docker (`make test-integration`) → 433 passed (+26 sobre la base de Fase 24 — incluye checkout completo, webhook con replay/idempotencia verificados por conteo, admin cross-tenant de compras auditado).
- Frontend (`pnpm test`) → 212 passed (+16 sobre la base de Fase 24).
- `pnpm build` → build de producción exitoso.
- `make test-e2e` → 20/20 specs passed (+2 nuevos: `billing-checkout.spec.ts`/`admin-console.spec.ts`, tras diagnosticar y corregir los 2 bugs reales descritos arriba), sin regresión en los 18 specs existentes.
- `make contracts` corrido dos veces seguidas → sin diff adicional entre corridas.
- `git diff --check` → limpio.
- `pytest -m stripe_sandbox` → no ejecutado en esta sesión (requiere credenciales reales de Stripe Test Mode que el founder debe provisionar — ver Bloqueante #3 e instrucciones en `deployment.md`); el test existe y se verificó que se auto-salta correctamente sin `STRIPE_SECRET_KEY`.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):**
- Ninguna adicional requiere ADR más allá de ADR 0025 (ya redactado, cubre la elección de Checkout hospedado sobre Payment Intents/Elements directo).

**Deuda técnica introducida:**
- `useReportJobStatus.ts` (Fase 23) comparte la misma forma de construcción-durante-render vulnerable a StrictMode que `usePurchaseStatus.ts` tenía — no confirmada como manifestada en producción (su E2E no expone la misma secuencia de remount forzado), no corregida en esta fase por estar fuera del alcance autorizado. Revisar si se detecta el mismo síntoma (estado de polling que nunca progresa) en reportes.
- El cobro de prueba real en Stripe Test Mode (mitad del criterio de aceptación que requiere una cuenta externa) queda pendiente de ejecución manual por el founder — procedimiento completo documentado en `deployment.md`, evidencia (IDs `cs_test_.../pi_test_...`) a registrar en `current-phase.md` una vez ejecutada.

**Instrucciones para la siguiente sesión:**
- Próxima fase según `backlog.md` (columna "Depende de"): **Fase 26** (Hardening) — confirmar dependencias antes de asumir.
- Antes de considerar Fase 25 100% cerrada operativamente (no solo en código): el founder debe ejecutar la demo manual de Stripe Test Mode (`deployment.md`, sección "Stripe (billing, Fase 25)") y la evidencia debe registrarse en `current-phase.md`.
- No tocar todavía: enforcement de entitlements (decisión de producto explícita de no implementarlo en esta fase, no un olvido); consola admin completa de la spec §12.2; `useReportJobStatus.ts` (ver deuda técnica arriba) salvo que se confirme un síntoma real.
- Housekeeping pendiente heredado, sin cambios: ramas `phase-14` a `phase-24` siguen sin borrarse (requiere confirmación explícita del founder); rama local `main` sigue desactualizada (requiere `git pull`/fast-forward explícito).

### Sesión — 2026-08-07 — Fase 24 (E11, Bloque 6 "Hardening y despliegue"): Notificaciones reales (Azure Communication Services) + centro in-app

**Resumen:** Sesión que comenzó en Plan Mode exclusivo: verificó el cierre formal de Fase 23 con evidencia de Git/GitHub (PR #37 fusionado a `main`, merge commit `40422bb5`), identificó Fase 24 por evidencia documental cruzada de `backlog.md`/`roadmap.md`/`session-handoff.md`, y produjo un plan técnico completo con una única pregunta genuinamente bloqueante: cuántos de los 9 eventos de la tabla original de la spec (§11) conectar en esta fase, dado que el criterio de aceptación textual del backlog solo exige "al menos un evento clave" pero múltiples fases previas (15, 17, 21, 22) habían diferido explícitamente "notificaciones reales" a esta fase exacta para otros eventos también. El founder resolvió explícitamente por la Opción A (8 de 9 eventos — todos salvo "Fecha próxima/vencida", el único sin punto de enganche síncrono existente). Tras la autorización ("apruebo la recomendación de usar la opción A"), ejecución completa en 6 bloques incrementales (modelo+migración, provider+worker, `NotificationService`+router, enganche de los 8 eventos, frontend, E2E+documentación), cada uno verificado contra Docker real antes de avanzar.

**Bugs reales detectados y corregidos durante la propia sesión de implementación (no heredados):** (1) un `return` prematuro insertado por error en `qna/service.py::publish_answer` dejaba código original inalcanzable — detectado vía `git diff` antes de correr ningún test, corregido eliminando el `return` duplicado. (2) el test de aislamiento por identidad reveló que `NotificationRepository.mark_read`/`mark_all_read` debían filtrar por `recipient_membership_id`, no solo `_id` — ya implementado correctamente desde el diseño original, el test solo lo confirmó. (3) un bug de contaminación cross-spec en el E2E existente: crear un `VendorOrganization` nuevo desde `notifications.spec.ts` en el tenant compartido "Acme Compradora (dev)" (el mismo que usan `qna.spec.ts`/`vendor-onboarding.spec.ts`) contaminaba el picker "Vincular proveedor" de cualquier otra evaluación con un candidato no-vinculado adicional, dependiendo del orden de ejecución alfabético de los specs — corregido ejecutando el nuevo spec enteramente contra el tenant "Globex Compradora (dev)" (sin uso previo en E2E), aislándolo por completo del catálogo compartido.

**Decisión bloqueante resuelta por el founder (plan §4):**
1. Alcance de eventos conectados: **Opción A** — 8 de 9 (invitación, publicación, pregunta recibida, respuesta publicada, propuesta enviada, reapertura, aprobación pendiente ×2, cierre). "Fecha próxima/vencida" queda fuera de alcance (requiere generalizar `time_based_tasks` hacia un barrido con deduplicación por umbral — candidato a Bloque 6/hardening posterior).

**Decisiones no bloqueantes resueltas por evidencia/razonamiento (plan §7, ninguna requirió al founder):**
1. Fila in-app síncrona best-effort + envío de email asíncrono vía worker (split "Report"-like), no todo síncrono ni todo asíncrono.
2. Id determinístico (no `uuid4()`) — permite llamar `notify()` sin envolver desde `_finish_publish` (idempotente vía `DuplicateKeyError`-como-éxito).
3. `EmailStatus` sin valor `"failed"` persistido — un intento fallido permanece `pending` con reintento agendado; `failed` solo existe como label de auditoría.
4. Sin Mailhog/Mailpit (cierra la apertura de ADR 0020) — `LoggingNotificationEmailProvider` + aserciones sobre logs en integración es la respuesta MVP honesta, sin emulador real de ACS contra el cual probar nada significativo.
5. Validador de configuración solo-producción, no fail-closed-en-todo-ambiente — sin gate legal documentado equivalente al de Foundry/ADR 0011.
6. Retención 90 días (`notification_retention_days`), por analogía con `audit_event_retention_days`/`ai_execution_retention_days`.

**Archivos tocados:** ver el detalle completo por bloque en `current-phase.md` — resumen: nuevo módulo `procurawise/notifications/` (`models.py`/`exceptions.py`/`repository.py`/`provider.py`/`azure_acs_email_provider.py`/`service.py`/`schemas.py`/`worker.py`/`dependencies.py`/`router.py`), `shared/tenant_collection.py` (+`update_many`), `shared/worker_loop.py` (+`time_based_tasks`, aditivo), `shared/config.py` (+7 settings), `audit/models.py` (+1 `AuditResourceType`, +3 `AuditAction`), `identity/service.py`/`identity/repository.py` (+`resolve_recipient_email`/`find_vendor_contacts_for_org`), `api/main.py`/`worker/main.py` (routers/dispatch registrados), `migrations/0021_notifications_indexes.py` (nuevo), `pyproject.toml` (+1 dependencia), ADR 0024 (nuevo); 6 servicios de dominio enganchados (`identity/vendor_auth_service.py`, `evaluations/service.py`, `scoring/service.py`, `decisions/service.py`, `qna/service.py`, `proposals/service.py`) + sus routers/composition points (incluidos 3 archivos de test de integración que instancian servicios directamente); frontend: `features/notifications/hooks/{useNotificationsPolling,useBuyerNotifications,useVendorNotifications}.ts` (nuevos), `features/notifications/components/{NotificationsBell,BuyerNotificationsBell,VendorNotificationsBell}.tsx` (nuevos), `app/AppShell.tsx` (+prop `notifications`), `app/router.tsx` (+inyección por layout), `lib/enumLabels.ts` (+`notificationEventLabels`), `components/ui/dropdown-menu.tsx` (nuevo, `npx shadcn add`, cero dependencias npm nuevas); `e2e/notifications.spec.ts` (nuevo); tests backend nuevos: `test_notification_models.py`, `test_notification_provider.py`, `test_notifications_worker.py`, `test_notification_service.py`, `test_notification_events_workflow.py`, `test_notification_isolation.py`; `NotificationsBell.test.tsx` (frontend).

**Resultado de pruebas:**
- `make lint`/`make typecheck` → limpio (backend + frontend).
- Backend unit (`pytest -m "not docker"`) → 260 passed (+5 sobre la base de Fase 23).
- Backend integración/API/seguridad Docker (`make test-integration`) → 407 passed (+15 sobre la base de Fase 23 — incluye el ciclo completo de `NotificationService` (notify→job→sent, idempotencia, reintentos, agotamiento, requeue sweep), los 8 eventos reales vía HTTP, y 7 tests de aislamiento negativo dedicados, tenant cruzado + identidad dentro del mismo tenant).
- Frontend (`pnpm test`) → 196 passed (+5 sobre la base de Fase 23).
- `pnpm build` → build de producción exitoso.
- `make test-e2e` → 18/18 specs passed (+1 nuevo: `notifications.spec.ts`, tras corregir el bug de contaminación cross-spec descrito arriba).
- `make contracts` corrido dos veces seguidas → sin diff.
- No aplica `make test-integration-ai` — Fase 24 no toca `ai/`/Service Bus.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):**
- Ninguna adicional requiere ADR más allá de ADR 0024 (ya redactado y aprobado por el founder para el proveedor de email/ACS).

**Deuda técnica introducida:**
- Ninguna material — `Notification` es una entidad enteramente nueva sin backfill; ninguna evaluación pre-Fase-24 requiere migración de datos.

**Instrucciones para la siguiente sesión:**
- Próxima fase según `backlog.md` (columna "Depende de" — fuente autoritativa, no `session-handoff.md`): **Fase 25**, Billing/Admin básico P1 (Stripe checkout sandbox + consola admin cross-tenant auditada) — depende de Fase 9 (✅ cerrada, sin dependencia directa de Fase 24).
- No tocar todavía: barrido de "Fecha próxima/vencida" (requiere generalizar `time_based_tasks`, diferido a Bloque 6/hardening); preferencias/opt-out de notificación (spec §17 las menciona, ningún otro documento lo hace); página `/notifications` dedicada (el dropdown cubre el MVP a la escala de NFR-003).
- Housekeeping pendiente heredado, sin cambios: ramas `phase-14` a `phase-23` siguen sin borrarse (requiere confirmación explícita del founder); rama local `main` sigue desactualizada (requiere `git pull`/fast-forward explícito).

### Sesión — 2026-08-06 — Fase 23 (E10, cierre Bloque 5 / inicio Bloque 6): Reportes/exports asíncronos (8 tipos) + import Excel/CSV de requerimientos

**Resumen:** Sesión que comenzó en Plan Mode exclusivo: verificó el cierre formal de Fase 22 con evidencia de Git/GitHub (PR #36 fusionado a `main`, merge commit `7c166c9`, 8/8 checks verdes), identificó Fase 23 por evidencia documental cruzada de `backlog.md`/`roadmap.md`/`session-handoff.md`, y produjo un plan técnico completo con una única pregunta genuinamente bloqueante: qué librerías de generación de PDF/XLSX/DOCX adoptar (CLAUDE.md §8 exige un ADR antes de agregar cualquier dependencia pesada, y ninguna existía en el proyecto). El founder resolvió explícitamente por la Opción A (`reportlab`+`openpyxl`+`python-docx`+`csv` stdlib, documentado en ADR 0023). Tras la autorización explícita del founder ("apruebo también avanzar con la implementación de este plan"), ejecución completa en 8 bloques incrementales (dependencias+modelo+migración, job asíncrono+worker, renderers PDF/DOCX, renderers XLSX/CSV, persistencia Blob+descarga, import Excel/CSV, frontend, E2E+documentación), cada uno verificado contra Docker real antes de avanzar. Dos bugs reales detectados y corregidos durante la propia sesión de implementación (no heredados): `ReportService.list_reports()` no validaba tenant ownership de la evaluación antes de consultar (detectado por el propio test de aislamiento nuevo, devolvía 200 vacío en vez de 404), y `useReportJobStatus.ts` (calcado del hook de Fase 13) nunca comprometía el estado `succeeded` al DOM bajo React 19 con varias queries de React Query concurrentes (detectado por `ReportsPage.test.tsx`, resuelto migrando a `useSyncExternalStore` con snapshot memoizado).

**Decisión bloqueante resuelta por el founder (ver plan §9, no por evidencia documental):**
1. Generación de PDF/XLSX/DOCX vía `reportlab`+`openpyxl`+`python-docx` (Opción A, ver ADR 0023) — las tres son pure-Python (sin dependencias de sistema, a diferencia de WeasyPrint), `openpyxl` cubre a la vez exportar XLSX y leer el import de Requirements, y `python-docx` permite entregar el "Documento formal de RFP" en Word+PDF como pide la spec textualmente, sin diferir DOCX a una fase futura.

**Decisiones no bloqueantes resueltas por evidencia (ver plan §10, ninguna requirió al founder):**
1. Ningún reporte visible al proveedor en esta fase — sin evidencia que lo requiera, queda para Fase 24+.
2. Sin `EvaluationStatus` nuevo (`closed`/`archived`) — `completed`+`Decision.status=="approved"` ya representan el cierre.
3. `Report` es colección propia (no extensión de `Document`) — grain distinto (por evaluación, no por proposal/requirement), ciclo de vida distinto (job asíncrono vs. upload síncrono).
4. Readiness heterogénea por tipo (matriz completa en `current-phase.md`) — `decision_record` es el único con precondición dura (`Decision.status=="approved"`).
5. Import de Requirements restringido a `Evaluation.status=="draft"`, reutilizando `add_requirements_bulk` (Fase 11) sin un camino de escritura propio.
6. No se exporta auditoría como noveno tipo de reporte — no es uno de los 8 entregables textuales de la spec §10.

**Archivos tocados:** ver el detalle completo por bloque en `current-phase.md` — resumen: nuevo módulo `procurawise/reports/` (`models.py`/`exceptions.py`/`repository.py`/`service.py`/`schemas.py`/`router.py`/`worker.py`/`assembly.py`/`render_types.py`/`renderers/{pdf,docx,xlsx,csv}.py`/`dependencies.py`/`import_types.py`/`import_parsing.py`/`import_service.py`/`import_schemas.py`/`import_router.py`), `shared/worker_loop.py` (nuevo, genérico, `ai/worker.py` intacto), `shared/config.py` (+4 settings), `audit/models.py` (+1 `AuditResourceType`, +5 `AuditAction`), `api/main.py`/`worker/main.py` (routers/dispatch registrados), `migrations/0020_reports_indexes.py` (nuevo), `pyproject.toml` (+3 dependencias), ADR 0023 (nuevo); frontend: `features/reports/hooks/useReportJobStatus.ts` (nuevo), `features/reports/pages/ReportsPage.tsx` (nuevo), `features/evaluations/components/ImportRequirementsDialog.tsx` (nuevo), `features/evaluations/components/EvaluationTabNav.tsx` (+tab "Reportes"), `app/router.tsx` (+ruta), `lib/enumLabels.ts` (+`reportTypeLabels`/`reportFormatLabels`/`reportStatusLabels`); `e2e/report-generation.spec.ts`/`e2e/requirements-import.spec.ts` (nuevos); tests backend nuevos: `test_report_models.py`, `test_shared_worker_loop.py`, `test_reports_worker.py`, `test_reports_assembly.py`, `test_reports_import_parsing.py`, `test_report_generation_workflow.py`, `test_requirements_import_workflow.py`, `test_report_isolation.py`; `ReportsPage.test.tsx`/`ImportRequirementsDialog.test.tsx` (frontend).

**Resultado de pruebas:**
- `make lint`/`make typecheck` → limpio (backend + frontend).
- Backend unit (`pytest -m "not docker"`) → 255 passed (+28 sobre la base de Fase 22).
- Backend integración/API/seguridad Docker (`make test-integration`) → 392 passed (+18 sobre la base de Fase 22 — incluye los 8 tipos × formatos válidos generando un archivo real con firma binaria correcta, idempotencia del job ante reintento, readiness gateada por tipo, flujo HTTP completo de import, y 9 tests de aislamiento negativo dedicados nuevos).
- Frontend (`pnpm test`) → 191 passed (+7 sobre la base de Fase 22).
- `pnpm build` → build de producción exitoso.
- `make test-e2e` → 17/17 specs passed (+2 nuevos: `report-generation.spec.ts`/`requirements-import.spec.ts`, tras corregir un primer intento que usaba `page.goto()` para navegar a rutas autenticadas y perdía el JWT en memoria).
- `make contracts` corrido dos veces seguidas → sin diff.
- No aplica `make test-integration-ai` — Fase 23 no toca `ai/`/Service Bus.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):**
- Ninguna adicional requiere ADR más allá de ADR 0023 (ya redactado y aprobado por el founder para las dependencias de generación de reportes).

**Deuda técnica introducida:**
- Ninguna material — `Report` es una entidad enteramente nueva sin backfill; ninguna evaluación pre-Fase-23 requiere migración de datos.

**Instrucciones para la siguiente sesión:**
- Próxima fase según `backlog.md` (columna "Depende de" — fuente autoritativa, no `session-handoff.md`): **Fase 24**, notificaciones reales (Azure Communication Services) + centro in-app — depende de Fase 23 (✅ cerrada).
- No tocar todavía: adjudicación contractual/firma electrónica (fuera de alcance permanente del MVP); visibilidad del proveedor sobre reportes/decisión (no confirmada para ninguna fase concreta todavía); export de auditoría como reporte (no solicitado, puede agregarse trivialmente reusando la arquitectura de `reports/` si el founder lo pide).
- Housekeeping pendiente heredado, sin cambios: ramas `phase-14` a `phase-22` siguen sin borrarse (requiere confirmación explícita del founder); rama local `main` sigue desactualizada (requiere `git pull`/fast-forward explícito).

### Sesión — 2026-08-06 — Fase 22 (E9, Bloque 5 "Decisión"): `decisions` — vista de aprobador + memo de cierre

**Resumen:** Sesión que comenzó en Plan Mode exclusivo: verificó el cierre formal de Fase 21 con evidencia de Git/GitHub (PR #35 fusionado a `main`, merge commit `d6df0ba`, 8/8 checks verdes), identificó Fase 22 por evidencia documental cruzada de `backlog.md`/`roadmap.md`/`session-handoff.md` (sin ADR dedicado que la resolviera de antemano, a diferencia de Fase 21), y produjo un plan técnico completo con una única pregunta genuinamente bloqueante: si la aprobación de la decisión debía reutilizar `Evaluation.approver_membership_id` (Fase 12) o requerir una asignación propia e independiente. El founder resolvió explícitamente por la asignación propia (Opción B), con precisiones vinculantes sobre la UX (sugerencia no vinculante del aprobador de publicación, nunca copiado automáticamente). Tras la autorización explícita del founder ("autorizo avanzar con la implementacion de esta fase"), ejecución completa en 7 bloques incrementales (modelo+repository+readiness, borrador y selección, asignación de aprobador propio, solicitud/retiro, aprobación+snapshot inmutable, frontend, E2E+documentación), cada uno verificado contra Docker real antes de avanzar. Dos bugs reales detectados y corregidos durante la propia sesión de implementación (no heredados): un `approve()` sin recuperación ante fallo parcial (detectado por diseño, antes de escribir el test), y un ciclo de gating imposible en la UI del botón "Solicitar aprobación" (detectado por el E2E, no por los tests unitarios que mockean por endpoint).

**Decisión bloqueante resuelta por el founder (ver plan §9, no por evidencia documental):**
1. `Decision.approver_membership_id` es un campo propio e independiente — nunca copiado de ni escrito hacia `Evaluation.approver_membership_id`. El owner puede elegir a la misma persona que aprobó la publicación o a una distinta. La UI puede sugerir el aprobador de publicación como valor inicial de formulario, pero nunca se persiste hasta una acción explícita del owner sobre `POST /decision/approver`. Motivo del founder: evita acoplar dos gates distintos del ciclo de vida y preserva la separación de funciones.

**Decisiones no bloqueantes resueltas por evidencia (ver plan §10, ninguna requirió al founder):**
1. `Decision` solo creable/editable mientras `Evaluation.status == "completed"` — evita reabrir `complete_evaluation()` (Fase 20) o `ProposalService.reopen()` (Fase 21).
2. Un único proveedor seleccionable + opción explícita "proceso desierto" — sin selección múltiple, sin señal de producto que la pida.
3. `Decision.status` reutiliza la forma de `ApprovalStatus` (4 valores, `rejected` no terminal) pero como tipo propio, no importado.
4. Justificación siempre obligatoria (no condicionada a "difiere de un ranking", que el sistema deliberadamente no calcula).
5. `Decision`/`DecisionSnapshot` como colecciones propias, no campos embebidos en `Evaluation`.
6. `snapshot_id` de `DecisionSnapshot` determinístico = `evaluation_id`, mismo truco de idempotencia que `EvaluationSnapshot`.

**Archivos tocados:** ver el detalle completo por bloque en `current-phase.md` — resumen: nuevo módulo `procurawise/decisions/` (`models.py`/`exceptions.py`/`repository.py`/`snapshot_repository.py`/`service.py`/`schemas.py`/`router.py`), `audit/models.py` (+7 `AuditAction`, +`"decision"` en `AuditResourceType`), `api/main.py` (router registrado), `migrations/0019_decisions_indexes.py` (nuevo); frontend: `features/decisions/pages/DecisionPage.tsx` (nuevo), `features/evaluations/components/EvaluationTabNav.tsx` (+tab "Decisión"), `app/router.tsx` (+ruta), `lib/enumLabels.ts` (+`decisionStatusLabels`/`decisionOutcomeLabels`); `e2e/decision-approval.spec.ts` (nuevo); tests backend nuevos: `test_decision_models.py`, `test_decision_workflow.py`, `test_decisions_audit_instrumentation.py`, `test_decision_isolation.py`; `DecisionPage.test.tsx` (frontend).

**Resultado de pruebas:**
- `make lint`/`make typecheck` → limpio (backend + frontend).
- Backend unit (`pytest -m "not docker"`) → 227 passed (+8 sobre la base de Fase 21).
- Backend integración/API/seguridad Docker (`make test-integration`) → 374 passed (+19 sobre la base de Fase 21 — incluye flujo feliz con aprobador de decisión distinto del de publicación, recuperación ante fallo parcial simulado, rechazo→edición→reaprobación, "proceso desierto", autoaprobación bloqueada, 7 casos de aislamiento cross-tenant dedicados, auditoría sin fuga de justificación).
- Frontend (`pnpm test`) → 184 passed (+5 sobre la base de Fase 21).
- `pnpm build` → build de producción exitoso.
- `make test-e2e` → 15/15 specs passed (+1 nuevo: `decision-approval.spec.ts`, tras corregir el bug de gating de UI).
- `make contracts` corrido dos veces seguidas → sin diff.
- No aplica `make test-integration-ai` — Fase 22 no toca `ai/`/Service Bus.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):**
- Ninguna requiere ADR — la independencia del aprobador de decisión es una decisión de producto/autorización sobre un módulo nuevo, no una reapertura de una decisión arquitectónica ya aprobada (no toca base de datos, patrón de comunicación, ni división de servicios).

**Deuda técnica introducida:**
- Ninguna material — `Decision`/`DecisionSnapshot` son entidades enteramente nuevas sin backfill; ninguna evaluación pre-Fase-22 requiere migración de datos (la ausencia de `Decision` es un estado válido).

**Instrucciones para la siguiente sesión:**
- Próxima fase según `backlog.md` (columna "Depende de" — fuente autoritativa, no `session-handoff.md`): **Fase 23**, reportes/exports asíncronos vía worker (8 entregables de §10 de la spec) + import Excel/CSV con preview+mapeo — depende de Fase 22 (✅ cerrada).
- No tocar todavía: notificaciones reales (Fase 24, requiere Fase 23 primero); adjudicación contractual/firma electrónica (fuera de alcance permanente del MVP); visibilidad del proveedor sobre la decisión (no confirmada para ninguna fase concreta todavía).
- Housekeeping pendiente heredado, sin cambios: ramas `phase-14` a `phase-21` siguen sin borrarse (requiere confirmación explícita del founder); rama local `main` sigue desactualizada (requiere `git pull`/fast-forward explícito).

### Sesión — 2026-08-05 — Fase 21 (E8, Bloque 5 "Decisión"): Ronda final de negociación — Ronda 0 + Ronda 1 opcional (BAFO), versionado, invalidación de scores, TCO por versión

**Resumen:** Sesión de planeación exclusiva en Plan Mode que primero verificó el cierre formal de Fase 20 con evidencia de Git/GitHub (PR #34 fusionado a `main`, merge commit `faf5691`, 8/8 checks verdes, base correcta `80dfe68`), y después identificó Fase 21 por evidencia documental cruzada de `backlog.md`/`roadmap.md` y, sobre todo, [ADR 0013](../architecture/decisions/0013-versionado-propuestas-negociacion.md) (advertido explícitamente de no asumirla solo por la secuencia histórica esperada, aunque coincidiera con ella). A diferencia de Fase 19/20, esta fase contó con un ADR dedicado que ya resolvía la mayoría del diseño de alto nivel — **no sobrevivió ninguna pregunta genuinamente bloqueante**; todas las decisiones de diseño se resolvieron con evidencia de ADR 0013 + lectura directa del código existente, documentadas en el plan (§9) como decisiones razonadas. Tras la autorización explícita del founder ("Autorizo avanzar con la implementacion de los cambios a codigo"), ejecución completa en 7 bloques incrementales (modelo de versionado+migración, reapertura backend, submit extendido+herencia real, invalidación/herencia de scores+tests de aceptación dedicados, contratos, frontend, E2E+documentación), cada uno verificado contra Docker real antes de avanzar.

**Decisiones no bloqueantes resueltas por evidencia (ver plan §9, ninguna requirió al founder):**
1. Reutilizar `EvaluationStatus="collecting_responses"`/`ProposalStatus="draft"` para la Ronda 1, sin estados nuevos — `documents/service.py`/`qna/service.py`/`proposals/service.py` ya gatean su escritura exactamente en esos dos valores.
2. `Proposal.round` (nuevo) separado de `Proposal.version` (ya existente, concurrencia optimista) — evita un overload semántico, confirmado leyendo que `version` se incrementa en cada edición individual, no solo en submit.
3. `Score` no cambia de grano (ya vivía por `snapshot_id` desde Fase 9) — solo se corrige el filtro de lectura, con fallback a la ronda anterior únicamente para respuestas `inherited` sin cambio.
4. `EconomicAssessment` gana `snapshot_id` pero sin fallback — recalificación completa cada ronda, porque el TCO (70% de su score) cambia estructuralmente en cuanto hay costos modificados y no tiene una unidad "qué cambió" por criterio como sí la tiene `Score` por `requirement_id`.
5. Sin entidad `NegotiationRound` separada — la ronda vive como campos directamente en `Proposal` (máximo 2 rondas, sin ciclo de vida propio que justifique una entidad dedicada en el MVP).

**Archivos tocados:** ver el detalle completo por bloque en `current-phase.md` — resumen: `proposals/models.py`/`schemas.py`/`service.py`/`router.py`/`repository.py`/`exceptions.py` (+versionado `Proposal.round`/`snapshots`, +`ProposalService.reopen()`, +endpoint `POST .../reopen`, +`SnapshotResponse.cost_items`/`tco_result`), `tco/models.py` (+`CostItemVersionStatus`), `scoring/models.py`/`repository.py`/`service.py` (+`EconomicAssessment.snapshot_id`, +`_scores_for_current_snapshot()`), `evaluations/repository.py` (+`update_deadline_while_collecting`), `vendor_portal/schemas.py`/`router.py`/`service.py` (extendidos), `audit/models.py` (+`proposal_reopened`), `migrations/0018_economic_assessments_snapshot_id_index.py` (nuevo); frontend: `features/proposals/components/ReopenProposalDialog.tsx` (nuevo), `features/proposals/pages/ProposalVersionComparisonPage.tsx` (nuevo), `features/vendor-portal/pages/VendorProposalDetailPage.tsx`/`components/CostItemsPanel.tsx` (extendidos con banner/badges), `features/scoring/pages/ScoringPage.tsx` (migrado de `.snapshot` a `.snapshots.at(-1)`), `lib/enumLabels.ts` (+`answerStatusLabels`/`costItemStatusLabels`), `app/router.tsx` (+ruta `/versions`); `e2e/proposal-negotiation.spec.ts` (nuevo); ~10 archivos de test backend nuevos/extendidos (incl. `test_proposal_reopen.py`, `test_negotiation_round_scoring.py`), 2 de test frontend nuevos.

**Resultado de pruebas:**
- `make lint`/`make typecheck` → limpio (backend + frontend).
- Backend unit (`pytest -m "not docker"`) → 219 passed (+9 sobre la base de Fase 20).
- Backend integración/API/seguridad Docker (`make test-integration`) → 355 passed (+14 sobre la base de Fase 20 — incluye la prueba directa del criterio de aceptación: invalidación de score por respuesta modificada con fallback automático para lo no modificado, `EconomicAssessment` sin herencia entre rondas, TCO nunca mezclado entre Ronda 0/Ronda 1 con totales fijos exactos, reapertura selectiva con 2 proveedores reales, máximo de 2 rondas rechazado con 409).
- Frontend (`pnpm test`) → 179 passed (+9 sobre la base de Fase 20).
- `pnpm build` → build de producción exitoso.
- `make test-e2e` → 14/14 specs passed (+1 nuevo: `proposal-negotiation.spec.ts`).
- `make contracts` corrido dos veces seguidas → sin diff.
- No aplica `make test-integration-ai` — Fase 21 no toca `ai/`/Service Bus.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):**
- Ninguna — todas las decisiones de diseño de esta fase ya estaban suficientemente ancladas en ADR 0013; ninguna contradice ni extiende una decisión arquitectónica ya aprobada.
- `SnapshotResponse` ganó `cost_items`/`tco_result` (no estaba en el plan original §12.1, que solo mencionaba respuestas/requerimientos) — agregado durante Bloque 6 al descubrir que la vista de comparación de rondas necesita leer el TCO/costos históricos de cada snapshot, dato que `ProposalSnapshot` ya congelaba desde Fase 19 pero que ningún response schema exponía todavía — no requiere ADR (campo de lectura adicional sobre un dato ya persistido, mismo patrón que el resto de la respuesta).

**Deuda técnica introducida:**
- Ninguna material — todos los campos nuevos son aditivos con default seguro (`round=0`, `snapshots` derivado del campo legado `snapshot`, `status="modified"`/`source_proposal_version=None`) para documentos pre-Fase-21, sin backfill.

**Instrucciones para la siguiente sesión:**
- Próxima fase según `backlog.md` (columna "Depende de" — fuente autoritativa, no `session-handoff.md`): **Fase 22**, vista de aprobador + memo de cierre (`decisions`) — depende de Fase 21 (✅ cerrada) y nunca implica adjudicación automática, la decisión final siempre requiere aprobación humana explícita (CLAUDE.md §6/§8).
- No tocar todavía: rondas de negociación adicionales (Ronda 2+, prohibido por `mvp-scope.md` línea 41); reportes ejecutivos (Fase 23); notificaciones reales (Fase 24).
- Housekeeping pendiente heredado, sin cambios: ramas `phase-14` a `phase-20` siguen sin borrarse (requiere confirmación explícita del founder); rama local `main` sigue desactualizada (requiere `git pull`/fast-forward explícito, fuera de alcance de una sesión de solo lectura).

### Sesión — 2026-08-05 — Fase 20 (E8): Scoring económico completo — TCO normalizado 70%, condiciones comerciales 15%, riesgo/predictibilidad 15%, fórmula final 40/20/40

**Resumen:** Sesión de planeación exclusiva en Plan Mode que primero resolvió, con evidencia de Git/GitHub (no asumida), una inconsistencia aparente entre dos reportes sobre el estado de cierre de Fase 19 (ambos eran correctos para su propio momento — PR #33 se fusionó *entre* sesiones, mismo patrón ya observado en cada cierre de fase anterior), y después identificó Fase 20 por evidencia documental cruzada de `backlog.md`/`roadmap.md` (advertido explícitamente de no asumirla solo por la secuencia histórica esperada). Identificó **una única pregunta genuinamente bloqueante** — el alcance de la "configurabilidad" de criterios/pesos económicos que ADR 0009 menciona sin especificar (¿solo pesos editables, o autoría dinámica completa de criterios?) — resuelta por el founder en la misma sesión vía `AskUserQuestion` (pesos editables, los 10 criterios de ADR 0009 fijos). Tras la aprobación del plan y autorización explícita de avanzar, ejecución completa en 7 bloques incrementales (modelo económico+pesos, fórmulas puras+tests exhaustivos, captura backend+endpoint de pesos, integración a `get_results()`/`complete_evaluation()`, contratos, frontend, E2E+documentación), cada uno verificado contra Docker real antes de avanzar.

**Decisión bloqueante resuelta por el founder (2026-08-05):**
1. Configurabilidad de criterios económicos (Pregunta Bloqueante #1 del plan): los 5 criterios comerciales y los 5 de riesgo de ADR 0009 son fijos en toda evaluación (mismo nombre/clave siempre) — el `evaluation_owner` solo puede reajustar los pesos numéricos de cada grupo antes de publicar (deben sumar 100% cada uno), congelados en `EvaluationSnapshot` al publicar; no existe un CRUD para agregar/quitar/renombrar criterios.

**Decisión de diseño central (no bloqueante, resuelta por evidencia):** nueva entidad `EconomicAssessment` (no una extensión de `Score`, que está atado a `requirement_id` y no tiene análogo cuando no hay Requirements — economic nunca los tiene). El TCO normalizado (70% del económico) nunca se persiste — se calcula en vivo comparando `TcoResult.grand_total` (Fase 19) entre las propuestas enviadas, mismo principio que `functional_points`/`technical_points`/`partial_result` ya usan. Autorización reutiliza `Assignment`/`enforce_section_assignment` (Fase 9/18) con un sentinel fijo `section="economic"`, sin inventar un segundo mecanismo de permisos.

**Archivos tocados:** ver el detalle completo por bloque en `current-phase.md` — resumen: `evaluations/models.py`/`schemas.py`/`service.py`/`router.py` (+`RequirementDimension`, +`EconomicCriteriaWeights`, +endpoint de pesos), `scoring/models.py`/`repository.py`/`service.py`/`router.py`/`schemas.py`/`exceptions.py` (+`EconomicAssessment`/`CriterionScore`, +`economic_formulas.py` nuevo, +integración a `get_results()`/`complete_evaluation()`, +endpoints `PUT`/`GET .../economic-assessment`), `assignments/service.py` (+`ECONOMIC_SECTION`), `audit/models.py` (+2 acciones), `ai/schemas.py` (`AIRequirementCandidate`/`TriggerSuggestionRequest` narrowed a `RequirementDimension`), `migrations/0017_economic_assessments_indexes.py` (nuevo); frontend: `features/scoring/components/EconomicAssessmentPanel.tsx` (nuevo), `features/scoring/pages/ScoringPage.tsx`/`ResultsPage.tsx` (extendidos), `features/evaluations/wizard/EconomicWeightsForm.tsx` (nuevo, montado en `WizardStepReview.tsx`), `lib/enumLabels.ts` (+`economicCriterionLabels`); `e2e/vertical-slice.spec.ts` (extendido, no un spec nuevo); ~6 archivos de test backend nuevos (unit+integración), 3 de test frontend nuevos.

**Resultado de pruebas:**
- `make lint`/`make typecheck` → limpio (backend + frontend).
- Backend unit (`pytest -m "not docker"`) → 210 passed (+20 sobre la base de Fase 19).
- Backend integración/API/seguridad Docker (`make test-integration`) → 341 passed (+19 sobre la base de Fase 19 — incluye la prueba directa del criterio de aceptación: 2 propuestas con TCO normalizado exacto 100%/50%, `final_result` ausente hasta completitud de las 3 dimensiones, `mandatory_alert` coexistiendo correctamente con la fórmula final).
- Frontend (`pnpm test`) → 170 passed (+9 sobre la base de Fase 19).
- `make test-e2e` → 13/13 specs passed (0 nuevos, `vertical-slice.spec.ts` extendido en el mismo archivo).
- `make contracts` corrido dos veces seguidas → sin diff.
- No aplica `make test-integration-ai` — Fase 20 no toca `ai/`/Service Bus.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):**
- Configurabilidad de pesos económicos — ya resuelta por el founder, ver arriba; no se documentó como ADR nuevo (detalle de implementación dentro del alcance ya cubierto por ADR 0009, no una decisión arquitectónica nueva).
- `RequirementDimension` como tipo más estrecho que `Dimension` para toda superficie de autoría de Requirements (`Requirement.dimension`, `RequirementCreateRequest`/`UpdateRequest`/`Response`, `AIRequirementCandidate`, `TriggerSuggestionRequest`) — no requiere ADR (refuerzo de tipo, no cambia ningún contrato ya aprobado ni agrega comportamiento nuevo).
- `GET /evaluations/{id}/proposals/{id}/economic-assessment` (no estaba en el plan original, que solo listaba `PUT`) — agregado durante Bloque 6 al descubrir que el frontend necesita leer los scores/`version` actuales antes de poder construir una actualización válida (mismo rol que `/results` cumple para `Score`, pero `EconomicAssessment` no tiene un agregado por-requirement del que colgarse) — no requiere ADR (endpoint de lectura adicional, mismo patrón 404-nunca-403 ya establecido).

**Deuda técnica introducida:**
- Ninguna material — `EconomicAssessment`/pesos económicos son aditivos; `Evaluation`/`EvaluationSnapshot` extendidos con default seguro para documentos pre-Fase-20, sin backfill.

**Instrucciones para la siguiente sesión:**
- Próxima fase según `backlog.md` (columna "Depende de" — fuente autoritativa, no `session-handoff.md`): **Fase 21**, ronda de negociación (ADR 0013 ya declara el diseño de versionado de propuesta al que `EconomicAssessment`/`CostItem` ya son compatibles sin cambios, atados a `proposal_id`).
- No tocar todavía: ranking/comparación entre proveedores en UI, reportes ejecutivos (fuera de alcance hasta fases posteriores); versión explícita de `EconomicAssessment` por ronda de negociación (Fase 21).
- Housekeeping pendiente heredado, sin cambios: ramas `phase-14` a `phase-19` siguen sin borrarse (requiere confirmación explícita del founder).

### Sesión — 2026-08-04 — Fase 19 (E8): `tco` — CostItem, cálculo TCO 1-5 años, FX congelado desde `FXRate`

**Resumen:** Sesión de planeación exclusiva en Plan Mode (verificación independiente del cierre de Fase 18 vía API de GitHub — PR #32, merge commit `a4dac51`, 8/8 checks verdes —, identificación de la siguiente fase confirmada por evidencia documental cruzada de `backlog.md`/`roadmap.md`/`mvp-scope.md`/`approved-mvp-plan.md` sin asumirla por la secuencia histórica esperada) que identificó **una única pregunta genuinamente bloqueante** — el algoritmo exacto de agregación del TCO por `CostItem` a través de los años, ausente de todo ADR/spec (solo el listado de campos existe) — resuelta por el founder en la misma sesión vía `AskUserQuestion` (fórmula única para los 3 tipos de costo, sin una segunda forma de campos para "variable"). Tras la aprobación del plan y autorización explícita de avanzar, ejecución completa en 7 bloques incrementales (modelo+FXRate admin, `TcoService` puro+tests exhaustivos de fórmula, captura vendor+preview, congelamiento en submit+lectura buyer, contratos, frontend, E2E+documentación), cada uno verificado contra Docker real antes de avanzar.

**Decisión bloqueante resuelta por el founder (2026-08-04):**
1. Fórmula TCO (Pregunta Bloqueante #1 del plan): una única fórmula para los 3 tipos de costo (único/recurrente/variable) — `monto(año Y) = cantidad × precio_unitario × frecuencia_anual × (1+incremento_anual)^(Y-año_inicio) × (1-descuento)` —, en vez de una tabla manual `{año:monto}` separada para "variable"; razonamiento aceptado: la especificación (§8.2) describe una única estructura de campos para las 3 categorías de tipo, sin evidencia de una segunda forma.

**Decisión de diseño central (no bloqueante, resuelta por evidencia):** el congelamiento de FX+costos+TCO ocurre dentro del mismo `ProposalService.submit()` ya existente, no en un endpoint nuevo — `TcoService.calculate()` es puro y nunca consulta `FXRateRepository` por sí misma, haciendo estructuralmente imposible que un recálculo posterior use una tasa distinta a la ya congelada.

**Archivos tocados:** ver el detalle completo por bloque en `current-phase.md` — resumen: nuevo módulo `tco/` (`models.py`, `repository.py`, `service.py`, `schemas.py`, `router.py`, `exceptions.py`), `evaluations/models.py`/`schemas.py`/`service.py`/`router.py` (+`base_currency`/`tco_horizon_years`), `proposals/models.py`/`repository.py`/`service.py` (+`cost_items` embebido, +congelamiento de TCO en `submit()`), `vendor_portal/schemas.py`/`service.py`/`router.py` (+CRUD de `CostItem` y preview), `admin/router.py` (+CRUD create-only de `FXRate`), `scoring/router.py` (respuesta de evaluación extendida), `migrations/0016_fx_rates_indexes.py` (nuevo); frontend: `features/vendor-portal/components/CostItemsPanel.tsx` (nuevo), `features/tco/pages/TcoResultPage.tsx` (nuevo), `features/vendor-portal/pages/VendorProposalDetailPage.tsx` (extendido), `features/proposals/pages/ProposalsPage.tsx` (+enlace "Ver TCO"), `app/router.tsx` (+ruta), `lib/enumLabels.ts` (+`costCategoryLabels`/`costTypeLabels`); `e2e/tco.spec.ts` (nuevo); ~10 archivos de test backend nuevos/extendidos, 2 de test frontend nuevos.

**Resultado de pruebas:**
- `make lint`/`make typecheck` → limpio (backend + frontend).
- Backend unit (`pytest -m "not docker and not docker_servicebus"`) → 190 passed.
- Backend integración/API/seguridad Docker (`make test-integration`) → 322 passed (incluye la prueba directa del criterio de aceptación: actualizar `FXRate` después del submit no cambia el TCO ya leído).
- Frontend (`pnpm test`) → 161 passed.
- `pnpm build` → build de producción exitoso.
- `make test-e2e` → 13/13 specs passed (1 nuevo — `tco.spec.ts`).
- `make contracts` corrido dos veces seguidas → sin diff.
- No aplica `make test-integration-ai` — Fase 19 no toca `ai/`/Service Bus (ADR 0020: sin cola para cálculos síncronos).

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):**
- Fórmula TCO — ya resuelta por el founder, ver arriba; no se documentó como ADR nuevo (detalle de cálculo, no una decisión arquitectónica ni de política de datos como ADR 0008/0009/0022).
- `Decimal`/`Decimal128` para todo monto monetario de `tco/` (nunca `float`) — desviación deliberada del único precedente existente (`proposals`' respuestas tipo `currency` usan `float`); justificada por precisión en sumas compuestas multi-año, no requiere ADR (decisión de implementación dentro de un módulo nuevo, no cambia un contrato ya aprobado).
- `FXRate` create-only (sin edición/borrado) — refuerza la garantía de inmutabilidad de snapshots sin necesitar un mecanismo de soft-delete; no requiere ADR (subconjunto más simple del CRUD ya anticipado por ADR 0008).

**Deuda técnica introducida:**
- Ninguna material — módulo `tco/` nuevo y aditivo; `Proposal`/`ProposalSnapshot`/`Evaluation` extendidos con campos opcionales/con default, compatibles con todos los documentos existentes sin backfill.

**Instrucciones para la siguiente sesión:**
- Próxima fase según `backlog.md` (fila 20, columna "Depende de" — fuente autoritativa, no `session-handoff.md`): **Fase 20**, scoring económico completo (TCO normalizado 70%, condiciones comerciales 15% con sub-pesos de ADR 0009, riesgo/predictibilidad 15%, fórmula final 40/20/40 + flags eliminatorios), depende de Fase 19 (cerrada en esta sesión). `Dimension` gana el valor `"economic"` en esa fase, no antes.
- No tocar todavía: `Dimension="economic"` (llega con Fase 20); versionado de `CostItem` por ronda de negociación (Fase 21, ADR 0013 ya declara la restricción "el TCO se recalcula completo por versión, nunca se mezclan costos de versiones distintas" — el diseño de esta fase ya es compatible sin cambios); UI de administración de `FXRate` (gestionado vía API, mismo precedente y founder decision de Fase 14 para `curated-sources`).
- Housekeeping pendiente heredado, sin cambios: ramas `phase-14`/`phase-15`/`phase-16`/`phase-17`/`phase-18` siguen sin borrarse (requiere confirmación explícita del founder).

### Sesión — 2026-08-03 — Fase 18 (E7): Evaluación asistida por IA (riesgos/score sugerido) con "aceptar o modificar" obligatorio

**Resumen:** Sesión de planeación exclusiva en Plan Mode (verificación independiente del cierre de Fase 17 vía API de GitHub — PR #31, merge commit `d3d9266`, 8/8 checks verdes —, 3 agentes de exploración en paralelo sobre `ai/`+worker+messaging, scoring/assignments/proposals, y especificación/compliance) que identificó **una única pregunta genuinamente bloqueante** — política de datos para enviar `ProposalAnswer` (protegido por NDA/Agreement) a Azure OpenAI, dado que ADR 0021 excluyó textualmente ese contenido de su alcance cubierto en Fase 13 — resuelta por el founder en la misma sesión vía `AskUserQuestion` (ADR nuevo, sin gate legal duro tipo Foundry). Tras la aprobación del plan y autorización explícita de avanzar, ejecución completa en 7 bloques incrementales (modelo+candidato+ADR 0022, servicio de dominio, worker con dispatch multi-topic, endpoints+extensión de `ScoringService`, contratos, frontend, E2E+documentación), cada uno verificado contra Docker/Service Bus real antes de avanzar.

**Decisión bloqueante resuelta por el founder (2026-08-03):**
1. Política de datos de IA (ADR 0022): se autoriza enviar `ProposalAnswer.value`/`vendor_comment` a Azure OpenAI para `score_suggestion`, documentado en un ADR nuevo, sin exigir una referencia de aprobación legal auditable como la de `FoundryWebSearchProvider` — razonamiento aceptado: Azure OpenAI permanece bajo el mismo Data Protection Addendum de Microsoft ya vigente desde Fase 13, a diferencia de Grounding with Bing (el motivo real del gate de ADR 0011).

**Decisión de diseño central (no bloqueante, resuelta por evidencia):** "aceptar o modificar" reutiliza el `PUT .../scores/{requirement_id}` ya existente desde Fase 9 — sin endpoint nuevo que escriba `Score`. La sugerencia de IA solo prellena el formulario ya existente; `ScoreWriteRequest` gana `source_ai_execution_id` opcional para trazabilidad, y `ScoringService` deriva server-side si la escritura fue "accepted"/"modified" comparando contra el candidato original.

**Archivos tocados:** ver el detalle completo por bloque en `current-phase.md` — resumen: `ai/models.py` (+`score_suggestion` use_case, +`proposal_id`/`snapshot_id`), `ai/schemas.py` (+`AIScoreSuggestionCandidate` y schemas relacionados), `ai/service.py` (+`request_score_suggestion`/`process_score_suggestion_job`), `ai/worker.py`/`worker/main.py` (dispatch real multi-topic), `ai/router.py` (+`score_suggestion_router`), `scoring/models.py`/`schemas.py`/`service.py`/`repository.py` (+`source_ai_execution_id`, +`_ai_decision`), `audit/models.py` (+3 acciones), `migrations/0015_ai_executions_proposal_index.py`, `shared/config.py` (+`ai_score_suggestion_enabled`), `docs/architecture/decisions/0022-politica-datos-evaluacion-asistida-ia.md` (nuevo), `docker/servicebus-emulator/config.json` (+cola `ai-score-suggestion`); frontend: `features/evaluations/hooks/useAiScoreSuggestionJobStatus.ts` (nuevo), `features/scoring/pages/ScoringPage.tsx` (extendido), `lib/enumLabels.ts` (+`riskFlagLabels`); `e2e/ai-score-suggestions.spec.ts` (nuevo); 5 archivos de test backend nuevos/extendidos, 1 de test frontend nuevo.

**Resultado de pruebas:**
- `make lint`/`make typecheck` → limpio (backend + frontend).
- Backend unit (`pytest -m "not docker and not docker_servicebus"`) → 174 passed.
- Backend integración/API/seguridad Docker (`make test-integration`) → 299 passed.
- Backend Service Bus real (`make test-integration-ai`) → 6 passed (dispatch multi-topic probado de punta a punta).
- Frontend (`pnpm test`) → 154 passed.
- `pnpm build` → build de producción exitoso.
- `make test-e2e` → 12/12 specs passed (1 nuevo — `ai-score-suggestions.spec.ts`).
- `make contracts` corrido dos veces seguidas → sin diff.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):**
- ADR 0022 (política de datos) — ya escrito, ver arriba.
- `enforce_section_assignment` extraído de `scoring/service.py` a función de módulo (reutilizada por `ai/service.py`) — refactor de bajo riesgo, no requiere ADR (no cambia comportamiento, solo evita duplicar el gate de autorización).
- `useAiScoreSuggestionJobStatus.ts` diseñado con "suscribir antes de arrancar" (a diferencia del hook de Fase 13) tras encontrar una condición de carrera real en tests: con un fetch que resuelve muy rápido, `controller.start()` puede notificar antes de que el efecto de suscripción (creado en el patrón original) llegue a registrarse, perdiendo la actualización. No se tocó el hook de Fase 13 ya en producción — no requiere ADR (detalle de implementación de un hook nuevo, no un cambio al contrato de ADR 0012).

**Deuda técnica introducida:**
- Ninguna material — extensión aditiva de `AIExecution`/`Score` (campos opcionales, compatibles con documentos existentes), sin colección nueva.

**Instrucciones para la siguiente sesión:**
- Próxima fase según `backlog.md`: revisar `roadmap.md` Bloque 5 (Fases 19-23: TCO, scoring económico completo, ronda de negociación, decisión, reportes) — Fase 19 es la siguiente candidata directa (`tco`), depende de Fase 9 (cerrada).
- No tocar todavía: dimensión económica en evaluación asistida por IA (depende de que exista scoring económico real, Fases 19-20); Q&A/documentos como input de IA (recomendación no bloqueante, no comprometida); cancelación de job (`AIExecutionStatus` sin `cancelled`); rate limiting duro de IA (Fase 26, mismo riesgo aceptado que Fase 13).
- Housekeeping pendiente heredado, sin cambios: rama `phase-14/research-provider-curated-foundry` sigue sin borrarse (requiere confirmación explícita del founder); ramas `phase-15`/`phase-16`/`phase-17`/`phase-18` tampoco se han borrado.

### Sesión — 2026-08-03 — Fase 17 (E7): `qna` — preguntas ligadas/generales, publicación anonimizada/privada, notificaciones

**Resumen:** Sesión de planeación exclusiva en Plan Mode (verificación independiente del cierre de Fase 16 vía API de GitHub — no solo el reporte de la sesión anterior —, confirmación documental de que la siguiente fase es Fase 17/E7 sin asumirlo por el título sugerido, y resolución de ~160 preguntas de planeación agrupadas por tema) que concluyó **sin ninguna pregunta bloqueante** tras evidencia documental triple-consistente sobre los puntos más ambiguos (visibilidad binaria vs. ternaria; alcance real de "notificaciones"; alcance de "aclaraciones"/"asignación"). El founder aprobó el plan y autorizó avanzar a la implementación directamente, sin necesitar `AskUserQuestion` para ninguna decisión de esta fase. Ejecución completa en 8 bloques incrementales (modelo+repositorio+migración, servicio de dominio, endpoints de proveedor+auditoría, endpoints de comprador+visibilidad/anonimización, contratos, frontend proveedor, frontend comprador+polling, E2E+documentación), cada uno verificado contra Mongo real antes de avanzar.

**Decisiones de diseño resueltas por evidencia documental (ninguna bloqueante, ver `current-phase.md` para el detalle completo):**
1. Visibilidad binaria (`private`/`published_anonymized`), no ternaria — sin un tercer estado "público con identidad".
2. Notificaciones = in-app únicamente, reutilizando `AuditEvent`+`PollingController` (ADR 0012) — sin email/push real, sin entidad `Notification`, sin bounded context nuevo (precedente directo: Fase 15 ya reservó "notificaciones reales" para Fase 24).
3. "Aclaraciones" sobre `ProposalAnswer` diferidas a Fase 21 (ADR 0013); "asignación" delegable de la respuesta sin fecha — `evaluation_owner` es la única autoridad en esta fase.

**Archivos tocados:** ver el detalle completo por bloque en `current-phase.md` — resumen: nuevo módulo `service/procurawise/qna/` (`models`, `repository`, `service`, `schemas`, `router` — dos `APIRouter`, proveedor y comprador —, `exceptions`); `migrations/0014_qna_indexes.py`; `audit/models.py` (+`qna_question` resource_type +3 acciones); `api/main.py` (+2 routers); frontend: `features/vendor-portal/hooks/useQuestionActions.ts` (nuevo), `features/vendor-portal/components/ProposalQnaPanel.tsx`/`RequirementQuestionThread.tsx` (nuevos, montados en `VendorProposalDetailPage.tsx`), `features/evaluations/pages/QnaPage.tsx` (nueva, ruta `/evaluations/:evaluationId/qna`), `features/evaluations/hooks/useQnaPolling.ts` (nuevo, segundo consumidor real de `PollingController`/ADR 0012), `app/router.tsx`/`EvaluationTabNav.tsx` (+ruta y pestaña "Q&A"); `e2e/qna.spec.ts` (nuevo); 4 archivos de test backend nuevos, 3 de test frontend nuevos.

**Resultado de pruebas:**
- `make lint`/`make typecheck` → limpio (backend + frontend).
- Backend unit (`pytest -m "not docker and not docker_servicebus"`) → 168 passed.
- Backend integración/API/seguridad Docker (`make test-integration`) → 279 passed (incl. test dedicado de fuga de identidad sobre `PublicQuestionResponse`).
- Frontend (`pnpm test`) → 150 passed.
- `pnpm build` → build de producción exitoso.
- `make test-e2e` → 11/11 specs passed (1 nuevo — `qna.spec.ts` — journey con dos organizaciones proveedoras reales, visibilidad privada y publicada-anonimizada, sin fuga de identidad).
- `make contracts` corrido tres veces seguidas → checksum idéntico, sin diff.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):**
- Ninguna requiere un ADR nuevo — visibilidad binaria es una regla de negocio de proyección de schema (no un patrón arquitectónico nuevo); notificaciones in-app reutilizan polling ya aprobado por ADR 0012, sin canal de entrega nuevo.
- `PollingController` (ADR 0012) usado deliberadamente solo como disparador de refresco (`refetch()` de React Query), nunca como dueño de los datos — evita doble dueño del caché entre el controller y React Query; documentado en el código de `useQnaPolling.ts`, no requiere ADR (no cambia el contrato de ADR 0012, solo cómo se consume desde un segundo caller).

**Deuda técnica introducida:**
- Ninguna material — módulo `qna/` completamente nuevo y aditivo, sin FKs entrantes desde otras colecciones, sin infraestructura nueva que operar.

**Instrucciones para la siguiente sesión:**
- Próxima fase según `backlog.md`: **Fase 18 (E7) — Evaluación asistida por IA (riesgos/score sugerido) con "aceptar o modificar" obligatorio**, depende de Fases 13 y 17 (ambas ya cerradas). [Corrección factual añadida en la sesión de Fase 18: ya cerrada también — ver entrada de sesión arriba.]
- No tocar todavía: entrega real de notificaciones por correo/push, preferencias de usuario, bounded context `notifications/` dedicado (todo Fase 24); "aclaraciones" del comprador sobre una `ProposalAnswer` ya enviada (Fase 21/ADR 0013); adjuntos nuevos en preguntas/respuestas de Q&A (si se necesitaran, referencia `document_id` al módulo `documents/` ya existente).
- Housekeeping pendiente heredado, sin cambios: rama `phase-14/research-provider-curated-foundry` sigue sin borrarse (requiere confirmación explícita del founder); ramas `phase-15`/`phase-16`/`phase-17` tampoco se han borrado.

### Sesión — 2026-08-03 — Fase 16 (E6): `documents` — subida vía Azurite, escaneo AV stub, versionado, URLs temporales

**Resumen:** Sesión de planeación en Plan Mode (verificación no destructiva de git sobre el cierre de Fase 15, inventario de reutilización sobre `shared/storage.py`/`proposals`/`vendor_portal`/`audit`) que identificó una pregunta bloqueante (grano de `Document`), resuelta explícitamente por el founder vía `AskUserQuestion`. Tras la aprobación del plan y una instrucción explícita del founder de proceder con la implementación, ejecución completa en 8 bloques incrementales (modelo+storage+config+migración, antivirus stub+servicio de dominio, endpoints de proveedor+auditoría, endpoints de comprador+integración con snapshot, contratos, frontend proveedor, frontend comprador, E2E+documentación), cada uno verificado contra servicios reales (Mongo, Azurite) antes de avanzar.

**Decisión bloqueante resuelta por el founder (2026-08-02):**
1. Grano de `Document`: `requirement_id` opcional — soporta evidencia puntual por requerimiento y adjuntos generales de propuesta simultáneamente, sin agregar `evidence_required` a `Requirement` en esta fase.

**Archivos tocados:** ver el detalle completo por bloque en `current-phase.md` — resumen: nuevo módulo `service/procurawise/documents/` (`models`, `repository`, `service`, `antivirus`, `schemas`, `router` — dos `APIRouter`, proveedor y comprador); `shared/storage.py` (+`generate_download_url` vía Service SAS, `from_settings` gana `container_name` opcional); `shared/config.py` (+3 settings de `documents_*`); `proposals/models.py` (+`ProposalSnapshot.document_ids`), `proposals/service.py` (`submit` los captura), `proposals/schemas.py`/`router.py` (+`document_ids`), `proposals/router.py`/`vendor_portal/router.py` (+dependencia `DocumentRepository` en `ProposalService`); `audit/models.py` (+`document` resource_type +5 acciones); `api/main.py` (+2 routers); `migrations/0013_documents_indexes.py`; `pyproject.toml` (+`python-multipart`); frontend: `features/vendor-portal/hooks/useDocumentActions.ts` (nuevo), `features/vendor-portal/components/ProposalDocumentsPanel.tsx`/`RequirementEvidenceUpload.tsx` (nuevos, montados en `VendorProposalDetailPage.tsx`), `features/scoring/components/BuyerDocumentsList.tsx` (nuevo, montado en `ScoringPage.tsx`), `lib/formatFileSize.ts` (nuevo), `testUtils/mockFetchRouter.ts` (fix: ya no asume que todo body es JSON); `e2e/documents.spec.ts` (nuevo); ~9 archivos de test backend nuevos, 4 de test frontend nuevos.

**Resultado de pruebas:**
- `make lint`/`make typecheck` → limpio (backend + frontend).
- Backend unit (`pytest -m "not docker and not docker_servicebus"`) → 163 passed.
- Backend integración/API/seguridad Docker (`make test-integration`) → 253 passed (incl. SAS real contra Azurite con expiración y permiso de solo-lectura verificados).
- Frontend (`pnpm test`) → 133 passed.
- `pnpm build` → build de producción exitoso.
- `make test-e2e` → 10/10 specs passed (1 nuevo — `documents.spec.ts` — journey completo de subida/reemplazo/rechazo/descarga real/envío/revisión de comprador).
- `make contracts` corrido dos veces seguidas → sin diff.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):**
- Ninguna requiere un ADR nuevo — el flujo de subida síncrona vía API-proxy (sin worker nuevo) es continuación directa de patrones ya aprobados (ADR 0020), no una decisión de arquitectura nueva.
- Provisión perezosa cacheada del contenedor de Blob de documentos (`documents/router.py::get_document_service`, primera llamada por proceso) en vez de atarla a `run_migrations()` — `run_migrations()` es solo-índices-Mongo y nunca se invoca automáticamente, así que atar la provisión de Blob ahí no habría resuelto el gap para `make dev`/tests; documentado en el código, no requiere ADR (no cambia arquitectura, solo dónde vive un `ensure_container()` idempotente).

**Deuda técnica introducida:**
- Blobs huérfanos por fallo parcial (Blob subido, inserción en Mongo falla) — housekeeping futuro no bloqueante, documentado en `current-phase.md`/`threat-model.md`.
- Azurite 3.33.0 no hace cumplir el alcance de permiso `sp=r` de una SAS en escrituras (gap de fidelidad Azurite/Azure real, no un bug de la implementación) — documentado en el docstring del test de integración correspondiente y en `threat-model.md`.

**Instrucciones para la siguiente sesión:**
- Próxima fase según `backlog.md`: **Fase 17 (E7) — `qna`: preguntas ligadas/generales, publicación anonimizada/privada, notificaciones**, depende de Fase 16 (ya cerrada). [Corrección factual añadida en la sesión de Fase 17: la épica es E7, no un placeholder — ver `roadmap.md`.]
- No tocar todavía: subida de documentos por el comprador (backend genérico ya lo soporta, UI diferida — R7 del plan); OCR/clasificación/resumen/firma electrónica de documentos (fuera de alcance del MVP); cuarentena física como pipeline asíncrono real (el stub síncrono basta para el criterio de aceptación).
- Housekeeping pendiente heredado, sin cambios: rama `phase-14/research-provider-curated-foundry` sigue sin borrarse (requiere confirmación explícita del founder).

### Sesión — 2026-08-02 — Fase 15 (E6): NDA/conflicto de interés reales (`Agreement`) + auth productiva de proveedor + colaboradores múltiples

**Resumen:** Sesión de planeación en Plan Mode (verificación no destructiva de git sobre el cierre de Fase 14 — encontró que el reporte citaba el hash pre-squash `afe06c1` en vez del real `f36f471`, y que la rama de Fase 14 no había sido borrada — más 3 agentes Explore en paralelo sobre identity/vendor_portal, proposals/vendor linking, y frontend/e2e) que identificó 4 preguntas bloqueantes, resueltas explícitamente por el founder vía `AskUserQuestion`. Tras la aprobación del plan y una instrucción explícita del founder de proceder con la implementación, ejecución completa en 10 bloques incrementales (módulo `agreements/`, JWT+invitación de proveedor, endpoints de alta/invitación, gates de `vendor_portal`, auditoría+`dev_seed.py`, tests backend, contratos, frontend, e2e, documentación), cada uno verificado contra servicios reales antes de avanzar.

**Decisiones bloqueantes resueltas por el founder (2026-08-02):**
1. Colaboradores: mismo rol `vendor_contact` para todos (permisos idénticos), invitación siempre a cargo del comprador — nunca autoinvitación por el proveedor.
2. Alcance de la invitación: por organización (no por evaluación) — el JWT de proveedor no lleva lista de `evaluation_id`s, el alcance se resuelve en cada request vía `vendor_org_id`+`tenant_id`.
3. Alta de `VendorOrganization`: combinada con la invitación inicial en un solo endpoint, utilizable standalone o antes de vincular a una evaluación.
4. Contenido legal: texto único a nivel plataforma, versionado como constantes de código, sin grandfathering al subir de versión.

**Corrección de diseño durante la implementación (resuelta a favor de la seguridad, no un bug):** el plan original recomendaba loguear el token de invitación en texto plano — contradecía el requisito explícito "secretos/tokens ausentes de logs y auditoría". Resuelto devolviendo el token una sola vez en la respuesta HTTP autenticada de creación, nunca logueado (solo su hash SHA-256 se persiste).

**Archivos tocados:** ver el detalle completo por bloque en `current-phase.md` — resumen: nuevo módulo `service/procurawise/agreements/` (`models`, `repository`, `service`, `schemas`, `legal_content`); `identity/models.py` (+`VendorInvitation`), `identity/repository.py` (+`VendorInvitationRepository`, `UserRepository.update_password`), `identity/jwt_provider.py` (+`vendor_access` token_use, `create_vendor_access_token`/`get_current_vendor_context`), `identity/vendor_auth_service.py` + `identity/vendor_auth_router.py` (nuevos), `identity/vendor_auth_schemas.py` (nuevo); `vendor_portal/dependencies.py` (nuevo), `vendor_portal/router.py` (migrado a JWT real), `vendor_portal/agreements_router.py` (nuevo); `shared/config.py` (+`vendor_invitation_ttl_days`/`trusted_proxy_hops`), `shared/request_ip.py` (nuevo); `audit/models.py` (+`vendor_organization` resource_type +5 acciones); `dev_seed.py` (password real de `vendor_user_a`, nuevo `vendor_user_a2`, Agreements pre-aceptados solo para el contacto principal); `api/main.py` (+4 routers); `migrations/0011_agreements_indexes.py`, `migrations/0012_vendor_invitations_indexes.py`; frontend: `vendor-auth/` (nuevo — `VendorAuthContext`/`VendorLoginPage`/`AcceptInvitationPage`), `features/agreements/` (nuevo — `RequireAgreementsAccepted`/`AgreementAcceptanceScreen`), `features/evaluations/components/` (+`CreateVendorOrganizationForm`/`InviteLinkNotice`/`VendorCollaboratorsPanel`), `app/router.tsx`/`guards.tsx` (`VendorLayout` migrado a auth real), `lib/http.ts` (+`activeVendorAccessToken`), `VendorsPage.tsx` (alta de proveedor + colaboradores); `e2e/vertical-slice.spec.ts`/`isolation.spec.ts` reescritos, `e2e/vendor-onboarding.spec.ts` (nuevo); ~15 archivos de test backend nuevos/extendidos, `App.integration.test.tsx` actualizado.

**Resultado de pruebas:**
- `make lint`/`make typecheck` → limpio (backend + frontend).
- Backend unit (`pytest -m "not docker and not docker_servicebus"`) → 156 passed.
- Backend integración/API/seguridad Docker (`make test-integration`) → 228 passed (incl. replay concurrente con `ThreadPoolExecutor` en `test_vendor_auth.py`).
- Frontend (`pnpm test`) → 116 passed.
- `pnpm build` → build de producción exitoso.
- `make test-e2e` → 9/9 specs passed (1 nuevo — `vendor-onboarding.spec.ts` — + 2 reescritos sin regresión).
- `make contracts` corrido dos veces seguidas → sin diff.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):**
- Ninguna requiere un ADR nuevo — la aclaración de D2 (alcance de invitación por organización, no lista de `evaluation_id`s en el JWT) se documentó como nota fechada en `architecture.md` §5, no como reapertura de arquitectura (no cambia monolito/BD/hosting/patrón de comunicación, CLAUDE.md §3).
- Corrección de diseño sobre R2 del plan (token en logs) — ver arriba, resuelta a favor del requisito de seguridad explícito, no como decisión arquitectónica nueva.

**Deuda técnica introducida:**
- `VendorAuthService.login` resuelve determinísticamente a la membership más antigua si un email tiene más de un `vendor_contact` (edge case sin requisito de producto detrás) — documentado, no bloqueante.
- `VendorOrganization.country`/`region` (GDPR) siguen sin existir en el modelo — la referencia obsoleta en `threat-model.md` que afirmaba lo contrario se corrigió, el campo en sí no se agregó (no era parte del criterio de aceptación textual).
- Rama `phase-14/research-provider-curated-foundry` (obsoleta desde el squash-merge de Fase 14) sigue sin borrarse — requiere confirmación explícita del founder, acción destructiva fuera del alcance de esta sesión.

**Instrucciones para la siguiente sesión:**
- Próxima fase según `backlog.md`: **Fase 16 (E6) — `documents`: subida vía Azurite, escaneo AV stub, versionado, URLs temporales**, depende de Fase 15 (ya cerrada).
- No tocar todavía: envío real de invitaciones por correo (Fase 24); contenido legal administrable/personalizable por tenant (fuera de alcance); extracción de `vendors/` como bounded context separado (recomendación no bloqueante, no comprometida).
- Housekeeping pendiente heredado, opcional: borrar la rama `phase-14/research-provider-curated-foundry` si el founder confirma; agregar `VendorOrganization.country`/`region` si Fase 16 (documentos) o una fase posterior necesita el flag GDPR real.

### Sesión — 2026-08-01 — Fase 14 (E5): `ResearchProvider` completo + `CuratedSourceProvider` + `FoundryWebSearchProvider` (desactivado)

**Resumen:** Sesión de planeación en Plan Mode (2 rondas de agentes Explore sobre docs/ADRs/roadmap/código de `ai/`, más un research spike vía WebFetch/WebSearch sobre la API real de Microsoft Foundry Web Search) que identificó 3 preguntas bloqueantes, resueltas explícitamente por el founder junto con 5 requisitos adicionales (catálogo de fuentes inmutable, validación de `source_id`, foco de seguridad admin/comprador, warnings estructurados, fix de `shared/health.py`). Tras la aprobación del plan y una instrucción explícita del founder de proceder con la implementación, ejecución completa en 9 bloques incrementales, cada uno verificado contra servicios reales (Mongo, Azurite) y, para `FoundryWebSearchProvider`, fakes HTTP determinísticos — sin credenciales reales de Foundry en ningún punto.

**Decisiones bloqueantes resueltas por el founder (2026-08-01):**
1. `CuratedSourceProvider`: colección Mongo a nivel plataforma (no tenant-scoped), CRUD `platform_admin`-only, solo soft-delete, sin admin UI esta fase, sin crawling de URLs.
2. `FoundryWebSearchProvider`: REST directo (`httpx`+`azure-identity` para el token), no el SDK `azure-ai-projects`/`azure-ai-agents` — confirmado viable por el research spike.
3. Gate de activación: solo flag a nivel de ambiente esta fase (+ referencia de aprobación legal, fail-closed en todo ambiente); activación por tenant diferida a cuando la aprobación legal esté cerca.

**Archivos tocados:** ver el detalle completo por bloque en `current-phase.md` — resumen: nuevo módulo `service/procurawise/curated_sources/` (`models`, `repository`, `service`, `schemas`); nuevos `ai/curated_source_provider.py`, `ai/foundry_web_search_provider.py`, `ai/composite_research_provider.py`, `ai/text_relevance.py`, `ai/prompts/requirement_generation/v2/`; modificados `ai/research_provider.py` (`DiscoveryResult`/`ResearchWarning`/`ResearchSnippet.url`+`.retrieved_at`), `ai/internal_knowledge_provider.py`, `ai/models.py` (`AIExecution.source_catalog`/`.warnings`), `ai/schemas.py`, `ai/service.py`, `ai/router.py`, `admin/router.py` (+5 endpoints `/curated-sources`), `shared/config.py` (+campos `foundry_*` +validador fail-closed), `shared/health.py` (fix de boundary leak), `pyproject.toml` (+`azure-identity`); `migrations/0010_curated_sources_indexes.py`; frontend: `AiSuggestRequirementsDialog.tsx` (panel de citaciones + banner de degradación), `client.ts` regenerado; ~10 archivos de test backend nuevos + 6 extendidos, 1 archivo de test frontend extendido; `docs/security/threat-model.md`, `docs/operations/deployment.md`, `docs/development/backlog.md`, `docs/development/current-phase.md` actualizados; `CLAUDE.md`, `docs/architecture/architecture.md`, ADR 0011, ADR 0021 actualizados (ver bloque de documentación de frontera de IA).

**Resultado de pruebas:**
- `make lint`/`make typecheck` → limpio (backend + frontend).
- Backend unit (`pytest -m "not docker and not docker_servicebus"`) → 147 passed.
- Backend integración/API/seguridad Docker (`make test-integration`) → 208 passed, incluyendo el foco de seguridad priorizado por el founder (JWT comprador/`tenant_admin` rechazado en rutas admin de `curated-sources`).
- Frontend (`pnpm test`) → 116 passed.
- `make test-e2e` → 8 specs passed, sin regresión (ninguno nuevo esta fase — ver nota de alcance en `current-phase.md`).
- `make contracts` corrido dos veces seguidas → sin diff.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):**
- Ninguna requiere un ADR nuevo — todo lo implementado ejecuta el alcance ya aprobado por ADR 0011 (`ResearchProvider`/gate legal) y ADR 0021 (`AIProvider`/`AIExecution`), formalizado como una clarificación fechada en ADR 0011 y un addendum en ADR 0021 (ver bloque de documentación de frontera de IA), no como decisiones arquitectónicas nuevas.
- Se optó por **no** usar `AuditEventService` para las acciones de administración de `curated_sources` (logging estructurado en su lugar) — `AuditEventRepository` siempre escribe vía `TenantCollection`, y contenido de plataforma sin `tenant_id` no encaja en ese modelo. Documentado en `curated_sources/service.py`.

**Deuda técnica introducida:**
- El E2E existente (`ai-requirement-suggestions.spec.ts`, Fase 13) no se extendió para ejercer citaciones/warnings — ese spec no llega al estado `succeeded` sin un worker/proveedor determinístico cableado en `scripts/test-e2e.sh` (deuda ya documentada en la sesión de Fase 13, no nueva de esta sesión). La cobertura equivalente existe en `AiSuggestRequirementsDialog.test.tsx`.
- Sin wrapper tipado de excepción de proveedor (`AIProviderError`/`AIProviderTimeoutError`) — gap de documentación identificado en el audit de frontera de IA (item 5), no bloqueante para esta fase, no introducido por ella.
- `CuratedSourceProvider` no filtra por `Dimension` (a diferencia de `InternalKnowledgeProvider`) — solo ranking por relevancia de palabras clave sobre título/resumen/tags. Aceptable con biblioteca curada pequeña; si el volumen crece, podría valer la pena un filtro por dimensión/tag más estricto — no comprometido para ninguna fase futura concreta.

**Instrucciones para la siguiente sesión:**
- Próxima fase según `backlog.md`: **Fase 15** (auth real de `vendor_contact`/`Colaborador proveedor`, spec §6.5 FR-043), depende de Fase 9 (ya cerrada) — confirmar contra `roadmap.md`/`backlog.md` antes de planear, no asumir desde este texto.
- No tocar todavía: activación del flag de `FoundryWebSearchProvider` en ningún ambiente sin aprobación legal documentada (ADR 0011); consentimiento/activación por tenant de Foundry (diferido a cerca de la Fase 28); cuota/límite duro de costo de IA (Fase 26).
- Housekeeping pendiente heredado, opcional: wrapper tipado de excepción de proveedor (`AIProviderError`) si se retoma la frontera de IA en una fase futura; filtro por dimensión en `CuratedSourceProvider` si el volumen de contenido curado lo justifica.

### Sesión — 2026-08-01 — Fase 13 (E5): Adaptador `AIProvider` real (Azure OpenAI/Foundry)

**Resumen:** Sesión de planeación en Plan Mode (3 agentes Explore en paralelo sobre docs/ADRs/roadmap, backend, y frontend/tests/CI para confirmar que Fase 13 era la fase siguiente y determinar qué infraestructura de IA ya existía — ninguna) seguida de 3 preguntas bloqueantes resueltas explícitamente por el founder antes de implementar. Tras la aprobación del plan y una instrucción explícita del founder de proceder con la implementación (sesión que empezó en modo solo-planeación), ejecución completa en 8 bloques incrementales, cada uno verificado contra servicios reales (Mongo, Azurite, y — por primera vez en el repo — el emulador real de Azure Service Bus) antes de avanzar.

**Decisiones bloqueantes resueltas por el founder (2026-08-01):**
1. Modelo de ejecución asíncrona: adaptador real de `ServiceBusMessageBus` + emulador de Azure Service Bus ahora, no un interino en el mismo proceso.
2. Persistencia de salida de IA: candidatos efímeros en `AIExecution.candidates`, ningún `Requirement` real se crea sin aceptación humana explícita.
3. Límite de costo de IA: solo observabilidad esta fase (`token_usage`/`cost_estimate` registrados, sin cuota dura); enforcement diferido a Fase 26.

**Archivos tocados:** ver el detalle completo por bloque en `current-phase.md` — resumen: nuevo paquete `service/procurawise/ai/` (`models`, `provider`, `azure_openai_provider`, `research_provider`, `internal_knowledge_provider`, `repository`, `service`, `router`, `worker`, `schemas`, `exceptions`, `prompts/`); `shared/config.py` (+campos `azure_openai_*`/`ai_*`), `shared/messaging.py` (+`ServiceBusMessageBus`/`get_message_bus`), `shared/health.py`/`api/routers/health.py` (+check `ai_provider`), `audit/models.py` (+resource_type `ai_execution` +4 acciones), `worker/main.py` (reescrito — primer dispatch table real), `api/main.py` (+router); `migrations/0009_ai_executions_indexes.py`; `docker-compose.yml` (+perfil `servicebus`), `docker/servicebus-emulator/config.json` (nuevo), `Makefile` (+`dev-up-servicebus`/`test-integration-ai`), `pyproject.toml` (+`openai`/`azure-servicebus`); frontend: `lib/pollingController.ts` (nuevo), `lib/http.ts` (`ApiError`+`headers`), `features/evaluations/hooks/useAiSuggestionJobStatus.ts` (nuevo), `features/evaluations/components/AiSuggestRequirementsDialog.tsx` (nuevo, montado en `WizardStepRequirements.tsx`/`RequirementsPage.tsx`); `e2e/ai-requirement-suggestions.spec.ts` (nuevo); `docs/architecture/decisions/0021-ai-provider-abstraction.md` (nuevo ADR); `docs/architecture/architecture.md`, `docs/security/threat-model.md`, `docs/operations/deployment.md`, `docs/development/backlog.md` actualizados; ~15 archivos de test backend nuevos/extendidos, 2 archivos de test frontend nuevos.

**Resultado de pruebas:**
- `make lint`/`make typecheck` → limpio (backend + frontend).
- Backend unit (`pytest -m "not docker and not docker_servicebus"`) → 124 passed.
- Backend integración Docker (`make test-integration`) → 194 passed.
- Backend integración contra el emulador real de Azure Service Bus (`make test-integration-ai`, target nuevo) → 5 passed, incluyendo un end-to-end genuino (publish real → `run_worker_loop` real → `AIExecution` succeeded).
- Frontend (`pnpm test`) → 115 passed.
- `make test-e2e` → 8 specs passed (1 nuevo, alcance limitado documentado en `current-phase.md` — no cubre el camino `succeeded`/aceptar contra un worker real, eso lo cubren el test de componente y la integración Python).
- `make contracts` corrido dos veces seguidas → sin diff.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):**
- Ninguna nueva más allá de lo ya cubierto por el ADR 0021 escrito en el Bloque 0 — toda la fase ejecuta arquitectura ya aprobada por ADR 0001/0005/0011/0012/0016/0020, formalizada en un ADR nuevo por tratarse de la primera integración con un proveedor de IA externo (regla CLAUDE.md §3), no por reabrir ninguna decisión previa.

**Deuda técnica introducida:**
- E2E no cubre el camino completo `succeeded`→revisar→aceptar contra un worker real — requeriría un proveedor de IA determinístico gateado a `environment in (local, test)` (mismo patrón que `DevelopmentIdentityProvider`) más iniciar el worker + perfil `servicebus` dentro de `scripts/test-e2e.sh`. Se decidió explícitamente no construirlo a ciegas en esta sesión dado que ese script ya causó un segfault de CI por complejidad de orquestación de procesos — la cobertura equivalente ya existe (test de componente con fetch mockeado + integración Python contra Mongo+Service Bus reales), así que el riesgo de construir infraestructura nueva sin verificación dedicada superaba el valor incremental.
- Tabla de precios de Azure OpenAI (`ai_prompt_price_per_1k_tokens_usd`/`ai_completion_price_per_1k_tokens_usd`) no tiene ningún valor por defecto — `cost_estimate` queda `null` hasta que el founder configure el precio real negociado para su región/acuerdo. Deliberado (no adivinar un precio), pero significa que la observabilidad de costo no está activa "de fábrica".

**Instrucciones para la siguiente sesión:**
- Próxima fase según `backlog.md`: **Fase 14 (E5) — `ResearchProvider` completo + `CuratedSourceProvider` + `FoundryWebSearchProvider`** (P1, abstracción P0/activación de Foundry P1 condicionado a aprobación legal — ver ADR 0011), depende de Fase 13 (ya cerrada).
- No tocar todavía: activación del flag de `FoundryWebSearchProvider` sin aprobación legal documentada (ADR 0011); cuota/límite duro de costo de IA (Fase 26); mejora/reescritura de requerimientos existentes vía IA (no está en el backlog).
- Housekeeping pendiente heredado, opcional: la deuda técnica de E2E arriba (worker + proveedor determinístico) es candidata a resolverse como parte de Fase 14 si esa fase también necesita un job asíncrono real de bùsqueda web, o puede quedar diferida más allá.

### Sesión — 2026-07-31 — Fase 11 (E4): Biblioteca de requerimientos (`KnowledgeTemplate`, plantillas estáticas, sin IA)

**Resumen:** Sesión de planeación en Plan Mode (3 agentes Explore en paralelo sobre docs/roadmap/backlog/handoff — para confirmar que Fase 11 era la fase siguiente, no asumida —, backend, y frontend/tests/CI; luego un agente Plan de diseño técnico detallado) seguida de 3 preguntas bloqueantes resueltas explícitamente por el founder antes de implementar (las 3 resueltas con la opción recomendada). Tras la aprobación del plan, implementación completa en 5 bloques incrementales, cada uno verificado contra Docker real antes de avanzar.

**Decisiones bloqueantes resueltas por el founder (2026-07-31):**
1. Autorización: `OWNER_ONLY` para crear/editar/eliminar plantillas e items y para aplicar; `BUYER_READ_ROLES` para listar/ver.
2. Semántica de "aplicar": solo plantilla completa — `item_ids` eliminado por completo de la API, no diferido como parámetro opcional.
3. Eliminación de plantilla: hard delete, sin archivo/soft-delete.

**Archivos tocados:** ver el listado completo por bloque en `current-phase.md` — resumen: `evaluations/models.py` (+`validate_requirement_patch`, +`Evaluation.approval_invalidation_extra_set()`), `evaluations/service.py` (usa los helpers extraídos), `evaluations/repository.py` (+`add_requirements_bulk`), `knowledge_templates/{models,repository,service,router,schemas,exceptions}.py` (nuevo), `migrations/0008_knowledge_template_indexes.py` (nuevo), `audit/models.py` (+7 acciones), `api/main.py` (backend); `KnowledgeTemplatesPage.tsx`, `KnowledgeTemplateDetailPage.tsx`, `ApplyTemplateButton.tsx` (nuevos), `WizardStepRequirements.tsx`/`RequirementsPage.tsx` (+`ApplyTemplateButton`), `router.tsx`/`AppShell.tsx` (frontend); `e2e/knowledge-templates.spec.ts` (nuevo); 9 archivos de test backend nuevos, 2 archivos de test frontend nuevos.

**Resultado de pruebas:**
- `make lint`/`make typecheck` → limpio (backend + frontend).
- `make test` → 106 passed backend + 103 passed frontend.
- `make test-integration` (Docker real) → 173 passed (+16 sobre la base de Fase 12).
- `make test-e2e` (Docker + Playwright real) → 7 specs passed.
- `make contracts` corrido dos veces seguidas → sin diff.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):** ninguna — no reabre monolito/DB/hosting/patrón de comunicación (CLAUDE.md §3); toda la fase es CRUD estándar sobre la arquitectura ya aprobada, reutilizando el precedente de composición cruzada de módulos que `AssignmentService` (Fase 9) ya estableció.

**Deuda técnica introducida:** ninguna nueva. Bug real encontrado y corregido durante la verificación E2E (no deuda, ya resuelto): `ApplyTemplateButton` mostraba `item_count` obsoleto porque `KnowledgeTemplateDetailPage` solo invalidaba la query de detalle, no la de listado — corregido invalidando ambas en cada mutación.

**Instrucciones para la siguiente sesión:**
- Próxima fase según `backlog.md`: **Fase 13 (E5) — Adaptador `AIProvider` real (Azure OpenAI/Foundry)**, P0, depende de Fase 12 (ya cerrada). Con Fase 11 cerrada, el Bloque 2 completo (Fases 8-12) queda formalmente cerrado; el Bloque 3 (IA y proveedores reales, Fases 13-16) queda desbloqueado.
- No tocar todavía: `Colaborador proveedor`/auth real de proveedor (Fase 15), consola `platform_admin`/`Administrador del cliente` (Fase 25), dimensión económica real (Fase 19-20), versionado/reapertura de evaluaciones publicadas (Fase 21), `FoundryWebSearchProvider` (Fase 14, requiere aprobación legal documentada antes de activarse — ADR 0011).
- Housekeeping pendiente heredado de sesiones anteriores, opcional: `current-phase.md`'s scaffold final ("Próximos pasos"/"Bloqueos", debajo de todas las secciones de fase) sigue reflejando la era AUTH-PROD; `README.md` sigue sin reflejar que Fase 12 (PR #24) ya está fusionada a `main`. Ninguno bloquea el inicio de Fase 13.

### Sesión — 2026-07-31 — Fase 12 (E4): Aprobación interna + publicación + snapshot inmutable

**Resumen:** Sesión de planeación en Plan Mode (3 agentes Explore en paralelo sobre docs/ADRs/git, backend, y frontend; luego un agente Plan de diseño técnico detallado) seguida de 4 preguntas bloqueantes de arquitectura resueltas explícitamente por el founder vía `AskUserQuestion` antes de implementar (las 4 resueltas con la opción recomendada), más 3 bloqueantes residuales de menor riesgo resueltos en la misma sesión de planeación. Tras la aprobación del plan, implementación completa en 7 bloques incrementales, cada uno verificado contra Docker real antes de avanzar.

**Decisiones bloqueantes resueltas por el founder (2026-07-31):**
1. Forma del ciclo de vida: gatear la transición `draft → collecting_responses` existente con un campo nuevo `approval_status`, sin agregar valores nuevos a `EvaluationStatus`.
2. Aprobar y publicar son dos acciones separadas (no una combinada).
3. Aprobador preasignado (`approver_membership_id`), elegido por el owner, con auto-aprobación bloqueada server-side.
4. "Pesos" del backlog = el chequeo de completitud de pesos ya existente (40/20), no un sistema de pesos nuevo.

**Archivos tocados:** ver el listado completo por bloque en `current-phase.md` — resumen: `evaluations/{models,repository,service,router,schemas,exceptions}.py` + `snapshot_repository.py` (nuevo) + `migrations/0007_*.py` (backend); `WizardStepReview.tsx`, `EvaluationApprovalPage.tsx` (nueva), `useApprovalInvalidationNotice.ts` (nuevo), `evaluationReadiness.ts`, `ErrorBanner.tsx`, `EvaluationTabNav.tsx`, `RequirementsPage.tsx`/`VendorsPage.tsx`/`EvaluationDetailPage.tsx` (frontend); `dev_seed.py`; 3 specs E2E nuevos/actualizados; 8 archivos de test backend actualizados para pasar por el flujo de aprobación antes de publicar.

**Resultado de pruebas:**
- `make lint`/`make typecheck` → limpio (backend + frontend).
- `make test` → 96 passed backend + 96 passed frontend.
- `make test-integration` (Docker real) → 146 passed (+6 sobre la base de Fase 10/9).
- `make test-e2e` (Docker + Playwright real) → 6 specs passed.
- `make contracts` corrido dos veces seguidas → sin diff.

**Decisiones ad-hoc tomadas en esta sesión (candidatas a ADR):**
- Snapshot en colección separada (`evaluation_snapshots`, repositorio insert-only) en vez de embebido en `Evaluation` — justificado por `requirements` sin límite (a diferencia de `MAX_LINKED_VENDORS`) y por inmutabilidad estructural (sin método de update/delete) en vez de solo un filtro condicional. No requiere ADR nuevo bajo CLAUDE.md §3 (no cambia monolito/BD/hosting/patrón de comunicación), pero sería un candidato razonable a un ADR corto siguiendo el precedente de ADR 0008/0009/0013 — no creado en esta sesión, queda como recomendación no bloqueante.
- Invalidación suave (no bloqueo duro) de la aprobación al editar mientras `pending`/`approved`, con aviso explícito en el frontend en vez de solo un badge — confirmado por el founder junto con los bloqueantes residuales.

**Deuda técnica introducida:**
- El aviso de invalidación de aprobación no está cableado en los pasos 1-3 del wizard (`WizardStepMetadata`/`WizardStepRequirements`/`WizardStepVendors`), solo en las páginas dedicadas (`RequirementsPage`/`VendorsPage`/`EvaluationDetailPage`) y en el paso 4 (`WizardStepReview`). El wizard sigue siendo alcanzable mientras `approval_status` es `pending`/`approved` (no cambia `EvaluationStatus`), así que editar ahí sin salir del wizard todavía no muestra el aviso explícito — el backend sí invalida correctamente en todos los casos, es solo una brecha de UX. Debe resolverse antes de considerar el flujo de aprobación "pulido" end-to-end, no es bloqueante para el criterio de aceptación del backlog.
- No existe un endpoint dedicado de historial de aprobación (múltiples ciclos de solicitud/rechazo) — `EvaluationApprovalPage` solo muestra la última decisión desde los campos de `Evaluation`. El audit trail (Fase 8) sí conserva el historial completo si se necesita reconstruirlo.

**Instrucciones para la siguiente sesión:**
- Próxima fase según `backlog.md`: Fase 11 (`KnowledgeTemplate`, biblioteca de requerimientos, P1, depende de Fase 9) es la única fase restante de este bloque — Fase 12 queda cerrada.
- Housekeeping pendiente de sesiones anteriores, opcional: `current-phase.md`'s scaffold final ("Próximos pasos"/"Bloqueos", debajo de todas las secciones de fase) sigue reflejando la era AUTH-PROD, no las fases más recientes — no se tocó en esta sesión por no ser parte del alcance de Fase 12.
- No tocar todavía: `Colaborador proveedor`/auth real de proveedor (Fase 15), consola `platform_admin`/`Administrador del cliente` (Fase 25), dimensión económica real (Fase 19-20), versionado/reapertura de evaluaciones publicadas (Fase 21).

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
