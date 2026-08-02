# ProcuraWise — Modelo de amenazas

Este documento se actualiza a medida que avanzan las fases (se cierra formalmente en la Fase 26 — Hardening, según [`docs/development/backlog.md`](../development/backlog.md)). Hasta entonces refleja el diseño aprobado, no controles ya implementados (el repositorio es greenfield al momento de escribir este documento).

## Activos

- Datos de tenants compradores: evaluaciones, requerimientos, propuestas, scores, decisiones, documentos.
- Datos de proveedores: respuestas, precios, documentos, aceptaciones de NDA/conflicto de interés.
- Credenciales y JWT (compradores, proveedores, `platform_admin`).
- Tasas FX (`FXRate`), configuración de rúbricas económicas.
- Prompts, resultados y trazabilidad de ejecuciones de IA (`AIExecution`), incluyendo el `source_catalog` inmutable de citaciones por job (Fase 14).
- Biblioteca curada de fuentes de investigación (`CuratedSource`, Fase 14) — contenido de plataforma, no tenant-scoped, gestionado solo por `platform_admin`.
- Secretos de infraestructura (Azure Key Vault, credenciales de servicios externos).

## Actores y superficie de confianza por rol

| Rol | Alcance de confianza |
|---|---|
| Usuario comprador (tenant) | Solo datos de su propio tenant, vía `tenant_id` del JWT |
| Usuario proveedor | Solo `vendor_org_id` + evaluaciones a las que fue invitado, vía router disjunto `/vendor-portal` |
| `platform_admin` | Cross-tenant, solo vía `find_across_tenants()` auditado con motivo obligatorio |
| Sistema de IA (`AIProvider`/`ResearchProvider`) | Solo datos sanitizados/abstractos permitidos por política (ver [ADR 0011](../architecture/decisions/0011-research-provider-gate-legal-foundry.md)) |

## Superficies de ataque

1. **API pública** (`/api/v1/*`) — autenticación, autorización, IDOR.
2. **Portal de proveedores** (`/api/v1/vendor-portal/*`) — acceso vía token de invitación, aislamiento de otras evaluaciones/proveedores.
3. **Uploads de documentos** — malware, tipo de archivo, tamaño, URLs temporales.
4. **IA / web-grounding** — exposición de datos confidenciales a un proveedor externo (ver riesgo crítico §24 de la spec).
5. **Webhooks** (Stripe, notificaciones) — validación de firma, replay.
6. **Panel `platform_admin`** — abuso de `find_across_tenants()`.

## Riesgo crítico #1: fuga multi-tenant

Marcado como riesgo crítico en la especificación (§24). Mitigación estructural, no solo por convención:

- `tenant_id` exclusivamente del claim JWT (nunca body/query/header del cliente).
- Wrapper `TenantCollection` inyecta automáticamente el filtro de tenant en cada operación Mongo.
- Router disjunto `/vendor-portal/*` sin `tenant_id` de comprador en el JWT de proveedor.
- `tests/security/test_tenant_isolation.py` y `test_vendor_isolation.py` corren en **cada PR desde VS-2A**, no solo antes del piloto: recurso de tenant A consultado desde tenant B → 404 (no 403, para no confirmar existencia).

Detalle arquitectónico completo en [ADR 0002](../architecture/decisions/0002-multi-tenant-mongodb.md).

**Estado de implementación (VS-2A, 2026-07-27):** `TenantCollection` (`service/procurawise/shared/tenant_collection.py`) implementado con las reglas descritas arriba más un control adicional: rechaza explícitamente cualquier intento de alterar `tenant_id` vía `$set`/`$setOnInsert`/`$unset` o reemplazo de documento, no solo vía filtro de lectura. El mecanismo de identidad (`DevelopmentIdentityProvider`, ver riesgo "Dev identity fuera de development" abajo) resuelve `tenant_id` desde una `Membership` persistida seleccionada por su propio `_id` (`X-Dev-Membership-Id`), nunca desde un valor de tenant enviado por el cliente. Pendiente de verificación contra Mongo real (sin Docker en la sesión de implementación) — ver `docs/development/current-phase.md`.

