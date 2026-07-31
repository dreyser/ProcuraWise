import { describe, expect, it } from 'vitest'
import {
  hasCompleteWeights,
  hasLinkedVendor,
  isReadyToRequestApproval,
  isReadyToStartCollection,
  requestApprovalPreconditionReasons,
  startCollectionPreconditionReasons,
  weightOf,
} from './evaluationReadiness'
import type { EvaluationDetailResponse, RequirementResponse } from '@/api/client'

function requirement(overrides: Partial<RequirementResponse>): RequirementResponse {
  return {
    id: 'req-1',
    dimension: 'functional',
    category: 'Core',
    title: 'Título',
    description: 'Descripción',
    priority: 'important',
    response_type: 'text',
    weight: 0,
    required: true,
    buyer_guidance: null,
    display_order: 1,
    options: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function evaluation(overrides: Partial<EvaluationDetailResponse>): EvaluationDetailResponse {
  return {
    id: 'eval-1',
    name: 'Evaluación',
    description: '',
    status: 'draft',
    requirements: [],
    linked_vendor_count: 0,
    created_by_membership_id: 'membership-1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    collecting_responses_started_at: null,
    evaluating_started_at: null,
    completed_at: null,
    approval_status: 'not_requested',
    approver_membership_id: null,
    response_deadline: null,
    approval_requested_at: null,
    approval_requested_by_membership_id: null,
    approval_decided_at: null,
    approval_decided_by_membership_id: null,
    approval_comment: null,
    approval_snapshot_id: null,
    ...overrides,
  }
}

describe('evaluationReadiness', () => {
  it('sums weight only within the requested dimension', () => {
    const e = evaluation({
      requirements: [
        requirement({ dimension: 'functional', weight: 15 }),
        requirement({ dimension: 'functional', weight: 25 }),
        requirement({ dimension: 'technical', weight: 20 }),
      ],
    })
    expect(weightOf(e, 'functional')).toBe(40)
    expect(weightOf(e, 'technical')).toBe(20)
  })

  it('hasCompleteWeights is false until both dimensions hit their exact target', () => {
    expect(
      hasCompleteWeights(
        evaluation({ requirements: [requirement({ dimension: 'functional', weight: 40 })] }),
      ),
    ).toBe(false)
    expect(
      hasCompleteWeights(
        evaluation({
          requirements: [
            requirement({ dimension: 'functional', weight: 40 }),
            requirement({ dimension: 'technical', weight: 20 }),
          ],
        }),
      ),
    ).toBe(true)
  })

  it('hasLinkedVendor reflects linked_vendor_count', () => {
    expect(hasLinkedVendor(evaluation({ linked_vendor_count: 0 }))).toBe(false)
    expect(hasLinkedVendor(evaluation({ linked_vendor_count: 2 }))).toBe(true)
  })

  it('reports one reason per unmet precondition, in order', () => {
    const reasons = startCollectionPreconditionReasons(evaluation({}))
    expect(reasons).toHaveLength(4)
    expect(reasons[0]).toContain('funcionales')
    expect(reasons[1]).toContain('técnicos')
    expect(reasons[2]).toContain('proveedor')
    expect(reasons[3]).toContain('aprobada')
  })

  it('isReadyToStartCollection is true only once every precondition is met, including approval', () => {
    const readyButNotApproved = evaluation({
      requirements: [
        requirement({ dimension: 'functional', weight: 40 }),
        requirement({ dimension: 'technical', weight: 20 }),
      ],
      linked_vendor_count: 1,
    })
    expect(startCollectionPreconditionReasons(readyButNotApproved)).toHaveLength(1)
    expect(isReadyToStartCollection(readyButNotApproved)).toBe(false)

    const ready = evaluation({ ...readyButNotApproved, approval_status: 'approved' })
    expect(startCollectionPreconditionReasons(ready)).toHaveLength(0)
    expect(isReadyToStartCollection(ready)).toBe(true)
  })

  it('requestApprovalPreconditionReasons requires approver and response_deadline too', () => {
    const readyWeightsAndVendor = evaluation({
      requirements: [
        requirement({ dimension: 'functional', weight: 40 }),
        requirement({ dimension: 'technical', weight: 20 }),
      ],
      linked_vendor_count: 1,
    })
    const reasons = requestApprovalPreconditionReasons(readyWeightsAndVendor)
    expect(reasons).toHaveLength(2)
    expect(isReadyToRequestApproval(readyWeightsAndVendor)).toBe(false)

    const ready = evaluation({
      ...readyWeightsAndVendor,
      approver_membership_id: 'approver-1',
      response_deadline: '2030-01-01T00:00:00Z',
    })
    expect(requestApprovalPreconditionReasons(ready)).toHaveLength(0)
    expect(isReadyToRequestApproval(ready)).toBe(true)
  })
})
