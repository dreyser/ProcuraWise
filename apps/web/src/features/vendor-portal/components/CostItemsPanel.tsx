import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  getGetProposalApiV1VendorPortalProposalsProposalIdGetQueryKey,
  getPreviewTcoApiV1VendorPortalProposalsProposalIdTcoPreviewGetQueryKey,
  useAddCostItemApiV1VendorPortalProposalsProposalIdCostItemsPost,
  usePreviewTcoApiV1VendorPortalProposalsProposalIdTcoPreviewGet,
  useRemoveCostItemApiV1VendorPortalProposalsProposalIdCostItemsCostItemIdDelete,
  type CostItemResponse,
  type CostItemWriteRequestCategory,
  type CostItemWriteRequestCostType,
  type CostItemWriteRequestCurrency,
  type TcoPreviewResponse,
  type VendorProposalDetailResponse,
} from '@/api/client'
import { unwrapData } from '@/lib/http'
import { normalizeApiError } from '@/lib/errors'
import { ErrorBanner } from '@/components/ErrorBanner'
import { EmptyState } from '@/components/EmptyState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { StatusBadge } from '@/components/StatusBadge'
import { translateCostCategory, translateCostItemStatus, translateCostType } from '@/lib/enumLabels'

interface CostItemsPanelProps {
  proposalId: string
  proposal: VendorProposalDetailResponse
  disabled: boolean
}

const CATEGORIES: CostItemWriteRequestCategory[] = [
  'initial',
  'recurring',
  'variable_extraordinary',
]
const COST_TYPES: CostItemWriteRequestCostType[] = ['one_time', 'recurring', 'variable']
const CURRENCIES: CostItemWriteRequestCurrency[] = ['MXN', 'USD']

interface DraftCostItem {
  concept: string
  category: CostItemWriteRequestCategory
  billingUnit: string
  quantity: string
  unitPrice: string
  currency: CostItemWriteRequestCurrency
  frequencyPerYear: string
  taxPct: string
  discountPct: string
  yearStart: string
  yearEnd: string
  annualIncrementPct: string
  costType: CostItemWriteRequestCostType
  notes: string
}

const emptyDraft: DraftCostItem = {
  concept: '',
  category: 'recurring',
  billingUnit: '',
  quantity: '1',
  unitPrice: '0',
  currency: 'MXN',
  frequencyPerYear: '1',
  taxPct: '0',
  discountPct: '0',
  yearStart: '1',
  yearEnd: '1',
  annualIncrementPct: '0',
  costType: 'recurring',
  notes: '',
}

/** Fase 19 (spec §8.2): vendor-authored cost capture, no buyer-defined
 * template (plan §6.A9) - free-form concept/category within the three fixed
 * categories. Reads/writes `proposal.cost_items` directly rather than
 * fetching its own list (unlike ProposalDocumentsPanel), since the parent
 * page already has the full VendorProposalDetailResponse loaded. */