## Riesgos específicos del vertical slice (VS-2A/VS-2B)

| Riesgo | Mitigación | Estado |
|---|---|---|
| IDOR (acceso a un recurso de otro tenant por ID) | `TenantCollection` inyecta/valida `tenant_id` en cada operación; 404 uniforme | VS-2A implementado |
| Tenant escape vía colección compartida | `TenantCollection` rechaza colisión de filtro y mutación de `tenant_id` (`$set`/`$unset`/reemplazo) | VS-2A implementado |
| Enumeración de proveedores | `VendorOrganization` tenant-scoped (no hay directorio cross-tenant que enumerar) | VS-2A implementado |
| Escalación de rol | Rol resuelto server-side desde `Membership` por `membership_id`; el cliente nunca envía `tenant_id` ni `role` | VS-2A implementado |
| `DevelopmentIdentityProvider` habilitado fuera de development/test | Gate por `environment in (local, test)` → 404 en cualquier otro valor; test de integración explícito con `environment=production` | VS-2A implementado |
| Mass assignment (campos gestionados por el servidor enviados por el cliente) | Todo schema de escritura hereda `APIModel` (`extra="forbid"`) → 422 | VS-2A (`APIModel` base); pruebas por endpoint de escritura llegan con VS-2B (primeros endpoints de escritura de negocio) |
| NoSQL injection | Validación Pydantic de toda entrada antes de construir filtros Mongo | VS-2A (schemas de identity); se extiende en VS-2B |
| Manipulación de estado (saltar transiciones de `Evaluation`/`Proposal`) | Transiciones solo vía endpoints dedicados que validan el estado origen server-side (las 8 reglas explícitas del diseño) | Diseñado, implementación en VS-2B |
| Manipulación de score fuera de rango o por actor no autorizado | Solo `evaluation_owner`/sub-roles evaluadores (`SCORE_WRITE_ROLES`, nunca `internal_collaborator`/`approver`), solo durante `Evaluation.evaluating`, rango 0-5 validado, `requirement_id` debe existir en el `snapshot` de la propuesta; desde Fase 9, si una sección tiene `Assignment` registrado, solo el evaluador asignado puede calificarla | VS-2B; roles/`Assignment` desde Fase 9 |
| Fuga de información hacia el proveedor (scores, comentarios, otros proveedores) | Router de proveedor (`/vendor-portal/*`) físicamente separado, con schemas de respuesta propios que nunca incluyen `Score`/comentarios/otros proveedores | Diseñado, implementación en VS-2B |
| Logging de respuestas de propuesta | Disciplina de no pasar `answer.value`/`comment` como campo `extra` de logging estructurado | Diseñado, implementación en VS-2B |

## STRIDE por módulo crítico (resumen, se detalla en Fase 26)

