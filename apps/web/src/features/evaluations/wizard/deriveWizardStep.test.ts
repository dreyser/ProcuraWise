import { describe, expect, it } from 'vitest'
import { deriveWizardStep } from './deriveWizardStep'
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

describe('deriveWizardStep', () => {
  it('lands on step 1 when the evaluation does not exist yet', () => {
    expect(deriveWizardStep(undefined)).toBe(1)
  })

  it('lands on step 2 when weights are incomplete', () => {
    expect(deriveWizardStep(evaluation({ requirements: [] }))).toBe(2)
    expect(
      deriveWizardStep(
        evaluation({ requirements: [requirement({ dimension: 'functional', weight: 40 })] }),
      ),
    ).toBe(2)
  })

  it('lands on step 3 when weights are complete but no vendor is linked', () => {
    const complete = evaluation({
      requirements: [
        requirement({ id: 'r1', dimension: 'functional', weight: 40 }),
        requirement({ id: 'r2', dimension: 'technical', weight: 20 }),
      ],
      linked_vendor_count: 0,
    })
    expect(deriveWizardStep(complete)).toBe(3)
  })

  it('lands on step 4 when weights are complete and at least one vendor is linked', () => {
    const ready = evaluation({
      requirements: [
        requirement({ id: 'r1', dimension: 'functional', weight: 40 }),
        requirement({ id: 'r2', dimension: 'technical', weight: 20 }),
      ],
      linked_vendor_count: 1,
    })
    expect(deriveWizardStep(ready)).toBe(4)
  })

  it('re-derives from state, not from having been on a later step before', () => {
    // Simulates removing a requirement that had pushed weights back below
    // target after the user had already reached step 3/4 - the derivation
    // must fall back to step 2, since there's nowhere else the data lives.
    const regressed = evaluation({
      requirements: [requirement({ dimension: 'functional', weight: 10 })],
      linked_vendor_count: 1,
    })
    expect(deriveWizardStep(regressed)).toBe(2)
  })
})
