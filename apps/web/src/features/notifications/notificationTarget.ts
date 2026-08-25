import type { NotificationResponse } from '@/api/client'

export type NotificationAudience = 'buyer' | 'vendor'

/**
 * UAT-13 (R4): every notification already carries resource_type/resource_id/
 * evaluation_id (notifications/models.py) - this maps that data to an
 * in-app route, so clicking a notification actually goes somewhere instead
 * of only marking it read (NotificationsBell.tsx's previous, deliberate
 * Fase 24 scope cut).
 *
 * Two events are intentionally left unmapped (return null, rendered as a
 * plain non-navigable item):
 * - `vendor_invited`: the recipient isn't authenticated yet when it fires
 *   (evaluation_id is always null) - the actionable link is the invite URL
 *   already in the email/vendor_auth_service.py, not an in-app route.
 * - `qna_answer_published` (vendor audience): the vendor portal has no
 *   dedicated Q&A route to land on (vendor/proposals/:id has an embedded
 *   thread, not a deep-linkable one) - building that route is out of scope
 *   here.
 *
 * `approval_requested` is overloaded across two resources (evaluations.
 * service.py's own approver request vs. decisions.service.py's decision
 * approver request) and must be routed on `resource_type`, not `event`
 * alone. `proposal_submitted`/`proposal_reopened` are sent to both a buyer
 * and a vendor recipient from the same call site with different intended
 * destinations, hence the `audience` parameter.
 */
export function resolveNotificationTarget(
  item: NotificationResponse,
  audience: NotificationAudience,
): string | null {
  const evaluationId = item.evaluation_id

  switch (item.event) {
    case 'evaluation_published':
      return evaluationId ? `/evaluations/${evaluationId}` : null
    case 'approval_requested':
      if (!evaluationId) return null
      return item.resource_type === 'decision'
        ? `/evaluations/${evaluationId}/decision`
        : `/evaluations/${evaluationId}/approval`
    case 'review_requested':
      return evaluationId ? `/evaluations/${evaluationId}/approval` : null
    case 'qna_question_received':
      return evaluationId ? `/evaluations/${evaluationId}/qna` : null
    case 'proposal_submitted':
    case 'proposal_reopened':
      return audience === 'vendor'
        ? `/vendor/proposals/${item.resource_id}`
        : evaluationId
          ? `/evaluations/${evaluationId}/proposals`
          : null
    case 'evaluation_completed':
      return evaluationId ? `/evaluations/${evaluationId}/results` : null
    case 'payment_succeeded':
      return '/billing'
    case 'vendor_invited':
    case 'qna_answer_published':
    default:
      return null
  }
}
