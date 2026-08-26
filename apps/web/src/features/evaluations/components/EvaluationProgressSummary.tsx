import {
  useGetResultsApiV1EvaluationsEvaluationIdResultsGet,
  useListAssignmentsApiV1EvaluationsEvaluationIdAssignmentsGet,
  useListOrgMembersApiV1OrgMembersGet,
  useListProposalsApiV1EvaluationsEvaluationIdProposalsGet,
  type AssignmentListResponse,
  type EvaluationDetailResponse,
  type OrgMembersListResponse,
  type ProposalSummaryResponse,
  type ResultsResponse,
} from '@/api/client'
import { unwrapData } from '@/lib/http'
import { DisabledActionHint } from '@/components/DisabledActionHint'
import { StatusBadge } from '@/components/StatusBadge'
import { LoadingState } from '@/components/LoadingState'
import { translateAssignmentStatus, translateDimension } from '@/lib/enumLabels'
import { startCollectionPreconditionReasons } from '@/features/evaluations/lib/evaluationReadiness'

/** UAT-04/09 (R3): a consolidated view of "what's blocking this evaluation
 * and what should the owner do next", plus per-evaluator completion
 * (self-reported via Assignment.status, AssignmentsPage.tsx) - all derived
 * from data already exposed by existing endpoints (no new backend
 * aggregation). Owner-only (mirrors ORG_MEMBERS_READ_ROLES, needed to
 * resolve evaluator display names). */
export function EvaluationProgressSummary({
  evaluationId,
  evaluation,
}: {
  evaluationId: string
  evaluation: EvaluationDetailResponse
}) {
  const assignmentsQuery =
    useListAssignmentsApiV1EvaluationsEvaluationIdAssignmentsGet(evaluationId)
  const assignments = unwrapData<AssignmentListResponse>(assignmentsQuery.data)?.items ?? []

  const proposalsQuery = useListProposalsApiV1EvaluationsEvaluationIdProposalsGet(evaluationId, {
    query: { enabled: evaluation.status === 'collecting_responses' },
  })
  const proposals = unwrapData<ProposalSummaryResponse[]>(proposalsQuery.data) ?? []

  const resultsQuery = useGetResultsApiV1EvaluationsEvaluationIdResultsGet(evaluationId, {
    query: { enabled: evaluation.status === 'evaluating' || evaluation.status === 'completed' },
  })
  const results = unwrapData<ResultsResponse>(resultsQuery.data)

  const orgMembersQuery = useListOrgMembersApiV1OrgMembersGet()
  const orgMembers = unwrapData<OrgMembersListResponse>(orgMembersQuery.data)?.items ?? []
  const evaluatorLabel = (membershipId: string) =>
    orgMembers.find((member) => member.membership_id === membershipId)?.display_name ?? membershipId

  const { blockers, nextAction } = computeProgress(evaluation, proposals, results)

  if (assignmentsQuery.isLoading) return <LoadingState label="Cargando estado consolidado…" />

  return (
    <section className="mt-6 rounded-md border border-border p-4">
      <h2 className="text-sm font-semibold text-foreground">Estado consolidado</h2>

      <div className="mt-3">
        <p className="text-sm font-medium text-foreground">Próxima acción</p>
        <p className="mt-1 text-sm text-muted-foreground">{nextAction}</p>
      </div>

      {blockers.length > 0 && (
        <div className="mt-3">
          <p className="text-sm font-medium text-foreground">Bloqueadores</p>
          <DisabledActionHint reasons={blockers} />
        </div>
      )}

      {assignments.length > 0 && (
        <div className="mt-3">
          <p className="text-sm font-medium text-foreground">Completitud por evaluador</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Autorreportada por cada evaluador en la pestaña "Asignaciones", no calculada a partir de
            las calificaciones reales.
          </p>
          <ul className="mt-2 flex flex-col gap-1.5 text-sm">
            {assignments.map((assignment) => (
              <li key={assignment.id} className="flex flex-wrap items-center gap-2">
                <span className="text-foreground">
                  {evaluatorLabel(assignment.evaluator_membership_id)}
                </span>
                <span className="text-xs text-muted-foreground">
                  {translateDimension(assignment.dimension)} · {assignment.section}
                </span>
                <StatusBadge label={translateAssignmentStatus(assignment.status)} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

function computeProgress(
  evaluation: EvaluationDetailResponse,
  proposals: ProposalSummaryResponse[],
  results: ResultsResponse | undefined,
): { blockers: string[]; nextAction: string } {
  if (evaluation.status === 'draft') {
    const blockers = startCollectionPreconditionReasons(evaluation)
    return {
      blockers,
      nextAction:
        blockers.length > 0
          ? blockers[0]
          : 'Todo listo - puedes iniciar la recepción de propuestas.',
    }
  }

  if (evaluation.status === 'collecting_responses') {
    const pending = proposals.filter((p) => p.status !== 'submitted')
    const blockers: string[] = []
    if (pending.length > 0) {
      blockers.push(`${pending.length} de ${proposals.length} proveedores no han respondido.`)
    }
    if (
      evaluation.response_deadline &&
      new Date(evaluation.response_deadline) < new Date() &&
      pending.length > 0
    ) {
      blockers.push('La fecha límite de respuesta ya pasó.')
    }
    return {
      blockers,
      nextAction:
        pending.length > 0
          ? 'Espera a que respondan los proveedores restantes, o inicia la evaluación con lo ya recibido.'
          : 'Todos los proveedores respondieron - puedes iniciar la evaluación.',
    }
  }

  if (evaluation.status === 'evaluating') {
    const blockers: string[] = []
    if (results?.scoring_status === 'incomplete') {
      blockers.push('Hay requerimientos sin calificar en al menos una propuesta.')
    }
    const alertsCount =
      results?.proposals.reduce((sum, p) => sum + p.mandatory_alerts_count, 0) ?? 0
    if (alertsCount > 0) {
      blockers.push(`${alertsCount} alerta(s) de requerimiento obligatorio sin cumplir.`)
    }
    return {
      blockers,
      nextAction:
        results?.scoring_status === 'complete'
          ? 'La calificación está completa - puedes completar la evaluación y registrar la decisión.'
          : 'Completa la calificación pendiente antes de cerrar la evaluación.',
    }
  }

  return {
    blockers: [],
    nextAction: 'Evaluación completada - revisa los resultados o registra la decisión final.',
  }
}