| Módulo | Amenaza principal | Control previsto |
|---|---|---|
| `identity`/auth | Spoofing, elevación de privilegios | JWT propio + `tenant_id` como claim, sin confiar en input del cliente |
| `vendors`/vendor-portal | Repudiation, tampering de aceptación NDA/COI | `Agreement` con `user_id`/`ip`/`timestamp`/`version`, append-only |
| `proposals` | Tampering post-envío | Snapshot inmutable al enviar propuesta |
| `ai`/`AIProvider` (Fase 13) | Prompt injection vía texto libre del usuario; tampering del output de IA | Texto libre solo en el prompt de usuario (nunca en el de sistema); salida restringida por JSON schema y validada por Pydantic antes de tocar el dominio; candidatos efímeros — ningún `Requirement` real se crea sin aceptación humana explícita (ADR 0021) |
| `ai`/`ResearchProvider` (Fase 14) | Information disclosure a terceros | Política de datos sanitizados; `InternalKnowledgeProvider` (sin red externa) y `CuratedSourceProvider` (contenido curado manualmente, sin fetch de URLs) activos; `FoundryWebSearchProvider` **implementado pero desactivado en todo ambiente** — gate fail-closed en código (`Settings._require_foundry_preconditions_when_enabled`), no solo el flag booleano (ADR 0011) |
| `ai`/citación de fuentes (Fase 14) | Tampering: el modelo cita un `source_id` inventado/inexistente para aparentar respaldo de una fuente que no existe | `AIRequirementCandidate.sources` (ids) se valida contra el `source_catalog` inmutable de ese job en `ai.service._sanitize_candidate_sources` — al generar y de nuevo al aceptar; ids desconocidos se descartan (candidato completo si cita solo ids inválidos); una URL mostrada al usuario siempre viene del `source_catalog` persistido, nunca del output del modelo directamente |
| `admin`/`curated-sources` (Fase 14) | Elevación de privilegios: un actor comprador (`evaluation_owner`/`tenant_admin`) escribe en la biblioteca curada global | Rutas `/api/v1/admin/curated-sources/*` en el router `platform_admin` físicamente separado (CLAUDE.md §4), autenticadas con `token_use="admin_access"` — un JWT comprador no decodifica contra esa verificación (rechazo estructural, no solo de rol), verificado en `tests/api/test_curated_sources_admin_router.py` |
| `ai`/activación accidental de Foundry (Fase 14) | Elevation of privilege / policy bypass: `FOUNDRY_WEB_SEARCH_ENABLED=true` se activa sin aprobación legal documentada | Fail-closed estructural: el flag solo no es suficiente — `Settings` exige además `foundry_legal_approval_reference`, `foundry_web_search_endpoint` y `foundry_web_search_agent_name` no vacíos, en **todo** ambiente (no solo producción); `tests/unit/test_config.py` cubre cada combinación de precondición faltante |
| `admin` | Elevación de privilegios cross-tenant | `find_across_tenants()` explícito, auditado, con motivo obligatorio — **implementado desde Fase 9** (antes era diseño aprobado sin código) |
| `assignments` | Un evaluador ve/califica secciones fuera de su responsabilidad | Rol esperado validado contra la dimensión al crear el `Assignment`; enforcement de sección en `scoring.upsert_score` (Fase 9) |
| `documents` | Malware, denial of service por tamaño | Escaneo AV stub (Fase 16), hardening real (Fase 26) |

## Controles existentes vs. pendientes

- **Existentes (diseñados, a implementar desde Fase 1):** aislamiento estructural de tenant, router disjunto de proveedores, snapshot inmutable, `Agreement` tipado.
- **Baseline de seguridad de pipeline (implementado desde Fase 1C, 2026-07-18):** secret scanning en cada PR/push a `main` vía `gitleaks` (`.github/workflows/security.yml`, job `secret-scan`, **bloqueante**), dependency vulnerability scanning vía `pip-audit` (Python) y `pnpm audit` (JS/pnpm) (jobs `python-deps`/`frontend-deps`, **informativo por ahora** — el repo es privado sin GitHub Advanced Security, y un árbol de dependencias recién creado tiene CVEs transitivos sin fix disponible que bloquearían PRs sin motivo real; política de bloqueo se revisita cuando haya bandwidth para triage regular), `Dependabot` para `pip`/`npm`/`github-actions`. **CodeQL no implementado** — no disponible gratis en un repo privado sin GHAS (requeriría hacer público el repo o adquirir GitHub Advanced Security); queda documentado aquí como mejora disponible, no como pendiente de una fase futura concreta.
- **Pendientes (Fase 26 — Hardening):** rate limiting, CSRF, headers de seguridad, promover dependency scanning de informativo a bloqueante (una vez exista bandwidth de triage regular), CodeQL si cambia la visibilidad del repo o se adquiere GHAS, SBOM, WCAG 2.1 AA, pruebas de performance, backup/restore verificado.
- **Pendientes de gate externo:** aprobación legal de web-grounding antes de activar `FoundryWebSearchProvider` (ver ADR 0011). El research spike de la Fase 14 confirmó un hallazgo material para esa revisión: "Grounding with Bing Search"/"Grounding with Bing Custom Search" son *First Party Consumption Services* de Microsoft **no cubiertos por el Data Protection Addendum**, y los datos enviados **salen del boundary de compliance/geografía de Azure** — esto no bloquea la implementación (que queda desactivada), pero es información directamente relevante para la revisión legal y debe documentarse explícitamente en esa revisión, no solo en este archivo.

