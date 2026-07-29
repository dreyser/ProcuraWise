import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AnswerAutosaveController } from '@/lib/answerAutosaveController'
import { ApiError } from '@/lib/http'

const updateAnswerMock = vi.fn()

vi.mock('@/api/client', () => ({
  updateAnswerApiV1VendorPortalProposalsProposalIdAnswersRequirementIdPut: (...args: unknown[]) =>
    updateAnswerMock(...args),
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

function envelope(version: number) {
  return {
    data: { id: 'proposal-1', version, requirements: [], answers: [] },
    status: 200,
    headers: new Headers(),
  }
}

beforeEach(() => {
  updateAnswerMock.mockReset()
})

describe('AnswerAutosaveController', () => {
  it('sends the seeded version on the first write and adopts the server-returned version', async () => {
    const first = deferred()
    updateAnswerMock.mockReturnValueOnce(first.promise)
    const onDetail = vi.fn()
    const controller = new AnswerAutosaveController('proposal-1', 1, onDetail)

    controller.queueAnswer('req-a', 'compliant')
    expect(controller.getPendingCount()).toBe(1)
    expect(updateAnswerMock).toHaveBeenCalledWith('proposal-1', 'req-a', {
      value: 'compliant',
      vendor_comment: undefined,
      expected_version: 1,
    })

    first.resolve(envelope(2))
    await first.promise
    await vi.waitFor(() => expect(controller.getPendingCount()).toBe(0))

    expect(controller.getCurrentVersion()).toBe(2)
    expect(onDetail).toHaveBeenCalledWith(envelope(2))
  })

  it('serializes two rapid edits on different requirements - the second waits and uses the updated version', async () => {
    const first = deferred()
    const second = deferred()
    updateAnswerMock.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const controller = new AnswerAutosaveController('proposal-1', 1)

    controller.queueAnswer('req-a', 'compliant')
    controller.queueAnswer('req-b', 42)

    // Only the first write should have gone out - the second must wait.
    expect(updateAnswerMock).toHaveBeenCalledTimes(1)
    expect(controller.getPendingCount()).toBe(2)

    first.resolve(envelope(2))
    await first.promise
    await vi.waitFor(() => expect(updateAnswerMock).toHaveBeenCalledTimes(2))

    // The second write must use version 2 (from the first response), not the
    // stale seeded version 1 - sending 1 again would 409 against itself.
    expect(updateAnswerMock).toHaveBeenNthCalledWith(2, 'proposal-1', 'req-b', {
      value: 42,
      vendor_comment: undefined,
      expected_version: 2,
    })

    second.resolve(envelope(3))
    await second.promise
    await vi.waitFor(() => expect(controller.getPendingCount()).toBe(0))
    expect(controller.getCurrentVersion()).toBe(3)
  })

  it('enters conflict state on a 409, clears the queue, and never auto-retries', async () => {
    const first = deferred()
    updateAnswerMock.mockReturnValueOnce(first.promise)
    const controller = new AnswerAutosaveController('proposal-1', 1)

    controller.queueAnswer('req-a', 'compliant')
    controller.queueAnswer('req-b', 42) // queued behind req-a, never sent

    first.reject(new ApiError(409, { detail: 'stale version' }))
    await vi.waitFor(() => expect(controller.getStatus()).toBe('conflict'))

    expect(controller.getPendingCount()).toBe(0)
    expect(updateAnswerMock).toHaveBeenCalledTimes(1) // req-b was dropped, not retried

    // Further queueAnswer calls are ignored while in conflict, until the
    // caller reloads and calls syncVersion.
    controller.queueAnswer('req-c', 'text')
    expect(updateAnswerMock).toHaveBeenCalledTimes(1)
  })

  it('syncVersion resets a conflicted controller to a clean, idle state', async () => {
    const first = deferred()
    updateAnswerMock.mockReturnValueOnce(first.promise)
    const controller = new AnswerAutosaveController('proposal-1', 1)

    controller.queueAnswer('req-a', 'compliant')
    first.reject(new ApiError(409, { detail: 'stale version' }))
    await vi.waitFor(() => expect(controller.getStatus()).toBe('conflict'))

    controller.syncVersion(5)

    expect(controller.getStatus()).toBe('idle')
    expect(controller.getCurrentVersion()).toBe(5)
    expect(controller.getPendingCount()).toBe(0)
  })

  it('records a field-level error on a non-409 failure without entering conflict', async () => {
    const first = deferred()
    updateAnswerMock.mockReturnValueOnce(first.promise)
    const controller = new AnswerAutosaveController('proposal-1', 1)

    controller.queueAnswer('req-a', 'not-a-valid-option')
    first.reject(new ApiError(400, { detail: "value must be one of the requirement's options" }))
    await vi.waitFor(() => expect(controller.getPendingCount()).toBe(0))

    expect(controller.getStatus()).toBe('idle')
    expect(controller.getFieldError('req-a')?.kind).toBe('business_rule')
  })
})
