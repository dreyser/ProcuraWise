import { useState } from 'react'
import {
  getGetAgreementStatusApiV1VendorPortalAgreementsStatusGetQueryKey,
  useAcceptAgreementApiV1VendorPortalAgreementsAcceptPost,
  type AgreementStatusResponse,
} from '@/api/client'
import { useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { ErrorBanner } from '@/components/ErrorBanner'
import { normalizeApiError } from '@/lib/errors'

function AgreementSection({
  id,
  title,
  text,
  accepted,
  onAccept,
  isPending,
}: {
  id: string
  title: string
  text: string
  accepted: boolean
  onAccept: () => void
  isPending: boolean
}) {
  const [checked, setChecked] = useState(false)

  if (accepted) {
    return (
      <div className="rounded-md border border-border p-4">
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        <p className="mt-2 text-sm text-muted-foreground" role="status">
          ✓ Aceptado
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-md border border-border p-4">
      <h2 className="text-sm font-semibold text-foreground">{title}</h2>
      <p className="mt-2 max-h-48 overflow-y-auto whitespace-pre-line text-sm text-muted-foreground">
        {text}
      </p>
      <div className="mt-3 flex items-center gap-2">
        <Checkbox
          id={`${id}-checkbox`}
          checked={checked}
          onCheckedChange={(value) => setChecked(value === true)}
        />
        <Label htmlFor={`${id}-checkbox`} className="text-sm font-normal">
          He leído y acepto este documento.
        </Label>
      </div>
      <Button type="button" className="mt-3" disabled={!checked || isPending} onClick={onAccept}>
        {isPending ? 'Aceptando…' : 'Aceptar'}
      </Button>
    </div>
  )
}

/**
 * Fase 15 backlog acceptance criterion: "Proveedor no accede al formulario
 * de respuesta sin aceptar ambos Agreement". Each type is accepted
 * independently, per-user (ADR 0014) - there is no "accept both at once"
 * shortcut, mirroring the backend gate which checks each type separately.
 */
export function AgreementAcceptanceScreen({ status }: { status: AgreementStatusResponse }) {
  const queryClient = useQueryClient()

  const invalidateStatus = () => {
    queryClient.invalidateQueries({
      queryKey: getGetAgreementStatusApiV1VendorPortalAgreementsStatusGetQueryKey(),
    })
  }

  const acceptNda = useAcceptAgreementApiV1VendorPortalAgreementsAcceptPost({
    mutation: { onSuccess: invalidateStatus },
  })
  const acceptConflictOfInterest = useAcceptAgreementApiV1VendorPortalAgreementsAcceptPost({
    mutation: { onSuccess: invalidateStatus },
  })

  return (
    <main className="mx-auto max-w-2xl p-8">
      <h1 className="text-lg font-semibold text-foreground">
        Antes de continuar, revisa y acepta estos documentos
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Necesitamos tu aceptación individual de ambos documentos antes de que puedas ver o responder
        propuestas.
      </p>

      <div className="mt-6 flex flex-col gap-4">
        {acceptNda.isError && <ErrorBanner message={normalizeApiError(acceptNda.error).message} />}
        <AgreementSection
          id="nda"
          title="Acuerdo de confidencialidad (NDA)"
          text={status.nda_text}
          accepted={status.nda_accepted}
          isPending={acceptNda.isPending}
          onAccept={() => acceptNda.mutate({ data: { type: 'nda' } })}
        />

        {acceptConflictOfInterest.isError && (
          <ErrorBanner message={normalizeApiError(acceptConflictOfInterest.error).message} />
        )}
        <AgreementSection
          id="conflict-of-interest"
          title="Declaración de conflicto de interés"
          text={status.conflict_of_interest_text}
          accepted={status.conflict_of_interest_accepted}
          isPending={acceptConflictOfInterest.isPending}
          onAccept={() =>
            acceptConflictOfInterest.mutate({ data: { type: 'conflict_of_interest' } })
          }
        />
      </div>
    </main>
  )
}
