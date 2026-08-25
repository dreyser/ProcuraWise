import { describe, expect, it } from 'vitest'
import {
  economicCriterionGuidanceFor,
  translateAnswerStatus,
  translateApprovalStatus,
  translateCompliantStatus,
  translateCostItemStatus,
  translateDimension,
  translateEconomicCriterion,
  translateEvaluationStatus,
  translateNotificationEvent,
  translatePriority,
  translateProposalStatus,
  translateResponseType,
  translateReviewStatus,
  translateRole,
  translateScoringStatus,
} from '@/lib/enumLabels'

// Fase 20 (ADR 0009) - the 10 fixed commercial/risk criterion keys, matching
// evaluations.models.DEFAULT_COMMERCIAL_WEIGHTS/DEFAULT_RISK_WEIGHTS.
const ECONOMIC_CRITERION_KEYS = [
  'payment_terms',
  'price_protection',
  'contractual_flexibility',
  'discounts_incentives',
  'billing_transparency',
  'variable_cost_exposure',
  'increases_indexation',
  'assumptions_exclusions',
  'fx_fiscal_regulatory',
  'exit_portability_lockin',
]

describe('enumLabels translations', () => {
  it('translates every real EvaluationStatus wire value', () => {
    expect(translateEvaluationStatus('draft')).toBe('Borrador')
    expect(translateEvaluationStatus('collecting_responses')).toBe('Recibiendo propuestas')
    expect(translateEvaluationStatus('evaluating')).toBe('En evaluación')
    expect(translateEvaluationStatus('completed')).toBe('Completada')
  })

  it('translates every real ProposalStatus wire value', () => {
    expect(translateProposalStatus('draft')).toBe('Borrador')
    expect(translateProposalStatus('submitted')).toBe('Enviada')
  })

  it('translates dimension and priority', () => {
    expect(translateDimension('functional')).toBe('Funcional')
    expect(translateDimension('technical')).toBe('Técnico')
    expect(translatePriority('mandatory')).toBe('Obligatorio')
    expect(translatePriority('important')).toBe('Importante')
    expect(translatePriority('desirable')).toBe('Deseable')
  })

  it('translates every real compliant_status answer value', () => {
    expect(translateCompliantStatus('compliant')).toBe('Cumple')
    expect(translateCompliantStatus('partially_compliant')).toBe('Cumple parcialmente')
    expect(translateCompliantStatus('non_compliant')).toBe('No cumple')
  })

  it('translates role and scoring status', () => {
    expect(translateRole('evaluation_owner')).toBe('Responsable de evaluación')
    expect(translateRole('evaluator_functional')).toBe('Evaluador funcional')
    expect(translateRole('evaluator_technical')).toBe('Evaluador técnico')
    expect(translateRole('evaluator_economic')).toBe('Evaluador económico')
    expect(translateRole('internal_collaborator')).toBe('Colaborador interno')
    expect(translateRole('approver')).toBe('Aprobador')
    expect(translateRole('tenant_admin')).toBe('Administrador del cliente')
    expect(translateRole('vendor_contact')).toBe('Contacto de proveedor')
    expect(translateScoringStatus('incomplete')).toBe('Calificación incompleta')
    expect(translateScoringStatus('complete')).toBe('Calificación completa')
  })

  it('translates all 10 real response_type values without falling back', () => {
    const responseTypes = [
      'compliant_status',
      'text',
      'single_choice',
      'multi_choice',
      'number',
      'percentage',
      'date',
      'url',
      'comment',
      'currency',
    ]
    for (const type of responseTypes) {
      expect(translateResponseType(type)).not.toBe(type)
    }
  })

  it('translates every real approval_status wire value', () => {
    expect(translateApprovalStatus('not_requested')).toBe('Sin solicitar')
    expect(translateApprovalStatus('pending')).toBe('Aprobación pendiente')
    expect(translateApprovalStatus('approved')).toBe('Aprobada')
    expect(translateApprovalStatus('rejected')).toBe('Rechazada')
  })

  it('translates every real review_status wire value distinctly from approval (ADR 0026)', () => {
    expect(translateReviewStatus('not_requested')).toBe('Sin solicitar')
    expect(translateReviewStatus('pending')).toBe('Revisión pendiente')
    expect(translateReviewStatus('approved')).toBe('Aprobada')
    expect(translateReviewStatus('rejected')).toBe('Rechazada')
  })

  it('translates every real ProposalAnswer.status wire value (Fase 21)', () => {
    expect(translateAnswerStatus('inherited')).toBe('Heredada')
    expect(translateAnswerStatus('modified')).toBe('Modificada')
  })

  it('translates every real CostItem.status wire value (Fase 21)', () => {
    expect(translateCostItemStatus('inherited')).toBe('Heredado')
    expect(translateCostItemStatus('modified')).toBe('Modificado')
    expect(translateCostItemStatus('removed')).toBe('Eliminado')
  })

  it('translates all 8 wired NotificationEvent values (Fase 24, Bloqueante #1 Opcion A)', () => {
    const events = [
      'vendor_invited',
      'evaluation_published',
      'qna_question_received',
      'qna_answer_published',
      'proposal_submitted',
      'proposal_reopened',
      'approval_requested',
      'evaluation_completed',
    ]
    for (const event of events) {
      expect(translateNotificationEvent(event)).not.toBe(event)
    }
  })

  it('falls back to the raw value for an unknown enum (never throws)', () => {
    expect(translateEvaluationStatus('some_future_status')).toBe('some_future_status')
  })

  it('translates every fixed economic criterion and gives each one guidance text (UAT-18)', () => {
    for (const key of ECONOMIC_CRITERION_KEYS) {
      expect(translateEconomicCriterion(key)).not.toBe(key)
      const guidance = economicCriterionGuidanceFor(key)
      expect(guidance).toBeDefined()
      expect(guidance!.length).toBeGreaterThan(20)
    }
  })

  it('returns undefined guidance for an unknown criterion key (never throws)', () => {
    expect(economicCriterionGuidanceFor('some_future_criterion')).toBeUndefined()
  })
})
