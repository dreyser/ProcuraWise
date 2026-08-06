import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  getDownloadUrlApiV1EvaluationsEvaluationIdReportsReportIdDownloadUrlGet,
  getGetReadinessApiV1EvaluationsEvaluationIdReportsReadinessGetQueryKey,
  getListReportsApiV1EvaluationsEvaluationIdReportsGetQueryKey,
  useCreateReportApiV1EvaluationsEvaluationIdReportsPost,
  useGetEvaluationApiV1EvaluationsEvaluationIdGet,
  useGetReadinessApiV1EvaluationsEvaluationIdReportsReadinessGet,
  useListReportsApiV1EvaluationsEvaluationIdReportsGet,
  ReportCreateRequestReportType,
  type EvaluationDetailResponse,
  type ReportCreateRequestFormat,
  type ReportDownloadUrlResponse,
  type ReportReadinessResponse,
  type ReportResponse,
} from '@/api/client'
import { ApiError, unwrapData, unwrapDataOrThrow } from '@/lib/http'
import { useAuth } from '@/auth/AuthContext'
import { StatusBadge } from '@/components/StatusBadge'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  translateEvaluationStatus,
  translateReportFormat,
  translateReportStatus,
  translateReportType,
} from '@/lib/enumLabels'
import { normalizeApiError } from '@/lib/errors'
import { EvaluationTabNav } from '@/features/evaluations/components/EvaluationTabNav'
import { useReportJobStatus } from '@/features/reports/hooks/useReportJobStatus'

const REPORT_TYPES = Object.values(ReportCreateRequestReportType)

/** "Reportes" tab (Fase 23, ADR 0023, backlog criterio de aceptación:
 * "Cada reporte se genera como job asíncrono y sigue el contrato de
 * polling"). Generation is owner-only (mirrors DecisionPage's isOwner
 * gating); every buyer role can list/poll/download, same BUYER_READ_ROLES
 * group already used by ResultsPage/DecisionPage - no new data is exposed to
 * a role that couldn't already see it via those pages. */
