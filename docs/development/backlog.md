# ProcuraWise — Backlog

Épicas E1-E11 mapeadas a las 29 fases del plan aprobado. Cada fase ≈ 1 sesión de Claude Code. P0 = requerido para el MVP; P1 = valioso pero no bloquea el cierre de su bloque. Dependencias son entre fases, no entre historias dentro de la misma fase (esas son secuenciales por definición).

Estado por fase se actualiza en [`docs/development/current-phase.md`](current-phase.md) (fase activa) y en la columna "Estado" de este documento conforme se completan sesiones. Estado inicial de todas las fases: **Not Started**.

---

## MVP (Fases 0-28)

### E1 — Fundación técnica (Bloque 0)

| Fase | Historia | P | Depende de | Criterio de aceptación (resumen) | Estado |
|---|---|---|---|---|---|
| 0 | Bootstrap: docker-compose (mongo+azurite+redis+mailhog), `pyproject.toml`+uv, FastAPI `/health`, React hello-world, pre-commit, CI lint+test skeleton | P0 | — | `docker compose up` levanta todo; CI verde en PR vacío; `/health` responde 200 | ✅ Completed (2026-07-18, ejecutada como 3 sesiones — 1A/1B/1C, ver `current-phase.md`; pre-commit se movió a la Fase 1 `identity`; "CI verde en PR vacío" verificado localmente, verificación en GitHub real pendiente del founder) |
| 1 | `identity`: Tenant/User/Membership + `TenantCollection` + middleware que extrae `tenant_id` del JWT | P0 | 0 | Crear tenant+usuario vía API; test negativo: tenant A no lee datos de tenant B | Not Started |
| 2 | Auth local (email+password) + OIDC Microsoft/Google (authlib) + JWT propio + login/logout en frontend. Excluye MFA | P0 | 1 | Login exitoso ambos flujos; JWT contiene `tenant_id` correcto; sesión expira | Not Started |

### E2 — Vertical slice RFP básico (Bloque 1) — cierra en la Fase 7 con el primer demo end-to-end

| Fase | Historia | P | Depende de | Criterio de aceptación (resumen) | Estado |
|---|---|---|---|---|---|
| 3 | `evaluations` CRUD + máquina de estados mínima (Borrador→Publicado→Cerrado) | P0 | 2 | Crear/editar evaluación en Borrador; transición de estado validada | Not Started |
| 4 | `requirements` alta manual (categoría, prioridad, eliminatorio, 3 tipos de respuesta, peso) | P0 | 3 | Requerimiento asociado a evaluación; pesos visibles | Not Started |
| 5 | `vendors` invitación simulada (email→log) + portal proveedor vía token, router `/vendor-portal` + captura `country`/`region` + mock de pantallas NDA/conflicto de interés (sin `Agreement` formal todavía) | P0 | 4 | Token de invitación da acceso solo a esa evaluación; proveedor no ve otras evaluaciones | Not Started |
| 6 | `proposals` respuesta de proveedor, borrador, envío formal con snapshot inmutable | P0 | 5 | Envío crea snapshot; edición posterior al envío bloqueada | Not Started |
| 7 | `scoring` básico manual 0-5 + tabla comparativa. **→ Cierre del vertical slice** | P0 | 6 | Comprador califica y ve comparativo de todos los proveedores invitados | Not Started |

### E3 — Colaboración interna y auditoría (Bloque 2, parte 1)

| Fase | Historia | P | Depende de | Criterio de aceptación (resumen) | Estado |
|---|---|---|---|---|---|
| 8 | `audit` AuditEvent append-only, instrumentado retroactivamente en fases 1-7 | P0 | 7 | Toda mutación relevante de fases 1-7 genera un `AuditEvent` consultable | Not Started |
| 9 | RBAC completo (todos los roles del §4 de la spec) + `Assignment` por sección | P0 | 8 | Usuario sin rol adecuado recibe 403 en acción restringida | Not Started |

### E4 — Wizard y biblioteca de requerimientos (Bloque 2, parte 2)

| Fase | Historia | P | Depende de | Criterio de aceptación (resumen) | Estado |
|---|---|---|---|---|---|
| 10 | Wizard guiado estático (sin IA) + autosave | P0 | 9 | Flujo de creación de evaluación guiado paso a paso, sin pérdida de datos al recargar | Not Started |
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

- **La integración de IA (E5) no es requisito para completar el primer vertical slice (E2, fases 0-7).** El vertical slice usa scoring 100% manual, sin `AIProvider`.
- **Stripe, correo real y Azure productivo no son requisito de la primera fase (E1) ni del vertical slice (E2).** Stripe llega en la Fase 25 (P1), correo real en la Fase 24, Azure real en la Fase 27 — todas muy posteriores al cierre del vertical slice.
- Cada fase, al cerrar sesión, actualiza `docs/development/current-phase.md` y `docs/development/session-handoff.md` — único mecanismo de continuidad entre sesiones sin memoria compartida.
