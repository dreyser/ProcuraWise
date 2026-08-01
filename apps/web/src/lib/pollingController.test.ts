import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PollingController } from '@/lib/pollingController'
import { ApiError } from '@/lib/http'

interface JobLike {
  status: 'queued' | 'running' | 'succeeded' | 'failed'
}

function isTerminal(job: JobLike): boolean {
  return job.status === 'succeeded' || job.status === 'failed'
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('PollingController', () => {
  it('polls immediately on start, then again after intervalMs while not terminal', async () => {
    const fetchFn = vi.fn().mockResolvedValue({ status: 'running' })
    const controller = new PollingController<JobLike>({
      intervalMs: 15_000,
      fetchFn,
      isTerminal,
    })

    controller.start()
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(1))
    expect(controller.getSnapshot().status).toBe('polling')

    await vi.advanceTimersByTimeAsync(15_000)
    expect(fetchFn).toHaveBeenCalledTimes(2)

    controller.dispose()
  })

  it('stops polling once the result is terminal', async () => {
    const fetchFn = vi.fn().mockResolvedValue({ status: 'succeeded' })
    const controller = new PollingController<JobLike>({ intervalMs: 15_000, fetchFn, isTerminal })

    controller.start()
    await vi.waitFor(() => expect(controller.getSnapshot().status).toBe('stopped'))

    await vi.advanceTimersByTimeAsync(60_000)
    expect(fetchFn).toHaveBeenCalledTimes(1)

    controller.dispose()
  })

  it('applies exponential backoff with jitter on repeated errors, capped at maxBackoffMs', async () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.5) // withJitter = exponential * 0.75, deterministic
    const fetchFn = vi.fn().mockRejectedValue(new Error('network down'))
    const controller = new PollingController<JobLike>({
      intervalMs: 1_000,
      fetchFn,
      isTerminal,
      maxBackoffMs: 10_000,
    })

    controller.start()
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(1))
    expect(controller.getSnapshot().error).not.toBeNull()

    // attempt 1 -> exponential = min(10000, 1000*2^1) = 2000, *0.75 = 1500
    await vi.advanceTimersByTimeAsync(1499)
    expect(fetchFn).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(fetchFn).toHaveBeenCalledTimes(2)

    // attempt 2 -> exponential = min(10000, 1000*2^2) = 4000, *0.75 = 3000
    await vi.advanceTimersByTimeAsync(2999)
    expect(fetchFn).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(1)
    expect(fetchFn).toHaveBeenCalledTimes(3)

    controller.dispose()
  })

  it('respects a Retry-After header instead of the computed backoff', async () => {
    const error = new ApiError(429, { detail: 'slow down' }, new Headers({ 'Retry-After': '5' }))
    const fetchFn = vi
      .fn()
      .mockRejectedValueOnce(error)
      .mockResolvedValueOnce({ status: 'succeeded' })
    const controller = new PollingController<JobLike>({ intervalMs: 15_000, fetchFn, isTerminal })

    controller.start()
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(1))

    await vi.advanceTimersByTimeAsync(4_999)
    expect(fetchFn).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(fetchFn).toHaveBeenCalledTimes(2)

    controller.dispose()
  })

  it('pauses while the tab is hidden and polls immediately on refocus', async () => {
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'hidden',
    })
    const fetchFn = vi.fn().mockResolvedValue({ status: 'running' })
    const controller = new PollingController<JobLike>({ intervalMs: 15_000, fetchFn, isTerminal })

    controller.start()
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(1))
    await vi.advanceTimersByTimeAsync(15_000)
    expect(controller.getSnapshot().status).toBe('paused')
    expect(fetchFn).toHaveBeenCalledTimes(1) // no second poll while hidden

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    })
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(2))

    controller.dispose()
  })

  it('pauses while offline and polls immediately on reconnect', async () => {
    const fetchFn = vi.fn().mockResolvedValue({ status: 'running' })
    const controller = new PollingController<JobLike>({ intervalMs: 15_000, fetchFn, isTerminal })

    controller.start()
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(1))

    window.dispatchEvent(new Event('offline'))
    await vi.advanceTimersByTimeAsync(15_000)
    expect(fetchFn).toHaveBeenCalledTimes(1)

    window.dispatchEvent(new Event('online'))
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(2))

    controller.dispose()
  })

  it('refreshNow() cancels the pending timer and polls immediately', async () => {
    const fetchFn = vi.fn().mockResolvedValue({ status: 'running' })
    const controller = new PollingController<JobLike>({ intervalMs: 15_000, fetchFn, isTerminal })

    controller.start()
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(1))

    controller.refreshNow()
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(2))

    controller.dispose()
  })

  it('flags stale past staleWarningMs without marking the job failed', async () => {
    const fetchFn = vi.fn().mockResolvedValue({ status: 'running' })
    const controller = new PollingController<JobLike>({
      intervalMs: 1_000,
      fetchFn,
      isTerminal,
      staleWarningMs: 5_000,
    })

    controller.start()
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(1))
    expect(controller.getSnapshot().stale).toBe(false)

    await vi.advanceTimersByTimeAsync(6_000)
    expect(controller.getSnapshot().stale).toBe(true)
    expect(controller.getSnapshot().result).toEqual({ status: 'running' })

    controller.dispose()
  })

  it('dispose() stops all future polling', async () => {
    const fetchFn = vi.fn().mockResolvedValue({ status: 'running' })
    const controller = new PollingController<JobLike>({ intervalMs: 15_000, fetchFn, isTerminal })

    controller.start()
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(1))

    controller.dispose()
    await vi.advanceTimersByTimeAsync(60_000)
    expect(fetchFn).toHaveBeenCalledTimes(1)
  })
})