export function ReportsPage() {
  const { evaluationId } = useParams<{ evaluationId: string }>()
  const { actor } = useAuth()
  const isOwner = actor?.role === 'evaluation_owner'
  const queryClient = useQueryClient()

  const evaluationQuery = useGetEvaluationApiV1EvaluationsEvaluationIdGet(evaluationId!)
  const evaluation = unwrapData<EvaluationDetailResponse>(evaluationQuery.data)

  const [selectedType, setSelectedType] = useState<ReportCreateRequestReportType>('rfp_document')
  const [selectedFormat, setSelectedFormat] = useState<ReportCreateRequestFormat | ''>('')
  const [reportId, setReportId] = useState<string | null>(null)
  const [downloadingId, setDownloadingId] = useState<string | null>(null)
  const [downloadError, setDownloadError] = useState<unknown>(null)

  const readinessQuery = useGetReadinessApiV1EvaluationsEvaluationIdReportsReadinessGet(
    evaluationId!,
    { report_type: selectedType },
    { query: { enabled: Boolean(evaluation) } },
  )
  const readiness = unwrapData<ReportReadinessResponse>(readinessQuery.data)
  const effectiveFormat = selectedFormat || readiness?.valid_formats[0] || ''

  const listQuery = useListReportsApiV1EvaluationsEvaluationIdReportsGet(evaluationId!, {
    query: { enabled: Boolean(evaluation) },
  })
  const reports = unwrapData<ReportResponse[]>(listQuery.data) ?? []

  const invalidateReports = () => {
    queryClient.invalidateQueries({
      queryKey: getListReportsApiV1EvaluationsEvaluationIdReportsGetQueryKey(evaluationId),
    })
    queryClient.invalidateQueries({
      queryKey: getGetReadinessApiV1EvaluationsEvaluationIdReportsReadinessGetQueryKey(
        evaluationId,
        { report_type: selectedType },
      ),
    })
  }

  const createReport = useCreateReportApiV1EvaluationsEvaluationIdReportsPost({
    mutation: {
      onSuccess: (response) => {
        setReportId(unwrapDataOrThrow<ReportResponse>(response).id)
      },
    },
  })

  const job = useReportJobStatus(evaluationId!, reportId)
  useEffect(() => {
    if (job?.result && (job.result.status === 'succeeded' || job.result.status === 'failed')) {
      invalidateReports()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.result?.status])

  const handleGenerate = () => {
    if (!effectiveFormat) return
    createReport.mutate(
      { evaluationId: evaluationId!, data: { report_type: selectedType, format: effectiveFormat } },
      { onSuccess: invalidateReports },
    )
  }

  const handleDownload = async (id: string) => {
    setDownloadError(null)
    setDownloadingId(id)
    try {
      const response =
        await getDownloadUrlApiV1EvaluationsEvaluationIdReportsReportIdDownloadUrlGet(
          evaluationId!,
          id,
        )
      const { url } = unwrapDataOrThrow<ReportDownloadUrlResponse>(response)
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch (error) {
      setDownloadError(error)
    } finally {
      setDownloadingId(null)
    }
  }

  if (evaluationQuery.isLoading) return <LoadingState label="Cargando reportes…" />
  if (evaluationQuery.error instanceof ApiError && evaluationQuery.error.status === 404) {
    return <ErrorBanner message="Esta evaluación no está disponible." />
  }
  if (evaluationQuery.error) {
    return <ErrorBanner message={normalizeApiError(evaluationQuery.error).message} />
  }
  if (!evaluation) return null

  const jobIsActive =
    reportId !== null && (job === null || job.status === 'polling' || job.status === 'paused')
  const jobFailed = reportId !== null && job?.result?.status === 'failed'
  const jobSucceeded = reportId !== null && job?.result?.status === 'succeeded'

  return (
    <div className="max-w-3xl">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-foreground">{evaluation.name}</h1>
        <StatusBadge label={translateEvaluationStatus(evaluation.status)} />
      </div>
      <EvaluationTabNav evaluationId={evaluation.id} />

      {isOwner && (
        <section className="mt-6">
          <h2 className="text-sm font-semibold text-foreground">Generar reporte</h2>
          <div className="mt-3 flex flex-col gap-3 sm:max-w-md">
            <div>
              <Label htmlFor="report-type-select">Tipo de reporte</Label>
              <Select
                value={selectedType}
                onValueChange={(value) => {
                  setSelectedType(value as ReportCreateRequestReportType)
                  setSelectedFormat('')
                }}
              >
                <SelectTrigger id="report-type-select" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {REPORT_TYPES.map((type) => (
                    <SelectItem key={type} value={type}>
                      {translateReportType(type)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {readiness && readiness.valid_formats.length > 1 && (
              <div>
                <Label htmlFor="report-format-select">Formato</Label>
                <Select
                  value={effectiveFormat || undefined}
                  onValueChange={(value) => setSelectedFormat(value as ReportCreateRequestFormat)}
                >
                  <SelectTrigger id="report-format-select" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {readiness.valid_formats.map((format) => (
                      <SelectItem key={format} value={format}>
                        {translateReportFormat(format)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {readiness && !readiness.can_generate && (
              <p className="text-xs text-muted-foreground">{readiness.reasons.join(' ')}</p>
            )}
            {createReport.isError && (
              <ErrorBanner message={normalizeApiError(createReport.error).message} />
            )}

            <Button
              type="button"
              className="self-start"
              disabled={
                !readiness?.can_generate ||
                !effectiveFormat ||
                createReport.isPending ||
                jobIsActive
              }
              onClick={handleGenerate}
            >
              {createReport.isPending ? 'Solicitando…' : 'Generar'}
            </Button>

            {jobIsActive && <LoadingState label="Generando reporte…" />}
            {jobFailed && (
              <ErrorBanner
                message={job?.result?.error ?? 'La generación falló. Intenta de nuevo.'}
              />
            )}
            {jobSucceeded && (
              <ErrorBanner
                variant="info"
                message="Reporte generado. Descárgalo desde la lista de abajo."
              />
            )}
          </div>
        </section>
      )}

      <section className="mt-6">
        <h2 className="text-sm font-semibold text-foreground">Reportes generados</h2>

        {Boolean(downloadError) && (
          <div className="mt-2">
            <ErrorBanner message={normalizeApiError(downloadError).message} />
          </div>
        )}

        <div className="mt-3">
          {listQuery.isLoading ? (
            <LoadingState label="Cargando reportes…" />
          ) : listQuery.error ? (
            <ErrorBanner message={normalizeApiError(listQuery.error).message} />
          ) : reports.length === 0 ? (
            <EmptyState
              title="Sin reportes"
              description="Todavía no se ha generado ningún reporte para esta evaluación."
            />
          ) : (
            <div className="overflow-x-auto rounded-md border border-border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Formato</TableHead>
                    <TableHead>Estado</TableHead>
                    <TableHead>Solicitado</TableHead>
                    <TableHead>Descargar</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {reports.map((report) => (
                    <TableRow key={report.id}>
                      <TableCell>{translateReportType(report.report_type)}</TableCell>
                      <TableCell>{translateReportFormat(report.format)}</TableCell>
                      <TableCell>
                        <StatusBadge label={translateReportStatus(report.status)} />
                      </TableCell>
                      <TableCell>{new Date(report.requested_at).toLocaleString()}</TableCell>
                      <TableCell>
                        {report.status === 'succeeded' ? (
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={downloadingId === report.id}
                            onClick={() => handleDownload(report.id)}
                          >
                            Descargar
                          </Button>
                        ) : (
                          '—'
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