## Auditoría (Fase 8, `audit`)

**Estado: implementado y verificado con Docker real (2026-07-30).** `AuditEvent` append-only instrumentado retroactivamente sobre VS-2A/VS-2B/VS-2C (evaluations/proposals/scoring) — 13 acciones de una taxonomía cerrada (`service/procurawise/audit/models.py::AuditAction`), nunca strings arbitrarios. Extiende el patrón ya establecido por `Agreement` (append-only, `user_id`/`ip`/`timestamp`/`version`, fila "proposals"/"vendors" de la tabla STRIDE arriba) a todo el vertical slice.

- **`tenant_id`/`actor_*`/`occurred_at`/`action` siempre server-derivados** desde `ActorContext` y el punto de instrumentación — nunca aceptados de un body de cliente (no existe endpoint de escritura pública para `AuditEvent`).
- **Append-only por disciplina de superficie, no por control de motor**: `AuditEventRepository` expone únicamente `record()` (insert) y lectura — nunca `update`/`delete`/`replace`. **Riesgo residual aceptado**: acceso administrativo directo a MongoDB Atlas (o `mongosh` local) puede modificar/borrar documentos sin pasar por la aplicación; esto no es mitigable a nivel de código en la arquitectura actual (sin roles de BD por tenant en Atlas M0). No se propone blockchain/event-store externo — desproporcionado para el MVP.
- **Consistencia mutación↔evento: best-effort, decisión explícita del founder (2026-07-30).** La mutación de negocio nunca se revierte por un fallo de `AuditEvent`; el fallo genera un log `ERROR` estructurado (`tenant_id`/`actor_id`/`action`/`resource_type`/`resource_id`/`correlation_id`), encapsulado en `AuditEventService.record()`. **Consecuencia aceptada**: pueden existir gaps poco frecuentes en el audit trail si el insert falla tras una mutación exitosa — no hay outbox ni transacciones en esta fase (ni el entorno local ni se asume Atlas M0 con transacciones multi-documento para este propósito).
- **Redacción de datos sensibles**: `metadata` es una allowlist explícita por acción (nombres de campos cambiados, IDs, valores numéricos de score) — nunca passwords/hashes, JWT, tokens OIDC, contenido completo de respuestas de propuesta, ni comentarios de scoring. Ver matriz completa en el plan de la fase.
- **Retención**: 1 año por defecto (consistente con [ADR 0016](../architecture/decisions/0016-retencion-datos-1-anio.md)), vía campo `expires_at` + TTL index (`ttl_audit_expires_at`), centralizado en `Settings.audit_event_retention_days`. Una retención distinta/más larga (práctica común para audit trails, potencialmente en tensión con ADR 0016) requeriría una decisión de producto/compliance explícita y, si cambia la política vigente, un ADR nuevo.
- **Consultable**: `GET /api/v1/evaluations/{evaluation_id}/audit-events`, tenant-scoped, paginado por cursor, autorizado solo para `evaluation_owner`/`evaluator` de su propio tenant — `vendor_contact` no tiene ruta equivalente (401 sin credenciales de comprador, mismo patrón ya establecido por AUTH-PROD).
- **Fuera de alcance de esta fase**: autosave de `ProposalAnswer` (alta frecuencia, decisión explícita de no auditar cada guardado — solo el `PROPOSAL_SUBMITTED` terminal); login/OIDC (identity/AUTH-PROD) — el criterio de aceptación del backlog nombra VS-2A/VS-2B/VS-2C, no AUTH-PROD, y `User`/`Membership` son entidades cross-tenant que no encajan en un `AuditEvent` tenant-scoped sin una decisión de diseño aparte.

