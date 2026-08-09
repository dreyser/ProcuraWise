import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

interface CrossTenantReasonGateProps {
  /** null until the operator has typed and submitted a real reason - no
   * query fires until then (plan S5.6/S13.9: "no canned reason, no request
   * without a real motivo typed by the operator"). */
  confirmedReason: string | null
  onConfirm: (reason: string) => void
}

/**
 * Fase 25 (billing/admin, ADR 0025, plan Bloqueante #2 Opcion b): the UI
 * half of "acción admin cross-tenant queda auditada con motivo" - the
 * reason is never pre-filled, never a constant, and is echoed back once
 * confirmed so the operator sees exactly what was recorded in every
 * touched tenant's own audit trail (admin/service.py::AdminEvaluationService
 * / AdminPurchaseService, action=platform_admin_cross_tenant_read).
 */
export function CrossTenantReasonGate({ confirmedReason, onConfirm }: CrossTenantReasonGateProps) {
  const [draft, setDraft] = useState('')

  if (confirmedReason) {
    return (
      <p className="text-xs text-muted-foreground">
        Consultando con motivo: <strong>{confirmedReason}</strong> — registrado en la bitácora de
        cada organización consultada.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-3 sm:max-w-md">
      <div>
        <Label htmlFor="cross-tenant-reason">Motivo de la consulta</Label>
        <Input
          id="cross-tenant-reason"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="p. ej. auditoría de cumplimiento"
        />
      </div>
      <Button
        type="button"
        className="self-start"
        disabled={draft.trim().length < 3}
        onClick={() => onConfirm(draft.trim())}
      >
        Consultar
      </Button>
    </div>
  )
}
