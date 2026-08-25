# ADR 0026: Reviewer y aprobación en dos pasos (Owner→Reviewer→Approver)

**Estado:** Accepted
**Fecha:** 2026-08-25
**Origen:** Remediación UAT piloto (E12), bloque R2 (UAT-06/07/08); dos preguntas bloqueantes resueltas por el founder en esta sesión (ver "Decisión" abajo); la pregunta sobre el modelado de `ApprovalStatus` ya había sido resuelta por el founder en la sesión de cierre de planeación de la remediación (2026-08-24, registrada en `backlog.md` sección E12).

## Contexto

El primer UAT real (Fase 28, Bloque C) expuso que el flujo de aprobación actual (Fase 12: `evaluation_owner` asigna un `approver`, pide aprobación, el approver aprueba/rechaza) es insuficiente para el caso real de un comprador con un revisor interno intermedio antes de escalar a quien aprueba formalmente (UAT-06/07/08). Además, `EvaluationTabNav.tsx` es hoy una lista estática de 10 pestañas sin ningún condicional de rol — cualquier actor ve las 10, incluida "Aprobación", sin importar si puede actuar en ella (UAT-08).

El modelo actual (`evaluations/models.py`) ya resuelve un problema estructuralmente idéntico para el approver: `approver_membership_id` (una Membership específica designada por evaluación, no un rol global genérico) + `approval_status: ApprovalStatus` (`not_requested|pending|approved|rejected`) + timestamps/autor de solicitud y decisión + `approval_comment`. `Assignment` (dimension+section, solo para gating de scoring por evaluador) no puede representar "el revisor de esta evaluación" — es un concepto distinto (todo-la-evaluación, no una sección de un dimension de scoring) y sería forzarlo a un molde que no le corresponde.

**Pregunta bloqueante ya resuelta (2026-08-24, `backlog.md` E12):** `ApprovalStatus` no gana un 5º valor. "Solicitar cambios" es una acción de UI que persiste `rejected`, preservando comentarios por requerimiento, con el evento de auditoría distinguiendo explícitamente una solicitud de cambios de un rechazo genérico.

**Dos preguntas bloqueantes adicionales, resueltas por el founder en esta sesión:**
1. ¿El paso de Reviewer es obligatorio para toda evaluación, o opcional por evaluación? → **Opcional por evaluación.** Si el Owner no asigna revisor, el flujo es idéntico al actual (Owner→Approver, sin cambios). Si asigna uno, la evaluación debe pasar revisión antes de poder pedir aprobación. Elegido explícitamente para no romper compatibilidad con evaluaciones/tests existentes y no forzar una migración de datos.
2. Cuando el Reviewer aprueba, ¿la evaluación avanza automáticamente a "pendiente de aprobación" (notificando al approver en la misma acción), o el Owner debe volver a pedir aprobación manualmente? → **Auto-encadenado.** La aprobación del Reviewer, en la misma transacción, mueve `approval_status` a `pending` (si el approver ya está asignado y el resto de la readiness ya se cumple) y notifica al approver — sin una segunda acción manual del Owner.

## Decisión

**Reviewer no es un nuevo valor de `Role`.** Reutiliza el rol ya existente `internal_collaborator` (Fase 9) — la misma solución que ya usa `approver_membership_id`: una Membership específica designada por evaluación, no una capacidad global nueva. El Owner designa el revisor con un endpoint nuevo, `POST /evaluations/{id}/reviewer`, mismo patrón exacto que `set_approver` (`SetApproverRequest`, guard de rol de la Membership candidata = `internal_collaborator`, guard de auto-revisión igual a `SelfApprovalError`).

**Nuevos campos en `Evaluation`** (todos opcionales, default sin asignar — sin migración de datos, mismo patrón `doc.get(...)` que el resto del modelo):
- `reviewer_membership_id: str | None`
- `review_status: ApprovalStatus` (reutiliza el mismo tipo, default `"not_requested"` — no es un estado nuevo, es la misma máquina de estados aplicada a una segunda etapa)
- `review_requested_at`, `review_requested_by_membership_id`
- `review_decided_at`, `review_decided_by_membership_id`
- `review_comment: str | None`