## RBAC completo y `Assignment` (Fase 9)

**Estado: implementado y verificado con Docker real (2026-07-30).** El modelo de roles crece de 3 a 8 valores tenant-scoped (spec §4) más un esqueleto mínimo, físicamente separado, para `platform_admin` (cross-tenant, sin `tenant_id`).

- **`Role` (`identity/models.py`)**: `evaluation_owner`, `evaluator_functional`, `evaluator_technical`, `evaluator_economic`, `internal_collaborator`, `approver`, `tenant_admin`, `vendor_contact`. Constantes de autorización centralizadas en `shared/roles.py` (antes duplicadas por router) — reduce el riesgo de que un router nuevo olvide replicar el mismo conjunto de roles permitidos.
- **`platform_admin` no es una `Membership`**: no tiene claim de `tenant_id` (architecture.md §5), así que vive en su propia colección (`platform_admins`, `admin/models.py::PlatformAdminAccount`) con su propio JWT (`token_use="admin_access"`, distinto de `"access"`). Verificado explícitamente (tests `test_admin_token_cannot_access_buyer_routes`/`test_buyer_token_cannot_access_admin_routes`) que un token de un tipo nunca es aceptado por el dependency chain del otro — no es solo un chequeo de rol, es un rechazo estructural en la verificación del JWT.
- **`find_across_tenants()` implementado**: `EvaluationRepository.find_across_tenants()` bypassa `TenantCollection` deliberadamente (como ya hacían los métodos cross-tenant de `MembershipRepository`), expuesto únicamente vía `GET /api/v1/admin/evaluations` (router físicamente separado), con `reason` obligatorio (`min_length=3`) y una `AuditEvent` (`platform_admin_cross_tenant_read`) por cada evaluación efectivamente tocada — no batched por tenant, para que aparezca en el propio audit trail de esa evaluación al consultarlo vía `GET /evaluations/{id}/audit-events`.
- **`Assignment` (`assignments/`)**: vincula un Membership evaluador a una sección (`Requirement.category`) dentro de una `dimension`, validado contra `EVALUATOR_ROLE_BY_DIMENSION` (el rol del evaluador debe coincidir con la dimensión) y contra que la sección exista realmente en los requirements de la evaluación (`SectionNotFoundError` si no). Solo `evaluation_owner` crea/quita asignaciones; el progreso (`status`) lo actualiza el propio evaluador asignado o el owner.
- **Corrección real encontrada durante la implementación**: ampliar `BUYER_READ_ROLES` para incluir `internal_collaborator`/`approver` (lectura general) les daba, sin querer, permiso de escritura de scores también, porque `scoring/router.py` reutilizaba esa misma tupla para su endpoint de escritura. Corregido con `SCORE_WRITE_ROLES` separado — ver tabla de riesgos específicos arriba.
- **`tenant_admin`**: capacidad mínima (`GET /api/v1/org/members`, tenant-scoped, nunca cross-tenant) — la consola de administración completa (spec: "Usuarios, roles, configuración, branding y políticas") es Fase 25.
- **Diferido en su momento, entregado en Fase 15**: `Colaborador proveedor` (spec §6.5 FR-043) + auth real de `vendor_contact` — ver sección dedicada abajo. `evaluator_economic` existe como rol pero no tiene nada real que calificar hasta que `Dimension` gane un valor `"economic"` (Fase 19-20).

