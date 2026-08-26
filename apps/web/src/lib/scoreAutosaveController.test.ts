import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ScoreAutosaveController } from '@/lib/scoreAutosaveController'
import { ApiError } from '@/lib/http'

const upsertScoreMock = vi.fn()

vi.mock('@/api/client', () => ({
  upsertScoreApiV1EvaluationsEvaluationIdProposalsProposalIdScoresRequirementIdPut: (
    ...args: unknown[]
  ) => upsertScoreMock(...args),
}))

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function envelope(requirementId: string, version: number) {
  return {
    data: {
      id: `score-${requirementId}`,
      requirement_id: requirementId,
      dimension: 'functional',
      priority: 'important',
      requirement_weight: 40,
      score: 4,
      comment: null,
      weighted_points: 32,
      mandatory_alert: false,
      version,
      created_by_membership_id: 'owner-1',
      updated_by_membership_id: 'owner-1',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      source_ai_execution_id: null,
    },
    status: 200,
    headers: new Headers(),
  }
}

beforeEach(() => {
  upsertScoreMock.mockReset()
})

describe('ScoreAutosaveController', () => {
  it('sends the seeded version for that field and adopts the server-returned version', async () => {
    const first = deferred()
    upsertScoreMock.mockReturnValueOnce(first.promise)
    const onScoreSaved = vi.fn()
    const controller = new ScoreAutosaveController('eval-1', 'proposal-1', onScoreSaved)
    controller.seedVersionIfIdle('req-a', 1)

    controller.queueScore('req-a', 4, 'bien')
    expect(controller.getFieldStatus('req-a')).toBe('saving')
    expect(upsertScoreMock).toHaveBeenCalledWith('eval-1', 'proposal-1', 'req-a', {
      score: 4,
      comment: 'bien',
      version: 1,
      source_ai_execution_id: undefined,
    })

    first.resolve(envelope('req-a', 2))
    await first.promise
    await vi.waitFor(() => expect(controller.getFieldStatus('req-a')).toBe('idle'))

    expect(onScoreSaved).toHaveBeenCalledWith('req-a', envelope('req-a', 2).data)

    // A second write on the same field must use the server-returned
    // version, not the stale seeded one - sending 1 again would 409.
    const second = deferred()
    upsertScoreMock.mockReturnValueOnce(second.promise)
    controller.queueScore('req-a', 5, 'mejor')
    expect(upsertScoreMock).toHaveBeenNthCalledWith(2, 'eval-1', 'proposal-1', 'req-a', {
      score: 5,
      comment: 'mejor',
      version: 2,
      source_ai_execution_id: undefined,
    })
  })

  it('omits version on the first-ever write for a never-scored requirement', () => {
    const controller = new ScoreAutosaveController('eval-1', 'proposal-1')
    controller.queueScore('req-a', 3)

    expect(upsertScoreMock).toHaveBeenCalledWith('eval-1', 'proposal-1', 'req-a', {
      score: 3,
      comment: undefined,
      version: undefined,
      source_ai_execution_id: undefined,
    })
  })

  it('writes to two different requirements in parallel, not serialized', () => {
    const controller = new ScoreAutosaveController('eval-1', 'proposal-1')
    controller.seedVersionIfIdle('req-a', 1)
    controller.seedVersionIfIdle('req-b', 5)

    controller.queueScore('req-a', 4)
    controller.queueScore('req-b', 2)

    // Unlike AnswerAutosaveController (one shared Proposal.version, so
    // writes serialize), each requirement's Score has its own independent
    // version - both writes fire immediately, neither waits on the other.
    expect(upsertScoreMock).toHaveBeenCalledTimes(2)
    expect(controller.getFieldStatus('req-a')).toBe('saving')
    expect(controller.getFieldStatus('req-b')).toBe('saving')
  })

  it('a 409 on one field only conflicts that field - a sibling field keeps autosaving', async () => {
    const a = deferred()
    const b = deferred()
    upsertScoreMock.mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise)
    const controller = new ScoreAutosaveController('eval-1', 'proposal-1')
    controller.seedVersionIfIdle('req-a', 1)
    controller.seedVersionIfIdle('req-b', 1)

    controller.queueScore('req-a', 4)
    controller.queueScore('req-b', 2)

    a.reject(new ApiError(409, { detail: 'stale version' }))
    await vi.waitFor(() => expect(controller.getFieldStatus('req-a')).toBe('conflict'))
    expect(controller.getFieldStatus('req-b')).toBe('saving')

    b.resolve(envelope('req-b', 2))
    await vi.waitFor(() => expect(controller.getFieldStatus('req-b')).toBe('idle'))

    // The conflicted field ignores further autosave attempts until resolved.
    controller.queueScore('req-a', 5)
    expect(upsertScoreMock).toHaveBeenCalledTimes(2)
  })

  it('resolveConflict clears the conflict and adopts the fresh version', async () => {
    const first = deferred()
    upsertScoreMock.mockReturnValueOnce(first.promise)
    const controller = new ScoreAutosaveController('eval-1', 'proposal-1')
    controller.seedVersionIfIdle('req-a', 1)
    controller.queueScore('req-a', 4)
    first.reject(new ApiError(409, { detail: 'stale version' }))
    await vi.waitFor(() => expect(controller.getFieldStatus('req-a')).toBe('conflict'))

    controller.resolveConflict('req-a', 7)
    expect(controller.getFieldStatus('req-a')).toBe('idle')

    const second = deferred()
    upsertScoreMock.mockReturnValueOnce(second.promise)
    controller.queueScore('req-a', 3)
    expect(upsertScoreMock).toHaveBeenNthCalledWith(2, 'eval-1', 'proposal-1', 'req-a', {
      score: 3,
      comment: undefined,
      version: 7,
      source_ai_execution_id: undefined,
    })
  })

  it('records a field-level error on a non-409 failure without entering conflict', async () => {
    const first = deferred()
    upsertScoreMock.mockReturnValueOnce(first.promise)
    const controller = new ScoreAutosaveController('eval-1', 'proposal-1')

    controller.queueScore('req-a', 9)
    first.reject(new ApiError(400, { detail: 'score must be between 0 and 5' }))
    await vi.waitFor(() => expect(controller.getFieldStatus('req-a')).toBe('idle'))

    expect(controller.getFieldError('req-a')?.kind).toBe('business_rule')
  })

  it('seedVersionIfIdle never clobbers a field that is saving or conflicted', async () => {
    const first = deferred()
    upsertScoreMock.mockReturnValueOnce(first.promise)
    const controller = new ScoreAutosaveController('eval-1', 'proposal-1')
    controller.seedVersionIfIdle('req-a', 1)
    controller.queueScore('req-a', 4)

    // A page-wide refresh landing mid-flight must not overwrite the version
    // this in-flight write is using.
    controller.seedVersionIfIdle('req-a', 99)

    first.resolve(envelope('req-a', 2))
    await vi.waitFor(() => expect(controller.getFieldStatus('req-a')).toBe('idle'))

    const second = deferred()
    upsertScoreMock.mockReturnValueOnce(second.promise)
    controller.queueScore('req-a', 5)
    expect(upsertScoreMock).toHaveBeenNthCalledWith(2, 'eval-1', 'proposal-1', 'req-a', {
      score: 5,
      comment: undefined,
      version: 2,
      source_ai_execution_id: undefined,
    })
  })
})
