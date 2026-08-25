import { describe, expect, it } from 'vitest'
import { resolveNotificationTarget } from './notificationTarget'
import type { NotificationResponse } from '@/api/client'

function item(overrides: Partial<NotificationResponse> = {}): NotificationResponse {
  return {
    id: 'notif-1',
    event: 'evaluation_published',
    resource_type: 'evaluation',
    resource_id: 'eval-1',
    evaluation_id: 'eval-1',
    title: 't',
    body: 'b',
    created_at: '2026-01-01T00:00:00Z',
    read_at: null,
    ...overrides,
  }
}

describe('resolveNotificationTarget (UAT-13)', () => {
  it('links evaluation_published to the evaluation summary', () => {
    expect(resolveNotificationTarget(item({ event: 'evaluation_published' }), 'buyer')).toBe(
      '/evaluations/eval-1',
    )
  })

  it('routes approval_requested by resource_type - evaluation vs. decision', () => {
    expect(
      resolveNotificationTarget(
        item({ event: 'approval_requested', resource_type: 'evaluation' }),
        'buyer',
      ),
    ).toBe('/evaluations/eval-1/approval')
    expect(
      resolveNotificationTarget(
        item({ event: 'approval_requested', resource_type: 'decision', resource_id: 'dec-1' }),
        'buyer',
      ),
    ).toBe('/evaluations/eval-1/decision')
  })

  it('links review_requested to the approval tab (ADR 0026)', () => {
    expect(resolveNotificationTarget(item({ event: 'review_requested' }), 'buyer')).toBe(
      '/evaluations/eval-1/approval',
    )
  })

  it('links qna_question_received to the Q&A tab', () => {
    expect(resolveNotificationTarget(item({ event: 'qna_question_received' }), 'buyer')).toBe(
      '/evaluations/eval-1/qna',
    )
  })

  it('routes proposal_submitted/proposal_reopened differently per audience', () => {
    const submitted = item({
      event: 'proposal_submitted',
      resource_type: 'proposal',
      resource_id: 'proposal-9',
    })
    expect(resolveNotificationTarget(submitted, 'buyer')).toBe('/evaluations/eval-1/proposals')
    expect(resolveNotificationTarget(submitted, 'vendor')).toBe('/vendor/proposals/proposal-9')

    const reopened = item({
      event: 'proposal_reopened',
      resource_type: 'proposal',
      resource_id: 'proposal-9',
    })
    expect(resolveNotificationTarget(reopened, 'buyer')).toBe('/evaluations/eval-1/proposals')
    expect(resolveNotificationTarget(reopened, 'vendor')).toBe('/vendor/proposals/proposal-9')
  })

  it('links evaluation_completed to Resultados', () => {
    expect(resolveNotificationTarget(item({ event: 'evaluation_completed' }), 'buyer')).toBe(
      '/evaluations/eval-1/results',
    )
  })

  it('links payment_succeeded to /billing regardless of evaluation_id', () => {
    expect(
      resolveNotificationTarget(
        item({ event: 'payment_succeeded', evaluation_id: null, resource_type: 'purchase' }),
        'buyer',
      ),
    ).toBe('/billing')
  })

  it('never links vendor_invited - the recipient is not authenticated yet', () => {
    expect(
      resolveNotificationTarget(
        item({
          event: 'vendor_invited',
          evaluation_id: null,
          resource_type: 'vendor_organization',
        }),
        'vendor',
      ),
    ).toBeNull()
  })

  it('never links qna_answer_published - no vendor Q&A route exists to land on', () => {
    expect(resolveNotificationTarget(item({ event: 'qna_answer_published' }), 'vendor')).toBeNull()
  })

  it('returns null when evaluation_id is missing for an evaluation-scoped event', () => {
    expect(
      resolveNotificationTarget(
        item({ event: 'evaluation_published', evaluation_id: null }),
        'buyer',
      ),
    ).toBeNull()
  })
})
