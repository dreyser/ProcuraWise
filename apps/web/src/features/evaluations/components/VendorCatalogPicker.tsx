import { useState } from 'react'
import {
  useListVendorOrganizationsApiV1VendorOrganizationsGet,
  type VendorOrganizationListResponse,
} from '@/api/client'
import { ErrorBanner } from '@/components/ErrorBanner'
import { EmptyState } from '@/components/EmptyState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { normalizeApiError } from '@/lib/errors'
import { unwrapData } from '@/lib/http'

interface VendorCatalogPickerProps {
  excludedIds: Set<string>
  onSelect: (vendorOrgId: string) => void
  isLinking: boolean
  linkingId: string | null
  disabled: boolean
}

/** Catalog picker for "vincular proveedores" - backed by
 * GET /api/v1/vendor-organizations (search + cursor pagination). Already
 * vinculados vendors are excluded client-side by id. */
export function VendorCatalogPicker({
  excludedIds,
  onSelect,
  isLinking,
  linkingId,
  disabled,
}: VendorCatalogPickerProps) {
  const [search, setSearch] = useState('')
  const { data, isLoading, error } = useListVendorOrganizationsApiV1VendorOrganizationsGet({
    search: search.trim() || undefined,
    limit: 20,
  })

  const catalog = unwrapData<VendorOrganizationListResponse>(data)
  const items = (catalog?.items ?? []).filter((item) => !excludedIds.has(item.id))

  return (
    <div>
      <Label htmlFor="vendor-search">Buscar proveedor</Label>
      <Input
        id="vendor-search"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Nombre del proveedor"
        disabled={disabled}
      />

      <div className="mt-2">
        {isLoading && <LoadingState label="Buscando proveedores…" />}
        {error && <ErrorBanner message={normalizeApiError(error).message} />}
        {!isLoading && !error && items.length === 0 && (
          <EmptyState
            title="Sin proveedores disponibles"
            description={
              search
                ? 'No hay resultados para tu búsqueda.'
                : 'No hay proveedores en el catálogo del tenant.'
            }
          />
        )}
        {items.length > 0 && (
          <ul className="flex flex-col gap-2">
            {items.map((item) => (
              <li
                key={item.id}
                className="flex items-center justify-between rounded-md border border-border px-3 py-2"
              >
                <span className="text-sm text-foreground">{item.name}</span>
                <Button
                  type="button"
                  size="sm"
                  disabled={disabled || isLinking}
                  onClick={() => onSelect(item.id)}
                >
                  {isLinking && linkingId === item.id ? 'Vinculando…' : 'Vincular'}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
