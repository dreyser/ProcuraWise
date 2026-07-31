# ProcuraWise — Backlog

Épicas E1-E11 mapeadas a las 29 fases del plan aprobado. Cada fase ≈ 1 sesión de Claude Code. P0 = requerido para el MVP; P1 = valioso pero no bloquea el cierre de su bloque. Dependencias son entre fases, no entre historias dentro de la misma fase (esas son secuenciales por definición).

Estado por fase se actualiza en [`docs/development/current-phase.md`](current-phase.md) (fase activa) y en la columna "Estado" de este documento conforme se completan sesiones. Estado inicial de todas las fases: **Not Started**.

---

## MVP (Fases 0-28)

### E1 — Fundación técnica (Bloque 0)

**Nota de IDs (2026-07-27):** las antiguas Fases 1 ("`identity`") y 2 ("Auth local") se restructuran para reflejar que el vertical slice se construye con un `DevelopmentIdentityProvider`, no con auth productiva. Los IDs `VS-2A`/`VS-2B`/`VS-2C`/`AUTH-PROD` reemplazan la numeración contradictoria; los números de fase ya cerrados u operativos (`0`, `8`-`28`) no se renumeran. Ver el plan de planeación correspondiente para el detalle completo de este cambio.

| Fase/ID | Historia | P | Depende de | Criterio de aceptación (resumen) | Estado |
|---|---|---|---|---|---|
| 0 | Bootstrap: docker-compose (mongo+azurite+redis+mailhog), `pyproject.toml`+uv, FastAPI `/health`, React hello-world, pre-commit, CI lint+test skeleton | P0 | — | `docker compose up` levanta todo; CI verde en PR vacío; `/health` responde 200 | ✅ Completed (2026-07-18, ejecutada como 3 sesiones — 1A/1B/1C, ver `current-phase.md`; pre-commit se movió fuera de esta fase — ver nota en VS-2A abajo, no forma parte de su alcance; "CI verde en PR vacío" verificado localmente, verificación en GitHub real pendiente del founder) |
| **VS-2A** (antes "Fase 1 — `identity`") | Tenant/User/Membership/VendorOrganization + `TenantCollection` (reglas estrictas: fuerza/rechaza `tenant_id` en insert, rechaza colisión de filtro y mutación de `tenant_id` vía `$set`/`$unset`/reemplazo, sin passthrough del driver) + `DevelopmentIdentityProvider` (`X-Dev-Membership-Id`, solo `environment=local\|test`) + `make seed-dev`/`seed-reset`. **Pre-commit explícitamente fuera de alcance** (CI ya cubre lint/format/typecheck) | P0 | 0 | Crear tenant+usuario+membership vía seed; `GET /api/v1/me` resuelve el actor correcto; una Membership de tenant A no lee recursos de tenant B (404); dev identity rechazada con `environment=production`; `make seed-dev` idempotente | 🔄 Implementado y verificado sin Docker (lint/typecheck/unit tests en verde, `make contracts` sin diff); **pendiente verificación de `make test-integration` contra Mongo real** (no había Docker disponible en la sesión de implementación) — mismo patrón de verificación en dos rondas que se usó en la Fase 1B, ver "Próximos pasos" en `current-phase.md` |
| **AUTH-PROD** (antes "Fase 2 — Auth local") | Auth local (email+password) + OIDC Microsoft/Google (authlib) + JWT propio + login/logout en frontend, sustituyendo a `DevelopmentIdentityProvider` **para rutas de comprador**. Excluye MFA. **Alcance acotado explícitamente** (decisión del founder, 2026-07-29): `vendor_contact` se queda en `DevelopmentIdentityProvider` hasta Fase 15; sin self-signup; sin recuperación de contraseña; JWT en memoria sin refresh token | P0 | VS-2C | Login exitoso ambos flujos; JWT contiene `tenant_id` correcto; sesión expira | ✅ Completed — implementado y verificado con Docker real (2026-07-29): `make test`/`test-integration`/`test-e2e`/`contracts`(x2) en verde, sin comitear — ver `docs/development/current-phase.md`. Verificación manual de OIDC contra Microsoft/Google reales pendiente (no bloqueante, IdP real requiere apps de prueba registradas) |