## NDA/conflicto de interés reales + auth productiva de proveedor (Fase 15)

**Estado: implementado y verificado con Docker real (2026-08-02).** Reemplaza `DevelopmentIdentityProvider` como mecanismo de identidad de `vendor_contact` — mismo patrón exacto que AUTH-PROD ya aplicó a comprador: el mecanismo dev no se borra (sigue sirviendo `/dev/actors`/`/me` y las herramientas locales), simplemente deja de ser aceptado por `vendor_portal/*`.

- **`Agreement` (`agreements/`, ADR 0014)**: registro append-only (`type: nda | conflict_of_interest`, `user_id`, `ip`, `timestamp`, `version`). Grano `user_id`, no `vendor_org_id` — cada colaborador acepta individualmente, nunca de forma representativa de toda la organización; un colaborador nuevo no hereda la aceptación de otro. `require_agreements_accepted` gatea todo endpoint de `vendor_portal/proposals` (nunca los de `vendor_portal/agreements` en sí, para no crear un candado circular) — 403 con `{"detail": "agreements_required", "missing": [...]}`, nunca 404 (el actor sí existe, solo le falta un paso).
- **Contenido legal**: texto único a nivel plataforma (no por tenant), versionado como constantes de código (`agreements/legal_content.py`, mismo patrón que los prompts de IA v1/v2) — sin grandfathering: subir `CURRENT_NDA_VERSION`/`CURRENT_CONFLICT_OF_INTEREST_VERSION` re-gatea a todo contacto inmediatamente, incluso con evaluaciones ya en curso.
- **JWT de proveedor**: `token_use="vendor_access"` (distinto de `"access"` y de `"admin_access"`) — estructuralmente rechazado por rutas de comprador y viceversa, verificado explícitamente (`test_vendor_contact_cannot_create_vendor_organization`, `test_owner_cannot_access_vendor_portal_routes`). Lleva `tenant_id` (a diferencia del JWT de `platform_admin`, que no tiene ninguno) porque `VendorOrganization` ya es tenant-owned — pero **no** lleva una lista de `evaluation_id`s: el alcance se resuelve en cada request vía `vendor_org_id`+`tenant_id` (decisión de planeación D2, alcance por organización, no por evaluación).
- **Invitación (`VendorInvitation`)**: token de un solo uso, generado con `secrets.token_urlsafe(32)`, persistido solo como hash SHA-256 (`token_hash`, índice único global — mismo precedente que `users.email`). Redención atómica y condicional (`try_accept`: `status=pending AND expires_at>now → accepted`) — una carrera concurrente sobre el mismo token deja ganar exactamente a una solicitud, verificado con un test que dispara 8 intentos simultáneos vía `ThreadPoolExecutor` (1 éxito, 7 rechazos). El token nunca se loguea ni se persiste en texto plano en ningún lado — se devuelve exactamente una vez en la respuesta HTTP autenticada de creación (visible solo para el `evaluation_owner` que hizo la llamada), corrigiendo una recomendación del plan original que proponía loguearlo (contradecía el requisito explícito de esta fase de mantener secretos fuera de logs/auditoría).
- **Alta de proveedor**: antes de esta fase no existía ningún endpoint para que un comprador diera de alta un `VendorOrganization` nuevo (solo `dev_seed.py`, directo a Mongo) — `POST /api/v1/vendor-organizations` (comprador, `require_owner`) lo resuelve, combinado con la invitación del contacto principal en la misma llamada.
- **Colaboradores múltiples**: mismo rol `vendor_contact`, mismos permisos que el contacto principal (decisión de planeación D1) — invitados únicamente por el comprador (`POST /vendor-organizations/{id}/collaborators`), nunca autoinvitación por el proveedor (verificado: un JWT de proveedor presentado a ese endpoint es rechazado en la autenticación, 401, antes de cualquier chequeo de rol).

