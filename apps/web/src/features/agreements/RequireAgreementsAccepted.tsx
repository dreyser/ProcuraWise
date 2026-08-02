import { type ReactElement } from 'react'
import {
  useGetAgreementStatusApiV1VendorPortalAgreementsStatusGet,
  type AgreementStatusResponse,
} from '@/api/client'
import { unwrapData } from '@/lib/http'
import { LoadingState } from '@/components/LoadingState'
import { ErrorBanner } from '@/components/ErrorBanner'
import { normalizeApiError } from '@/lib/errors'
import { AgreementAcceptanceScreen } from '@/features/agreements/AgreementAcceptanceScreen'

/**
 * Fase 15: gates every vendor_portal route behind both Agreements having
 * been accepted by the current user (backlog acceptance criterion:
 * "Proveedor no accede al formulario de respuesta sin aceptar ambos
 * Agreement"). Wraps VendorLayout's children in app/router.tsx, so no
 * individual vendor-portal page needs to duplicate this check.
 */
export function RequireAgreementsAccepted({ children }: { children: ReactElement }) {
  const { data, isLoading, error } = useGetAgreementStatusApiV1VendorPortalAgreementsStatusGet()
  const status = unwrapData<AgreementStatusResponse>(data)

  if (isLoading) return <LoadingState label="Verificando acuerdos…" />
  if (error) {
    return (
      <main className="mx-auto max-w-md p-8">
        <ErrorBanner message={normalizeApiError(error).message} />
      </main>
    )
  }
  if (!status) return null

  if (!status.nda_accepted || !status.conflict_of_interest_accepted) {
    return <AgreementAcceptanceScreen status={status} />
  }

  return children
}