### E2 — Vertical slice RFP básico (Bloque 1) — cierra en VS-2C con el primer demo end-to-end

| Fase/ID | Historia | P | Depende de | Criterio de aceptación (resumen) | Estado |
|---|---|---|---|---|---|
| **VS-2B** (antes Fases 3-6) | Backend: `evaluations`+`requirements` (embebidos), `proposals`+`answers` (Proposal **es** la asociación evaluation↔vendor — no existe colección `evaluation_vendors`, corregido durante la planeación de VS-2B) con snapshot inmutable al enviar, `scoring` 0-5. Máquina de estados explícita (requirements/vendors solo en `draft`, answers solo en `collecting_responses`+`draft`, scores solo en `evaluating`, snapshot como fuente de verdad del cálculo). Mass assignment: `extra="forbid"` en todo schema de escritura. Router de proveedor físicamente separado bajo `/api/v1/vendor-portal/*`, sin acceso a `GET /api/v1/evaluations/{id}` | P0 | VS-2A | Flujo owner→requirement→vendor→proposal→submit→score→result funcional vía API; snapshot inmutable; proveedor no invitado→404; `vendor_contact` nunca accede a rutas de comprador; campo prohibido en body→422 | ✅ Completed — implementado, verificado con Docker real, comiteado y fusionado a `main` (2026-07-27, PR #14) |
| **VS-2C** (antes Fase 7 + frontend de 3-6) | Frontend: selector de Membership dev, páginas por rol, cliente OpenAPI regenerado (`client: 'react-query'`), Playwright E2E (spec de flujo desde recepción hasta completar + negativo de aislamiento — ver nota de cobertura en `current-phase.md`). Incluyó 2 ajustes de backend indispensables resueltos en la misma fase: `GET /api/v1/vendor-organizations` (catálogo de proveedores, paginado por cursor) y validación de `PATCH Requirement` sobre el documento resultante. **→ Cierre del vertical slice** | P0 | VS-2B | Demo manual de los 13 pasos desde la UI; Playwright verde; loading/empty/error visibles; actor activo siempre visible | ✅ **Completed y cerrado formalmente** (2026-07-28, verificación de cierre 2026-07-29) — `make test`/`test-integration`/`test-e2e`/`contracts`(x2) en verde, diff contra `origin/main` confirmado dentro del alcance autorizado, pendiente de commit — ver `current-phase.md` |

### E3 — Colaboración interna y auditoría (Bloque 2, parte 1)

| Fase | Historia | P | Depende de | Criterio de aceptación (resumen) | Estado |
|---|---|---|---|---|---|
| 8 | `audit` AuditEvent append-only, instrumentado retroactivamente en VS-2A/VS-2B/VS-2C | P0 | VS-2C | Toda mutación relevante del vertical slice genera un `AuditEvent` consultable | ✅ Completed (2026-07-30) — implementado y verificado con Docker real: `make lint`/`typecheck`/`test`/`test-integration`/`contracts`(x2) en verde. Alcance: evaluations (9 acciones) + proposals (submit) + scoring (score/complete), 13 acciones en total; login/OIDC (AUTH-PROD) y autosave de `ProposalAnswer` explícitamente fuera de alcance por decisión del founder — ver `current-phase.md` |
| 9 | RBAC completo (todos los roles del §4 de la spec) + `Assignment` por sección | P0 | 8 | Usuario sin rol adecuado recibe 403 en acción restringida | ✅ Completed (2026-07-30) — implementado y verificado con Docker real: `make lint`/`typecheck`/`test`/`test-integration`/`test-e2e`/`contracts`(x2) en verde. Alcance aprobado por el founder: roles de comprador (8 de los 10 del §4) + `Assignment` por sección + esqueleto mínimo de `platform_admin`/`tenant_admin`; `Colaborador proveedor` explícitamente diferido a Fase 15, consola/UI de administración a Fase 25 — ver `current-phase.md` |

### E4 — Wizard y biblioteca de requerimientos (Bloque 2, parte 2)

| Fase | Historia | P | Depende de | Criterio de aceptación (resumen) | Estado |
|---|---|---|---|---|---|
| 10 | Wizard guiado estático (sin IA) + autosave | P0 | 9 | Flujo de creación de evaluación guiado paso a paso, sin pérdida de datos al recargar | ✅ Completed (2026-07-31) — implementado y verificado con Docker real: `make lint`/`typecheck`/`test`/`test-integration`/`test-e2e` en verde, `make contracts` sin diff (fase 100% frontend, cero cambios de backend por decisión del founder — ver `current-phase.md`) |
| 11 | Biblioteca de requerimientos (`KnowledgeTemplate`, plantillas estáticas, sin IA) | P1 | 9 | Plantilla aplicable a nueva evaluación, reduce alta manual | Not Started |
| 12 | Aprobación interna + publicación con validaciones (pesos/fechas/aprobador) + snapshot inmutable | P0 | 10 | Publicación bloqueada si pesos no suman 100% o falta aprobador; snapshot generado | Not Started |

### E5 — IA de generación y descubrimiento (Bloque 3, parte 1)

| Fase | Historia | P | Depende de | Criterio de aceptación (resumen) | Estado |
|---|---|---|---|---|---|
| 13 | Adaptador `AIProvider` real (Azure OpenAI/Foundry) para Descubrimiento+Generación usando solo `InternalKnowledgeProvider`; salida validada por schema; `AIExecution` con costo/modelo/prompt-version; contrato de job asíncrono/polling adaptativo | P0 | 12 | Generación produce requerimientos candidatos válidos por schema sin red externa; polling sigue el contrato de `ADR 0012` | Not Started |
| 14 | `ResearchProvider` completo + `CuratedSourceProvider` + `FoundryWebSearchProvider` implementado pero **desactivado por defecto** (feature flag, P1 condicionado a aprobación legal); trazabilidad de fuentes | P1 (abstracción P0, activación de Foundry P1 condicionado) | 13 | Flag apagado por defecto en todo ambiente; activarlo requiere aprobación legal documentada, no solo config | Not Started |

**Nota:** el "hecho" de este epic para el MVP **no requiere** búsqueda web en vivo funcionando — ver contradicción documentada en `docs/planning/approved-mvp-plan.md`, sección 5.

### E6 — Confianza del proveedor y documentos (Bloque 3, parte 2)

| Fase | Historia | P | Depende de | Criterio de aceptación (resumen) | Estado |
|---|---|---|---|---|---|
| 15 | NDA real + conflicto de interés real, ambos vía `Agreement` (tipo `nda`/`conflict_of_interest`, usuario/IP/fecha/versión) + colaboradores múltiples por proveedor | P0 | 14 | Proveedor no accede al formulario de respuesta sin aceptar ambos `Agreement` | Not Started |
| 16 | `documents`: subida vía Azurite, escaneo AV stub, versionado, URLs temporales | P0 | 15 | Archivo subido, versionado, URL expira tras tiempo configurado | Not Started |

### E7 — Q&A y evaluación asistida por IA (Bloque 4)

| Fase | Historia | P | Depende de | Criterio de aceptación (resumen) | Estado |
|---|---|---|---|---|---|
| 17 | `qna` preguntas ligadas/generales, publicación anonimizada/privada, notificaciones | P0 | 16 | Pregunta de proveedor visible a comprador; respuesta publicada según visibilidad configurada | Not Started |
| 18 | Evaluación asistida por IA (riesgos/score sugerido) con "aceptar o modificar" obligatorio | P0 | 13, 17 | Score sugerido nunca se guarda sin acción explícita del evaluador humano | Not Started |

### E8 — TCO y scoring económico (Bloque 5, parte 1)

| Fase | Historia | P | Depende de | Criterio de aceptación (resumen) | Estado |
|---|---|---|---|---|---|
| 19 | `tco` CostItem, cálculo 1-5 años, FX congelado desde `FXRate` (actualización manual por `platform_admin`) | P0 | 18 | TCO recalculado no cambia al actualizar `FXRate` después de publicación | Not Started |
| 20 | Scoring económico completo: TCO normalizado 70%, condiciones comerciales 15% (sub-pesos por ADR 0009), riesgo/predictibilidad 15%; escala humana 0-5 con guías; scores extremos requieren comentario; criterios configurables antes de publicar, congelados al publicar | P0 | 19 | Fórmula final 40/20/40 + flags eliminatorios calcula correctamente contra casos de prueba fijos | Not Started |

### E9 — Negociación y decisión (Bloque 5, parte 2)

| Fase | Historia | P | Depende de | Criterio de aceptación (resumen) | Estado |
|---|---|---|---|---|---|
| 21 | Ronda final de negociación: Ronda 0 inicial (inmutable) + Ronda 1 opcional (BAFO), versionado `inherited`/`modified`/`removed` + `source_proposal_version`; invalidación de scores; recálculo completo de TCO por versión; comparación inicial vs. final | P0 | 20, 8 (auditoría) | Modificar una respuesta invalida su score; TCO nunca mezcla costos entre versiones; toda reapertura queda auditada con justificación | Not Started |
| 22 | `decisions`: vista de aprobador + memo de cierre | P0 | 21 | Decisión requiere aprobador humano explícito; nunca hay adjudicación automática | Not Started |

### E10 — Reportes y notificaciones (Bloque 5 cierre + Bloque 6 parte 1)

| Fase | Historia | P | Depende de | Criterio de aceptación (resumen) | Estado |
|---|---|---|---|---|---|
| 23 | Reportes/exports asíncronos vía worker (8 entregables de §10 de la spec), import Excel/CSV con preview+mapeo | P0 | 22 | Cada reporte se genera como job asíncrono y sigue el contrato de polling | Not Started |
| 24 | Notificaciones reales (Azure Communication Services) + centro in-app | P1 | 23 | Notificación real enviada en al menos un evento clave (invitación, publicación) | Not Started |

### E11 — Billing, hardening y lanzamiento (Bloque 6 cierre)

| Fase | Historia | P | Depende de | Criterio de aceptación (resumen) | Estado |
|---|---|---|---|---|---|
| 25 | Billing/Admin básico P1: Stripe checkout, consola admin cross-tenant auditada | P1 | 9 | Cobro de prueba exitoso en modo sandbox; acción admin cross-tenant queda auditada con motivo | Not Started |
| 26 | Hardening: rate limiting, CSRF, headers, escaneo secretos/deps en CI, WCAG AA, performance, backup/restore, `threat-model.md` cerrado | P0 | 24 | Escaneo de seguridad en CI sin hallazgos críticos abiertos; restore de backup probado | Not Started |
| 27 | Infra Azure real (Bicep) + CI/CD GitHub Actions OIDC staging→prod | P0 | 26 | Deploy a staging exitoso vía pipeline, sin secretos de larga vida en el repo | Not Started |
| 28 | UAT piloto 1-3 empresas, fixes, lanzamiento controlado | P0 | 27 | Al menos 1 evaluación completa cerrada end-to-end por un piloto real | Not Started |

---

## Notas explícitas de alcance del backlog

- **La integración de IA (E5) no es requisito para completar el primer vertical slice (E2, VS-2A/VS-2B/VS-2C).** El vertical slice usa scoring 100% manual, sin `AIProvider`.
- **Stripe, correo real y Azure productivo no son requisito de la primera fase (E1) ni del vertical slice (E2).** Stripe llega en la Fase 25 (P1), correo real en la Fase 24, Azure real en la Fase 27 — todas muy posteriores al cierre del vertical slice.
- **Auth productiva (`AUTH-PROD`) no es requisito para completar el vertical slice.** El vertical slice usa `DevelopmentIdentityProvider` (`X-Dev-Membership-Id`), gateado a `environment in (local, test)` — ver VS-2A.
- Cada fase, al cerrar sesión, actualiza `docs/development/current-phase.md` y `docs/development/session-handoff.md` — único mecanismo de continuidad entre sesiones sin memoria compartida.
