import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'

interface ReopenProposalDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  vendorName: string
  onConfirm: (data: { reason: string; response_deadline: string }) => void
  isPending?: boolean
}

/** Fase 21 (FR-047, ADR 0013): reopening a submitted proposal for a single
 * negotiation round requires the owner to state a reason and a new response
 * deadline - unlike ConfirmDialog, this action needs form inputs, not just a
 * static confirmation. */
export function ReopenProposalDialog({
  open,
  onOpenChange,
  vendorName,
  onConfirm,
  isPending = false,
}: ReopenProposalDialogProps) {
  const [reason, setReason] = useState('')
  const [deadline, setDeadline] = useState('')

  const canConfirm = reason.trim().length > 0 && deadline.length > 0

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      setReason('')
      setDeadline('')
    }
    onOpenChange(nextOpen)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Reabrir propuesta de {vendorName}</DialogTitle>
          <DialogDescription>
            El proveedor podrá editar sus respuestas y costos en una nueva ronda de negociación.
            Esta acción queda auditada.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div>
            <Label htmlFor="reopen-proposal-reason">Motivo</Label>
            <Textarea
              id="reopen-proposal-reason"
              value={reason}
              disabled={isPending}
              onChange={(event) => setReason(event.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="reopen-proposal-deadline">Nueva fecha límite de respuesta</Label>
            <Input
              id="reopen-proposal-deadline"
              type="date"
              value={deadline}
              disabled={isPending}
              onChange={(event) => setDeadline(event.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)} disabled={isPending}>
            Cancelar
          </Button>
          <Button
            onClick={() =>
              onConfirm({
                reason: reason.trim(),
                response_deadline: new Date(`${deadline}T00:00:00Z`).toISOString(),
              })
            }
            disabled={isPending || !canConfirm}
          >
            {isPending ? 'Procesando…' : 'Reabrir propuesta'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