## Riesgos aceptados temporalmente

| Riesgo | Dueño | Fecha de revisión | Referencia |
|---|---|---|---|
| MongoDB Atlas tier M0 (cluster compartido, sin Private Endpoint) en producción | Founder | Post-MVP, sin gatillo numérico predefinido | [ADR 0015](../architecture/decisions/0015-tier-mongodb-atlas-m0.md) |
| Búsqueda web en vivo (`FoundryWebSearchProvider`) implementada (Fase 14) pero desactivada hasta aprobación legal; datos salen del boundary de compliance/geografía de Azure una vez activada (Grounding with Bing no está cubierto por el Data Protection Addendum de Microsoft) | Founder / abogado externo | ≥2 semanas antes del piloto (Fase 28) | [ADR 0011](../architecture/decisions/0011-research-provider-gate-legal-foundry.md) |
| `CuratedSourceProvider` sin UI de administración dedicada (Fase 14) — gestión solo vía API `/api/v1/admin/curated-sources/*` | Founder | Sin fecha fija, condicionado a volumen de curación | Sesión de planeación de Fase 14 |
| Retención de datos fija a 1 año, no configurable por tenant | Founder | Post-MVP | [ADR 0016](../architecture/decisions/0016-retencion-datos-1-anio.md) |
| `AuditEvent` con garantía best-effort (gap posible si el insert falla tras una mutación exitosa); sin protección contra acceso admin directo a Mongo | Founder | Post-MVP, revisitar si surge un requisito de compliance más estricto | Plan de Fase 8 (`~/.claude/plans/dreamy-enchanting-seal.md`, fuera del repo) |
| `platform_admin`/`Administrador del cliente`: solo esqueleto mínimo (un endpoint cross-tenant auditado, un endpoint de lectura de organización) — sin consola/UI de administración, sin gestión de usuarios/roles/billing | Founder | Fase 25 | `docs/development/backlog.md`, fila Fase 25 |
| Abuso de costo de IA (llamadas repetidas a `POST .../ai/requirement-suggestions`): `AIExecution` registra costo/uso solo con fines de observabilidad, sin límite duro por tenant | Founder | Fase 26 (Hardening, junto con el resto de rate limiting) | [ADR 0021](../architecture/decisions/0021-ai-provider-abstraction.md) |
| Contenido legal de `Agreement` (NDA/conflicto de interés) fijo a nivel plataforma, no administrable ni personalizable por tenant (Fase 15) | Founder | Sin fecha fija, condicionado a si legal pide cambios frecuentes de texto | Sesión de planeación de Fase 15 |
| `POST /vendor-auth/login` resuelve determinísticamente a la `vendor_contact` Membership más antigua si un mismo email tiene más de una (distintas organizaciones), en vez de ofrecer un selector (Fase 15) | Founder | Sin fecha fija, edge case sin requisito de producto detrás | Sesión de planeación de Fase 15 |

## Bandera GDPR

`VendorOrganization.country`/`region` marcaría proveedores basados en la UE para activar el flujo de cumplimiento GDPR (residencia de datos, derecho al olvido) — **estos campos todavía no existen en el modelo** (corrección de esta fase: una versión anterior de este documento afirmaba que sí, por una referencia obsoleta a una numeración de fases previa a la restructuración VS-2A/VS-2B). Ninguna fase hasta Fase 15 los agregó; quedan como trabajo futuro no comprometido a una fase concreta.

## Referencias

- [`docs/planning/approved-mvp-plan.md`](../planning/approved-mvp-plan.md), sección 11.
- [`docs/architecture/architecture.md`](../architecture/architecture.md), sección 5.
- [ADR 0002](../architecture/decisions/0002-multi-tenant-mongodb.md), [ADR 0011](../architecture/decisions/0011-research-provider-gate-legal-foundry.md).
