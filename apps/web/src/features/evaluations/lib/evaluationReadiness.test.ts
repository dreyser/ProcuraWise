import { describe, expect, it } from 'vitest'
import {
  hasCompleteWeights,
  hasLinkedVendor,
  isReadyToStartCollection,
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
    expect(reasons).toHaveLength(3)
    expect(reasons[0]).toContain('funcionales')
    expect(reasons[1]).toContain('técnicos')
    expect(reasons[2]).toContain('proveedor')
  })

  it('isReadyToStartCollection is true only once every precondition is met', () => {
    const ready = evaluation({
      requirements: [
        requirement({ dimension: 'functional', weight: 40 }),
        requirement({ dimension: 'technical', weight: 20 }),
      ],
      linked_vendor_count: 1,
    })
    expect(startCollectionPreconditionReasons(ready)).toHaveLength(0)
    expect(isReadyToStartCollection(ready)).toBe(true)
  })
})
