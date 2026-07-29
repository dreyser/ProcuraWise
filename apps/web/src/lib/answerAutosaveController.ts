import {
  updateAnswerApiV1VendorPortalProposalsProposalIdAnswersRequirementIdPut,
  type VendorProposalDetailResponse,
} from '@/api/client'
import { ApiError, unwrapDataOrThrow } from '@/lib/http'
import { normalizeApiError, type NormalizedError } from '@/lib/errors'

interface QueuedAnswer {
  value: unknown
  vendorComment?: string
}

export type AutosaveStatus = 'idle' | 'saving' | 'conflict'

type Listener = () => void

/**
 * `Proposal.version` is global to the whole proposal, not per-answer (brief
 * §20/§3) - two answer writes in flight at once would race for the same
 * version and produce a client-generated 409. This serializes writes to at
 * most one in flight at a time, per Proposal, outside React state (a plain
 * class driven by refs) so the queueing logic isn't at the mercy of stale
 * closures across renders.
 */
export class AnswerAutosaveController {
  readonly proposalId: string
  private version: number
  private queue = new Map<string, QueuedAnswer>()
  private saving = new Set<string>()
  private status: AutosaveStatus = 'idle'
  private fieldErrors = new Map<string, NormalizedError>()
  private processing = false
  private listeners = new Set<Listener>()
  private onDetail?: (response: {
    data: VendorProposalDetailResponse
    status: number
    headers: Headers
  }) => void

  constructor(
    proposalId: string,
    initialVersion: number,
    onDetail?: (response: {
      data: VendorProposalDetailResponse
      status: number
      headers: Headers
    }) => void,
  ) {
    this.proposalId = proposalId
    this.version = initialVersion
    this.onDetail = onDetail
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

  getStatus(): AutosaveStatus {
    return this.status
  }

  getCurrentVersion(): number {
    return this.version
  }

  getPendingCount(): number {
    return this.queue.size + this.saving.size
  }

  isFieldPending(requirementId: string): boolean {
    return this.queue.has(requirementId) || this.saving.has(requirementId)
  }

  getFieldError(requirementId: string): NormalizedError | undefined {
    return this.fieldErrors.get(requirementId)
  }

  /** Called after the caller reloads the proposal (e.g. from the conflict
   * dialog's "recargar") - resets to a clean, unconflicted state. */
  syncVersion(version: number): void {
    this.version = version
    this.status = 'idle'
    this.queue.clear()
    this.saving.clear()
    this.fieldErrors.clear()
    this.notify()
  }

  queueAnswer(requirementId: string, value: unknown, vendorComment?: string): void {
    if (this.status === 'conflict') return
    this.fieldErrors.delete(requirementId)
    this.queue.set(requirementId, { value, vendorComment })
    this.notify()
    void this.processNext()
  }

  private async processNext(): Promise<void> {
    if (this.processing || this.status === 'conflict') return
    const next = this.queue.entries().next()
    if (next.done) return

    const [requirementId, answer] = next.value
    this.processing = true
    this.queue.delete(requirementId)
    this.saving.add(requirementId)
    this.status = 'saving'
    this.notify()

    try {
      const response =
        await updateAnswerApiV1VendorPortalProposalsProposalIdAnswersRequirementIdPut(
          this.proposalId,
          requirementId,
          {
            value: answer.value,
            vendor_comment: answer.vendorComment,
            expected_version: this.version,
          },
        )
      const detail = unwrapDataOrThrow<VendorProposalDetailResponse>(response)
      this.version = detail.version
      this.saving.delete(requirementId)
      // Push the server's authoritative answers/version back into the
      // query cache - without this the UI would keep showing pre-save
      // values even though the write already succeeded.
      this.onDetail?.({ data: detail, status: response.status, headers: response.headers })
    } catch (error) {
      this.saving.delete(requirementId)
      if (error instanceof ApiError && error.status === 409) {
        this.status = 'conflict'
        this.queue.clear()
        this.saving.clear()
      } else {
        this.fieldErrors.set(requirementId, normalizeApiError(error))
      }
    }

    this.processing = false
    if (this.status !== 'conflict') {
      this.status = this.queue.size > 0 || this.saving.size > 0 ? 'saving' : 'idle'
    }
    this.notify()

    if (this.status !== 'conflict') {
      void this.processNext()
    }
  }
}
