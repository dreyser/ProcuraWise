import {
  upsertScoreApiV1EvaluationsEvaluationIdProposalsProposalIdScoresRequirementIdPut,
  type ScoreResponse,
} from '@/api/client'
import { ApiError, unwrapDataOrThrow } from '@/lib/http'
import { normalizeApiError, type NormalizedError } from '@/lib/errors'

interface QueuedScore {
  score: number
  comment?: string
  sourceAiExecutionId?: string | null
}

export type FieldAutosaveStatus = 'idle' | 'saving' | 'conflict'

type Listener = () => void

/**
 * UAT-15 (R3): autosave for scoring, on the same "plain class driven by
 * refs, not React state" architecture as `AnswerAutosaveController` - but
 * NOT the same class. `Score.version` (scoring/models.py) is one counter
 * per (proposal_id, requirement_id), unlike `Proposal.version`, which is
 * one counter shared by every answer in the proposal. That difference
 * means a stale write to one requirement's score can never race a write to
 * a different requirement's score, so this controller serializes writes
 * per-field (one in flight at a time for a given requirementId) instead of
 * globally, and a 409 puts only that one field into "conflict" - every
 * other field keeps autosaving normally, unlike the vendor controller
 * where any 409 halts the whole queue.
 */
export class ScoreAutosaveController {
  readonly evaluationId: string
  readonly proposalId: string
  private versions = new Map<string, number | undefined>()
  private queue = new Map<string, QueuedScore>()
  private saving = new Set<string>()
  private conflicts = new Set<string>()
  private processing = new Set<string>()
  private fieldErrors = new Map<string, NormalizedError>()
  private listeners = new Set<Listener>()
  private onScoreSaved?: (requirementId: string, score: ScoreResponse) => void

  constructor(
    evaluationId: string,
    proposalId: string,
    onScoreSaved?: (requirementId: string, score: ScoreResponse) => void,
  ) {
    this.evaluationId = evaluationId
    this.proposalId = proposalId
    this.onScoreSaved = onScoreSaved
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

  getFieldStatus(requirementId: string): FieldAutosaveStatus {
    if (this.conflicts.has(requirementId)) return 'conflict'
    if (this.saving.has(requirementId) || this.queue.has(requirementId)) return 'saving'
    return 'idle'
  }

  getPendingCount(): number {
    return this.queue.size + this.saving.size
  }

  getFieldError(requirementId: string): NormalizedError | undefined {
    return this.fieldErrors.get(requirementId)
  }

  /** Seeds this field's known version from freshly-loaded server data -
   * only while the field is untouched (`idle`, no queued/in-flight write),
   * so a page-wide data refresh (e.g. another evaluator's write) never
   * clobbers the version this controller needs for a write already in
   * flight or about to be sent. Safe to call every render with every
   * requirement's current version; it is a no-op for any field this
   * controller is actively managing. */
  seedVersionIfIdle(requirementId: string, version: number): void {
    if (this.getFieldStatus(requirementId) !== 'idle') return
    this.versions.set(requirementId, version)
  }

  /** Called after the caller reloads results post-conflict (e.g. "Recargar"
   * on that one row) - clears the conflict and adopts the fresh version. */
  resolveConflict(requirementId: string, version: number | undefined): void {
    this.conflicts.delete(requirementId)
    this.fieldErrors.delete(requirementId)
    this.versions.set(requirementId, version)
    this.notify()
  }

  queueScore(
    requirementId: string,
    score: number,
    comment?: string,
    sourceAiExecutionId?: string | null,
  ): void {
    if (this.conflicts.has(requirementId)) return
    this.fieldErrors.delete(requirementId)
    this.queue.set(requirementId, { score, comment, sourceAiExecutionId })
    this.notify()
    void this.processNext(requirementId)
  }

  private async processNext(requirementId: string): Promise<void> {
    if (this.processing.has(requirementId) || this.conflicts.has(requirementId)) return
    const answer = this.queue.get(requirementId)
    if (answer === undefined) return

    this.processing.add(requirementId)
    this.queue.delete(requirementId)
    this.saving.add(requirementId)
    this.notify()

    try {
      const response =
        await upsertScoreApiV1EvaluationsEvaluationIdProposalsProposalIdScoresRequirementIdPut(
          this.evaluationId,
          this.proposalId,
          requirementId,
          {
            score: answer.score,
            comment: answer.comment,
            version: this.versions.get(requirementId),
            source_ai_execution_id: answer.sourceAiExecutionId ?? undefined,
          },
        )
      const saved = unwrapDataOrThrow<ScoreResponse>(response)
      this.versions.set(requirementId, saved.version)
      this.saving.delete(requirementId)
      this.onScoreSaved?.(requirementId, saved)
    } catch (error) {
      this.saving.delete(requirementId)
      if (error instanceof ApiError && error.status === 409) {
        this.conflicts.add(requirementId)
        this.queue.delete(requirementId)
      } else {
        this.fieldErrors.set(requirementId, normalizeApiError(error))
      }
    }

    this.processing.delete(requirementId)
    this.notify()

    if (!this.conflicts.has(requirementId)) {
      void this.processNext(requirementId)
    }
  }
}
