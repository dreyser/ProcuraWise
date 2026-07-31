import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey,
  getListProposalsApiV1EvaluationsEvaluationIdProposalsGetQueryKey,
  useLinkVendorApiV1EvaluationsEvaluationIdVendorsPost,
  useListProposalsApiV1EvaluationsEvaluationIdProposalsGet,
  useListVendorOrganizationsApiV1VendorOrganizationsGet,
  useUnlinkVendorApiV1EvaluationsEvaluationIdVendorsVendorOrgIdDelete,
  type EvaluationDetailResponse,
  type ProposalSummaryResponse,
  type VendorOrganizationListResponse,
} from '@/api/client'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { DisabledActionHint } from '@/components/DisabledActionHint'
import { EmptyState } from '@/components/EmptyState'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { translateProposalStatus } from '@/lib/enumLabels'
import { normalizeApiError } from '@/lib/errors'
import { unwrapData } from '@/lib/http'
import { VendorCatalogPicker } from '@/features/evaluations/components/VendorCatalogPicker'
import { hasLinkedVendor } from '@/features/evaluations/lib/evaluationReadiness'

const MAX_LINKED_VENDORS = 6

interface WizardStepVendorsProps {
  evaluation: EvaluationDetailResponse
  onChanged: () => void
  onBack: () => void
  onNext: () => void
}

/** Step 3. Same linking flow as `VendorsPage` (`VendorCatalogPicker` reused
 * as-is), without the start-collection action - that's step 4. */
export function WizardStepVendors({
  evaluation,
  onChanged,
  onBack,
  onNext,
}: WizardStepVendorsProps) {
  const queryClient = useQueryClient()

  const proposalsQuery = useListProposalsApiV1EvaluationsEvaluationIdProposalsGet(evaluation.id)
  const proposals = unwrapData<ProposalSummaryResponse[]>(proposalsQuery.data) ?? []

  // Same rationale as VendorsPage: an unfiltered, high-limit catalog page
  // used only to resolve names for already-linked vendors.
  const namesQuery = useListVendorOrganizationsApiV1VendorOrganizationsGet({ limit: 100 })
  const namesCatalog = unwrapData<VendorOrganizationListResponse>(namesQuery.data)
  const nameById = new Map((namesCatalog?.items ?? []).map((item) => [item.id, item.name]))

  const [pendingUnlink, setPendingUnlink] = useState<{ vendorOrgId: string; name: string } | null>(
    null,
  )
  const [linkingId, setLinkingId] = useState<string | null>(null)

  const invalidate = () => {
    onChanged()
    queryClient.invalidateQueries({
      queryKey: getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey(evaluation.id),
    })
    queryClient.invalidateQueries({
      queryKey: getListProposalsApiV1EvaluationsEvaluationIdProposalsGetQueryKey(evaluation.id),
    })
  }

  const linkVendor = useLinkVendorApiV1EvaluationsEvaluationIdVendorsPost({
    mutation: { onSuccess: invalidate },
  })
  const unlinkVendor = useUnlinkVendorApiV1EvaluationsEvaluationIdVendorsVendorOrgIdDelete({
    mutation: { onSuccess: invalidate },
  })

  const atCapacity = proposals.length >= MAX_LINKED_VENDORS
  const linkedVendorOrgIds = new Set(proposals.map((p) => p.vendor_org_id))
  const ready = hasLinkedVendor(evaluation)

  return (
    <div>
      <section>
        <h2 className="text-sm font-semibold text-foreground">
          Proveedores vinculados ({proposals.length} / {MAX_LINKED_VENDORS})
        </h2>

        {proposalsQuery.isLoading && <LoadingState label="Cargando proveedores vinculados…" />}
        {proposalsQuery.error && (
          <ErrorBanner message={normalizeApiError(proposalsQuery.error).message} />
        )}
        {!proposalsQuery.isLoading && proposals.length === 0 && (
          <div className="mt-2">
            <EmptyState title="Ningún proveedor vinculado todavía" />
          </div>
        )}
        {proposals.length > 0 && (
          <div className="mt-2 overflow-x-auto rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Proveedor</TableHead>
                  <TableHead>Estado de la propuesta</TableHead>
                  <TableHead>Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {proposals.map((proposal) => {
                  const name = nameById.get(proposal.vendor_org_id) ?? 'Proveedor'
                  return (
                    <TableRow key={proposal.id}>
                      <TableCell>{name}</TableCell>
                      <TableCell>{translateProposalStatus(proposal.status)}</TableCell>
                      <TableCell>
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          onClick={() =>
                            setPendingUnlink({ vendorOrgId: proposal.vendor_org_id, name })
                          }
                        >
                          Desvincular
                        </Button>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </section>

      <section className="mt-6 max-w-lg">
        <h2 className="text-sm font-semibold text-foreground">Vincular proveedor</h2>
        {atCapacity ? (
          <p className="mt-2 text-sm text-muted-foreground">
            Ya alcanzaste el máximo de {MAX_LINKED_VENDORS} proveedores vinculados.
          </p>
        ) : (
          <div className="mt-2">
            {linkVendor.isError && (
              <div className="mb-2">
                <ErrorBanner message={normalizeApiError(linkVendor.error).message} />
              </div>
            )}
            <VendorCatalogPicker
              excludedIds={linkedVendorOrgIds}
              isLinking={linkVendor.isPending}
              linkingId={linkingId}
              disabled={false}
              onSelect={(vendorOrgId) => {
                setLinkingId(vendorOrgId)
                linkVendor.mutate(
                  { evaluationId: evaluation.id, data: { vendor_org_id: vendorOrgId } },
                  { onSettled: () => setLinkingId(null) },
                )
              }}
            />
          </div>
        )}
      </section>

      <div className="mt-8 flex items-center gap-2">
        <Button type="button" variant="outline" onClick={onBack}>
          Atrás
        </Button>
        <Button type="button" disabled={!ready} onClick={onNext}>
          Siguiente
        </Button>
      </div>
      <DisabledActionHint reasons={ready ? [] : ['Debes vincular al menos un proveedor.']} />

      <ConfirmDialog
        open={pendingUnlink !== null}
        onOpenChange={(open) => !open && setPendingUnlink(null)}
        title="Desvincular proveedor"
        description={`${pendingUnlink?.name ?? 'Este proveedor'} dejará de estar vinculado a la evaluación.`}
        confirmLabel="Desvincular"
        variant="destructive"
        isPending={unlinkVendor.isPending}
        onConfirm={() => {
          if (!pendingUnlink) return
          unlinkVendor.mutate(
            { evaluationId: evaluation.id, vendorOrgId: pendingUnlink.vendorOrgId },
            { onSuccess: () => setPendingUnlink(null) },
          )
        }}
      />
    </div>
  )
}
