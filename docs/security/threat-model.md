# ProcuraWise — Modelo de amenazas

Este documento se actualiza a medida que avanzan las fases (se cierra formalmente en la Fase 26 — Hardening, según [`docs/development/backlog.md`](../development/backlog.md)). Hasta entonces refleja el diseño aprobado, no controles ya implementados (el repositorio es greenfield al momento de escribir este documento).

## Activos

- Datos de tenants compradores: evaluaciones, requerimientos, propuestas, scores, decisiones, documentos.
- Datos de proveedores: respuestas, precios, documentos, aceptaciones de NDA/conflicto de interés.
- Credenciales y JWT (compradores, proveedores, `platform_admin`).
- Tasas FX (`FXRate`), configuración de rúbricas económicas.
- Prompts, resultados y trazabilidad de ejecuciones de IA (`AIExecution`).
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
| `ai`/`ResearchProvider` | Information disclosure a terceros | Política de datos sanitizados, `FoundryWebSearchProvider` tras flag + aprobación legal (ADR 0011) |
| `admin` | Elevación de privilegios cross-tenant | `find_across_tenants()` explícito, auditado, con motivo obligatorio — **implementado desde Fase 9** (antes era diseño aprobado sin código) |
| `assignments` | Un evaluador ve/califica secciones fuera de su responsabilidad | Rol esperado validado contra la dimensión al crear el `Assignment`; enforcement de sección en `scoring.upsert_score` (Fase 9) |
| `documents` | Malware, denial of service por tamaño | Escaneo AV stub (Fase 16), hardening real (Fase 26) |

## Controles existentes vs. pendientes

- **Existentes (diseñados, a implementar desde Fase 1):** aislamiento estructural de tenant, router disjunto de proveedores, snapshot inmutable, `Agreement` tipado.
- **Baseline de seguridad de pipeline (implementado desde Fase 1C, 2026-07-18):** secret scanning en cada PR/push a `main` vía `gitleaks` (`.github/workflows/security.yml`, job `secret-scan`, **bloqueante**), dependency vulnerability scanning vía `pip-audit` (Python) y `pnpm audit` (JS/pnpm) (jobs `python-deps`/`frontend-deps`, **informativo por ahora** — el repo es privado sin GitHub Advanced Security, y un árbol de dependencias recién creado tiene CVEs transitivos sin fix disponible que bloquearían PRs sin motivo real; política de bloqueo se revisita cuando haya bandwidth para triage regular), `Dependabot` para `pip`/`npm`/`github-actions`. **CodeQL no implementado** — no disponible gratis en un repo privado sin GHAS (requeriría hacer público el repo o adquirir GitHub Advanced Security); queda documentado aquí como mejora disponible, no como pendiente de una fase futura concreta.
- **Pendientes (Fase 26 — Hardening):** rate limiting, CSRF, headers de seguridad, promover dependency scanning de informativo a bloqueante (una vez exista bandwidth de triage regular), CodeQL si cambia la visibilidad del repo o se adquiere GHAS, SBOM, WCAG 2.1 AA, pruebas de performance, backup/restore verificado.
- **Pendientes de gate externo:** aprobación legal de web-grounding antes de activar `FoundryWebSearchProvider` (ver ADR 0011).

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
- **Diferido explícitamente**: `Colaborador proveedor` (spec §6.5 FR-043) → Fase 15, junto con auth real de `vendor_contact`; `evaluator_economic` existe como rol pero no tiene nada real que calificar hasta que `Dimension` gane un valor `"economic"` (Fase 19-20).

## Riesgos aceptados temporalmente

| Riesgo | Dueño | Fecha de revisión | Referencia |
|---|---|---|---|
| MongoDB Atlas tier M0 (cluster compartido, sin Private Endpoint) en producción | Founder | Post-MVP, sin gatillo numérico predefinido | [ADR 0015](../architecture/decisions/0015-tier-mongodb-atlas-m0.md) |
| Búsqueda web en vivo (`FoundryWebSearchProvider`) desactivada hasta aprobación legal | Founder / abogado externo | ≥2 semanas antes del piloto (Fase 28) | [ADR 0011](../architecture/decisions/0011-research-provider-gate-legal-foundry.md) |
| Retención de datos fija a 1 año, no configurable por tenant | Founder | Post-MVP | [ADR 0016](../architecture/decisions/0016-retencion-datos-1-anio.md) |
| `AuditEvent` con garantía best-effort (gap posible si el insert falla tras una mutación exitosa); sin protección contra acceso admin directo a Mongo | Founder | Post-MVP, revisitar si surge un requisito de compliance más estricto | Plan de Fase 8 (`~/.claude/plans/dreamy-enchanting-seal.md`, fuera del repo) |
| `platform_admin`/`Administrador del cliente`: solo esqueleto mínimo (un endpoint cross-tenant auditado, un endpoint de lectura de organización) — sin consola/UI de administración, sin gestión de usuarios/roles/billing | Founder | Fase 25 | `docs/development/backlog.md`, fila Fase 25 |

## Bandera GDPR

`VendorOrganization.country`/`region` (capturado en la Fase 5) marca proveedores basados en la UE; solo esos activan el flujo de cumplimiento GDPR (residencia de datos, derecho al olvido). El resto de tenants no lo activa por default.

## Referencias

- [`docs/planning/approved-mvp-plan.md`](../planning/approved-mvp-plan.md), sección 11.
- [`docs/architecture/architecture.md`](../architecture/architecture.md), sección 5.
- [ADR 0002](../architecture/decisions/0002-multi-tenant-mongodb.md), [ADR 0011](../architecture/decisions/0011-research-provider-gate-legal-foundry.md).
