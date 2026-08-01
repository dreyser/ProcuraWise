import { ApiError } from '@/lib/http'
import { normalizeApiError, type NormalizedError } from '@/lib/errors'

/**
 * Generic implementation of ADR 0012's adaptive-polling contract - the
 * first real consumer of that ADR (Fase 13, ai). Framework-agnostic (plain
 * class + subscribe/notify, same shape as `AnswerAutosaveController`) so it
 * can be unit-tested with fake timers/dispatched DOM events without a
 * React render loop, and reused by any future async-job screen (reports in
 * Fase 23, etc.) without duplicating this logic.
 *
 * Contract implemented here (ADR 0012, "no es opcional parcial"):
 * - polls at `intervalMs` while a terminal state hasn't been reached
 * - pauses while the tab is hidden, polls immediately on refocus
 * - pauses while offline, polls immediately on reconnect
 * - exponential backoff + jitter on error, capped at `maxBackoffMs`
 * - respects a `Retry-After` header when present on a 429/503 ApiError
 * - flags `stale` past `staleWarningMs` without treating the job as failed
 * - always allows a manual `refreshNow()`, exposes `lastUpdatedAt`
 */

export type PollingStatus = 'idle' | 'polling' | 'paused' | 'stopped'

export interface PollingSnapshot<T> {
  status: PollingStatus
  result: T | null
  error: NormalizedError | null
  lastUpdatedAt: Date | null
  stale: boolean
}

export interface PollingControllerOptions<T> {
  intervalMs: number
  fetchFn: () => Promise<T>
  isTerminal: (result: T) => boolean
  maxBackoffMs?: number
  staleWarningMs?: number
}

const DEFAULT_MAX_BACKOFF_MS = 60_000
const DEFAULT_STALE_WARNING_MS = 15 * 60_000

function retryAfterMs(error: unknown): number | null {
  if (!(error instanceof ApiError) || !error.headers) return null
  const header = error.headers.get('Retry-After')
  if (!header) return null
  const seconds = Number(header)
  return Number.isFinite(seconds) ? seconds * 1000 : null
}

type Listener = () => void

export class PollingController<T> {
  private timer: ReturnType<typeof setTimeout> | null = null
  private status: PollingStatus = 'idle'
  private result: T | null = null
  private error: NormalizedError | null = null
  private lastUpdatedAt: Date | null = null
  private stale = false
  private consecutiveErrors = 0
  private startedAt: number | null = null
  private isVisible: boolean
  private isOnline: boolean
  private disposed = false
  private listeners = new Set<Listener>()
  private readonly options: PollingControllerOptions<T>

  constructor(options: PollingControllerOptions<T>) {
    this.options = options
    this.isVisible = typeof document === 'undefined' || document.visibilityState !== 'hidden'
    this.isOnline = typeof navigator === 'undefined' || navigator.onLine
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', this.handleVisibilityChange)
    }
    if (typeof window !== 'undefined') {
      window.addEventListener('online', this.handleOnline)
      window.addEventListener('offline', this.handleOffline)
    }
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }

  private notify(): void {
    this.listeners.forEach((listener) => listener())
  }

  getSnapshot(): PollingSnapshot<T> {
    return {
      status: this.status,
      result: this.result,
      error: this.error,
      lastUpdatedAt: this.lastUpdatedAt,
      stale: this.stale,
    }
  }

  start(): void {
    if (this.disposed || this.status === 'stopped') return
    this.startedAt = Date.now()
    this.status = 'polling'
    void this.poll()
  }

  /** Cancels the pending timer and polls immediately - used for the "manual
   * refresh" affordance ADR 0012 requires, and internally on refocus/reconnect. */
  refreshNow(): void {
    if (this.disposed || this.status === 'stopped') return
    this.clearTimer()
    void this.poll()
  }

  dispose(): void {
    this.disposed = true
    this.clearTimer()
    if (typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', this.handleVisibilityChange)
    }
    if (typeof window !== 'undefined') {
      window.removeEventListener('online', this.handleOnline)
      window.removeEventListener('offline', this.handleOffline)
    }
    this.listeners.clear()
  }

  private clearTimer(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer)
      this.timer = null
    }
  }

  private handleVisibilityChange = (): void => {
    this.isVisible = document.visibilityState !== 'hidden'
    if (this.isVisible) {
      this.refreshNow()
    } else {
      this.clearTimer()
      this.notify()
    }
  }

  private handleOnline = (): void => {
    this.isOnline = true
    this.refreshNow()
  }

  private handleOffline = (): void => {
    this.isOnline = false
    this.clearTimer()
    this.notify()
  }

  private scheduleNext(delayMs: number): void {
    this.clearTimer()
    if (this.disposed || this.status === 'stopped') return
    if (!this.isVisible || !this.isOnline) {
      // Paused - handleVisibilityChange/handleOnline call refreshNow() when
      // the tab refocuses or the connection returns, no timer needed here.
      this.status = 'paused'
      this.notify()
      return
    }
    this.timer = setTimeout(() => void this.poll(), delayMs)
  }

  private async poll(): Promise<void> {
    if (this.disposed) return
    try {
      const result = await this.options.fetchFn()
      if (this.disposed) return
      this.result = result
      this.error = null
      this.consecutiveErrors = 0
      this.lastUpdatedAt = new Date()
      this.stale =
        this.startedAt !== null &&
        Date.now() - this.startedAt > (this.options.staleWarningMs ?? DEFAULT_STALE_WARNING_MS)

      if (this.options.isTerminal(result)) {
        this.status = 'stopped'
        this.clearTimer()
        this.notify()
        return
      }
      this.status = 'polling'
      this.notify()
      this.scheduleNext(this.options.intervalMs)
    } catch (rawError) {
      if (this.disposed) return
      this.error = normalizeApiError(rawError)
      this.consecutiveErrors += 1
      this.notify()

      const hint = retryAfterMs(rawError)
      const maxBackoff = this.options.maxBackoffMs ?? DEFAULT_MAX_BACKOFF_MS
      const exponential = Math.min(
        maxBackoff,
        this.options.intervalMs * 2 ** this.consecutiveErrors,
      )
      const withJitter = exponential * (0.5 + Math.random() * 0.5)
      this.scheduleNext(hint ?? withJitter)
    }
  }
}