export function CostItemsPanel({ proposalId, proposal, disabled }: CostItemsPanelProps) {
  const queryClient = useQueryClient()
  const [showAddForm, setShowAddForm] = useState(false)
  const [draft, setDraft] = useState<DraftCostItem>(emptyDraft)

  const proposalQueryKey = getGetProposalApiV1VendorPortalProposalsProposalIdGetQueryKey(proposalId)
  const previewQueryKey =
    getPreviewTcoApiV1VendorPortalProposalsProposalIdTcoPreviewGetQueryKey(proposalId)

  const invalidateAfterMutation = () => {
    queryClient.invalidateQueries({ queryKey: previewQueryKey })
  }

  const addCostItem = useAddCostItemApiV1VendorPortalProposalsProposalIdCostItemsPost({
    mutation: {
      onSuccess: (response) => {
        queryClient.setQueryData(proposalQueryKey, response)
        invalidateAfterMutation()
        setDraft(emptyDraft)
        setShowAddForm(false)
      },
    },
  })

  const removeCostItem =
    useRemoveCostItemApiV1VendorPortalProposalsProposalIdCostItemsCostItemIdDelete({
      mutation: {
        onSuccess: (response) => {
          queryClient.setQueryData(proposalQueryKey, response)
          invalidateAfterMutation()
        },
      },
    })

  const previewQuery = usePreviewTcoApiV1VendorPortalProposalsProposalIdTcoPreviewGet(proposalId, {
    query: { enabled: !disabled },
  })
  const preview = unwrapData<TcoPreviewResponse>(previewQuery.data)

  const handleAdd = () => {
    addCostItem.mutate({
      proposalId,
      data: {
        concept: draft.concept,
        category: draft.category,
        billing_unit: draft.billingUnit,
        quantity: draft.quantity,
        unit_price: draft.unitPrice,
        currency: draft.currency,
        frequency_per_year: draft.frequencyPerYear,
        tax_pct: draft.taxPct,
        discount_pct: draft.discountPct,
        year_start: Number(draft.yearStart),
        year_end: Number(draft.yearEnd),
        annual_increment_pct: draft.annualIncrementPct,
        cost_type: draft.costType,
        notes: draft.notes || null,
        expected_version: proposal.version,
      },
    })
  }

  const handleRemove = (item: CostItemResponse) => {
    removeCostItem.mutate({
      proposalId,
      costItemId: item.id,
      params: { expected_version: proposal.version },
    })
  }

  return (
    <div className="rounded-md border border-border p-4">
      <h2 className="text-sm font-semibold text-foreground">Costos (TCO)</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Captura las partidas de costo de tu propuesta - iniciales, recurrentes y variables.
      </p>

      {(addCostItem.isError || removeCostItem.isError) && (
        <div className="mt-3">
          <ErrorBanner
            message={normalizeApiError(addCostItem.error ?? removeCostItem.error).message}
          />
        </div>
      )}

      <div className="mt-4">
        {proposal.cost_items.length === 0 ? (
          <EmptyState title="Sin partidas" description="Aún no has capturado ningún costo." />
        ) : (
          <div className="overflow-x-auto rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Concepto</TableHead>
                  <TableHead>Categoría</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Cantidad</TableHead>
                  <TableHead>Precio unitario</TableHead>
                  <TableHead>Moneda</TableHead>
                  <TableHead>Años</TableHead>
                  {proposal.round > 0 && <TableHead>Estado</TableHead>}
                  {!disabled && <TableHead>Acciones</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {proposal.cost_items.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>{item.concept}</TableCell>
                    <TableCell>{translateCostCategory(item.category)}</TableCell>
                    <TableCell>{translateCostType(item.cost_type)}</TableCell>
                    <TableCell>{item.quantity}</TableCell>
                    <TableCell>{item.unit_price}</TableCell>
                    <TableCell>{item.currency}</TableCell>
                    <TableCell>
                      {item.year_start}–{item.year_end}
                    </TableCell>
                    {proposal.round > 0 && (
                      <TableCell>
                        <StatusBadge label={translateCostItemStatus(item.status)} />
                      </TableCell>
                    )}
                    {!disabled && (
                      <TableCell>
                        {item.status !== 'removed' && (
                          <Button
                            type="button"
                            variant="destructive"
                            size="sm"
                            disabled={removeCostItem.isPending}
                            onClick={() => handleRemove(item)}
                          >
                            Eliminar
                          </Button>
                        )}
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      <div className="mt-4">
        {previewQuery.isLoading && !disabled && <LoadingState label="Calculando TCO…" />}
        {previewQuery.error && (
          <ErrorBanner message={normalizeApiError(previewQuery.error).message} />
        )}
        {preview && (
          <p className="text-sm text-foreground" role="status">
            TCO estimado ({preview.horizon_years} año(s), {preview.base_currency}):{' '}
            <span className="font-semibold">{preview.grand_total}</span>
          </p>
        )}
      </div>

      {!disabled && (
        <div className="mt-4">
          {!showAddForm ? (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => setShowAddForm(true)}
            >
              Agregar partida de costo
            </Button>
          ) : (
            <div className="rounded-md border border-border p-3">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                  Concepto
                  <input
                    className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                    value={draft.concept}
                    onChange={(e) => setDraft({ ...draft, concept: e.target.value })}
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                  Categoría
                  <select
                    className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                    value={draft.category}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        category: e.target.value as CostItemWriteRequestCategory,
                      })
                    }
                  >
                    {CATEGORIES.map((c) => (
                      <option key={c} value={c}>
                        {translateCostCategory(c)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                  Tipo
                  <select
                    className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                    value={draft.costType}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        costType: e.target.value as CostItemWriteRequestCostType,
                      })
                    }
                  >
                    {COST_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {translateCostType(t)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                  Unidad de cobro
                  <input
                    className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                    value={draft.billingUnit}
                    onChange={(e) => setDraft({ ...draft, billingUnit: e.target.value })}
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                  Cantidad
                  <input
                    className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                    value={draft.quantity}
                    onChange={(e) => setDraft({ ...draft, quantity: e.target.value })}
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                  Precio unitario
                  <input
                    className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                    value={draft.unitPrice}
                    onChange={(e) => setDraft({ ...draft, unitPrice: e.target.value })}
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                  Moneda
                  <select
                    className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                    value={draft.currency}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        currency: e.target.value as CostItemWriteRequestCurrency,
                      })
                    }
                  >
                    {CURRENCIES.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                  Año inicio
                  <input
                    className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                    value={draft.yearStart}
                    onChange={(e) => setDraft({ ...draft, yearStart: e.target.value })}
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                  Año fin
                  <input
                    className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                    value={draft.yearEnd}
                    onChange={(e) => setDraft({ ...draft, yearEnd: e.target.value })}
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                  Incremento anual (%)
                  <input
                    className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                    value={draft.annualIncrementPct}
                    onChange={(e) => setDraft({ ...draft, annualIncrementPct: e.target.value })}
                  />
                </label>
              </div>
              <div className="mt-3 flex gap-2">
                <Button
                  type="button"
                  size="sm"
                  disabled={addCostItem.isPending || !draft.concept || !draft.billingUnit}
                  onClick={handleAdd}
                >
                  {addCostItem.isPending ? 'Guardando…' : 'Guardar partida'}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setShowAddForm(false)
                    setDraft(emptyDraft)
                  }}
                >
                  Cancelar
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
