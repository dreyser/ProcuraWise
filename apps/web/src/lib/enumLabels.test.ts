import { describe, expect, it } from 'vitest'
import {
  translateApprovalStatus,
  translateCompliantStatus,
  translateDimension,
  translateEvaluationStatus,
  translatePriority,
  translateProposalStatus,
  translateResponseType,
  translateRole,
  translateScoringStatus,
} from '@/lib/enumLabels'

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

  it('falls back to the raw value for an unknown enum (never throws)', () => {
    expect(translateEvaluationStatus('some_future_status')).toBe('some_future_status')
  })
})