**Nuevos endpoints** (mismo router `evaluations/`, mismo prefijo `/evaluations/{evaluation_id}`):
- `POST /reviewer` — Owner, draft + `review_status in (not_requested, rejected)`.
- `POST /request-review` / `DELETE /request-review` — Owner, mismo patrón que `request_approval`/`withdraw_approval_request`. Nueva razón de *readiness* ("un revisor debe estar asignado antes de pedir revisión") solo aparece **si `reviewer_membership_id` no es `None`** — si el Owner nunca asignó revisor, esta etapa no existe para esa evaluación.
- `POST /review/approve` — Reviewer (`actor.membership_id == reviewer_membership_id`), `review_status: pending → approved`. **En la misma transacción**, si el resto de la readiness de aprobación ya se cumple (approver asignado, `response_deadline` fijado), también transiciona `approval_status: not_requested|rejected → pending` y notifica al approver — el mismo efecto que `request_approval`, sin una segunda llamada del Owner (pregunta bloqueante #2).
- `POST /review/reject` — Reviewer, `review_status: pending → rejected`. Cuerpo: `comment: str` (requerido, igual que `RejectionRequest` hoy) + `requirement_notes: list[{requirement_id, comment}] | None` (nuevo, opcional) + `kind: "rejected" | "changes_requested"` (default `"rejected"`). El campo persistido (`review_status`) es idéntico en ambos casos — solo cambia qué acción de auditoría se registra.
- `POST /approve` / `POST /reject` (Approver, ya existentes) ganan la misma extensión `requirement_notes`/`kind` por simetría — un approver que rechaza también puede "solicitar cambios" con comentarios por requerimiento, con el mismo tratamiento de auditoría distinguible.

**Auditoría** (`audit/models.py`, `AuditAction`): nuevos valores `evaluation_reviewer_set`, `evaluation_review_requested`, `evaluation_review_withdrawn`, `evaluation_review_approved`, `evaluation_review_rejected`, `evaluation_review_changes_requested`, `evaluation_changes_requested` (esta última, la variante "solicitar cambios" del `reject` del Approver que ya existe). Nunca se colapsa una solicitud de cambios y un rechazo genérico en la misma acción de auditoría, exactamente como exige la decisión ya aprobada del 2026-08-24 — el discriminador es la propia `action`, no un campo de metadata opcional que un lector pueda ignorar.

**Invalidación por edición** (`INVALIDATED_BY_APPROVAL_EDIT`, hoy `("pending", "approved")` solo para `approval_status`): se extiende el mismo disparador para resetear también `review_status`/`review_comment`/`review_decided_*` a su estado inicial cuando el Owner hace una edición draft-gateada mientras `review_status` está en `pending`/`approved` — mismo principio que ya protege `approval_status`: una edición posterior a una decisión invalida esa decisión, nunca la deja como aprobación implícita de un contenido distinto al revisado.

**Navegación contextual (UAT-08):** `EvaluationTabNav.tsx` deja de ser una lista estática — la pestaña "Aprobación" se oculta para cualquier actor que no sea `evaluation_owner`, el `approver` asignado, o (nuevo) el `reviewer` asignado de esa evaluación específica. Cambio puramente de visibilidad en frontend, mismo principio ya aplicado en R1B/UAT-14 (el backend ya es la autoridad real vía los guards de arriba; ocultar una pestaña sin acción disponible no es, en sí, un control de seguridad).

## Alternativas consideradas

- **Nuevo valor `Role = "reviewer"` global**: descartado — un reviewer es una capacidad por-evaluación sobre una Membership existente (igual que approver), no una nueva categoría de usuario del tenant. Habría requerido tocar cada lugar que enumera `Role` (RBAC, seeds, formularios de invitación) sin ganar nada que `reviewer_membership_id` no dé ya.
- **Modelar el Reviewer vía `Assignment`**: descartado — `Assignment.dimension` es `Dimension` (`functional|technical|economic`), un concepto de scoring por sección; forzar "revisor de toda la evaluación" a esa forma sería una capa de indirección falsa sin beneficio, y complicaría innecesariamente `enforce_section_assignment`, que no tiene nada que ver con este flujo.
- **Agregar `changes_requested` como 5º valor de `ApprovalStatus`**: descartado por el founder (decisión previa, 2026-08-24) — tocaría un enum ya consumido por `notifications/`/`reports/` (`decision_record`) sin necesidad; el mismo resultado (distinguible en auditoría, con comentarios por requerimiento) se logra sin tocar el tipo.
- **Reviewer obligatorio para toda evaluación**: descartado por el founder (pregunta bloqueante #1) — habría exigido migrar/actualizar cada evaluación y test existente que hoy usa el flujo Owner→Approver de un solo paso, sin beneficio adicional sobre hacerlo opcional y aditivo.
- **Reencadenar manualmente tras la aprobación del Reviewer**: descartado por el founder (pregunta bloqueante #2) — una segunda acción manual del Owner no aporta ningún control adicional real (el Owner ya decidió delegar en el Reviewer al pedir la revisión), solo fricción.
- **Comentarios por requerimiento en una colección nueva tipo `qna/`**: descartado — sobre-ingeniería para este alcance; una lista embebida (`requirement_notes`) en el propio cuerpo de la petición de rechazo/solicitud-de-cambios, persistida junto al evento de auditoría, cubre el criterio ("comentarios por requerimiento preservados") sin infraestructura nueva.

## Consecuencias

- Ningún dato existente requiere migración: los campos nuevos son opcionales y ausentes en evaluaciones ya creadas se leen como `not_requested`/`None`, comportamiento idéntico al actual.
- Cada spec e2e/test de integración existente que ejercita el flujo de aprobación (`evaluation-approval.spec.ts`, `proposal-negotiation.spec.ts`, `vertical-slice.spec.ts`, `decision-approval.spec.ts`, `tests/conftest.py::approve_and_publish`, etc.) sigue pasando sin modificación — ninguna asigna revisor, así que ninguna atraviesa la nueva etapa. Los tests nuevos de R2 deben cubrir explícitamente el camino **con** revisor (journey de 3 actores) y confirmar que el camino **sin** revisor sigue sin cambios.
- `dev_seed.py` ya siembra una Membership `internal_collaborator` (`Colaborador Interno A`) — candidato natural para el actor Reviewer en los nuevos tests, sin sembrar una identidad nueva.
- El criterio de aceptación de R2 en `backlog.md` ("reviewer nunca aprueba, approver nunca edita") se verifica con un test de autorización negativo: un Reviewer que intenta llamar `/approve`/`/reject` (los endpoints del Approver) debe recibir 403 por rol, y un Approver que intenta editar requerimientos/vendors debe recibir 403 por `require_owner` — ambos guards ya existen hoy, el test solo los ejercita en la combinación nueva.
- `EvaluationTabNav` deja de recibir solo `evaluationId` — necesita también el `actor` (ya disponible vía `useActor()`/`ActorContext` en cada página que la renderiza) y los `membership_id` de approver/reviewer de la evaluación para decidir qué pestañas mostrar.

## Referencias

- Backlog, sección E12, bloque R2.
- [ADR 0021 — Abstracción de proveedor de IA](0021-ai-provider-abstraction.md) (mismo principio de "capacidad sobre membership existente, no rol nuevo", aplicado ahí a la frontera de proveedores).
- `docs/development/current-phase.md` — entradas de R1A/R1B/R1C (mismo remediation, bloques previos).
- `service/procurawise/evaluations/models.py`, `evaluations/service.py` (flujo de aprobación de un paso ya existente, extendido aquí).
