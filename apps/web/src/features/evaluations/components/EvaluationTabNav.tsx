import { NavLink } from 'react-router-dom'
import {
  useGetEvaluationApiV1EvaluationsEvaluationIdGet,
  type EvaluationDetailResponse,
} from '@/api/client'
import { useAuth } from '@/auth/AuthContext'
import { unwrapData } from '@/lib/http'

const TABS = [
  { suffix: '', label: 'Resumen' },
  { suffix: '/requirements', label: 'Requerimientos' },
  { suffix: '/vendors', label: 'Proveedores' },
  { suffix: '/assignments', label: 'Asignaciones' },
  { suffix: '/approval', label: 'Aprobación' },
  { suffix: '/proposals', label: 'Propuestas' },
  { suffix: '/qna', label: 'Q&A' },
  { suffix: '/results', label: 'Resultados' },
  { suffix: '/decision', label: 'Decisión' },
  { suffix: '/reports', label: 'Reportes' },
]

/** UAT-08 (ADR 0026, R2): "Aprobación" is hidden from any actor who can
 * never act on it there - the evaluation_owner (always), the assigned
 * approver, and (new) the assigned reviewer. Reuses the same query every
 * page that renders this nav already issued for `evaluationId` (identical
 * key, React Query dedupes it), so this never adds a real extra request -
 * only a page rendering the nav before its own evaluation query has
 * resolved would see a brief, harmless flicker of the tab appearing once
 * cached data lands, which none of the current callers do (they all gate
 * their own render on the evaluation already being loaded). */
export function EvaluationTabNav({ evaluationId }: { evaluationId: string }) {
  const { actor } = useAuth()
  const evaluationQuery = useGetEvaluationApiV1EvaluationsEvaluationIdGet(evaluationId)
  const evaluation = unwrapData<EvaluationDetailResponse>(evaluationQuery.data)

  const canSeeApprovalTab =
    actor?.role === 'evaluation_owner' ||
    (actor?.role === 'approver' && actor.membership_id === evaluation?.approver_membership_id) ||
    (actor?.role === 'internal_collaborator' &&
      actor.membership_id === evaluation?.reviewer_membership_id)

  const tabs = TABS.filter((tab) => tab.suffix !== '/approval' || canSeeApprovalTab)

  return (
    <nav aria-label="Secciones de la evaluación" className="mt-4 flex gap-4 border-b border-border">
      {tabs.map((tab) => (
        <NavLink
          key={tab.suffix}
          to={`/evaluations/${evaluationId}${tab.suffix}`}
          end={tab.suffix === ''}
          className={({ isActive }) =>
            `border-b-2 pb-2 text-sm ${
              isActive
                ? 'border-foreground font-medium text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  )
}
