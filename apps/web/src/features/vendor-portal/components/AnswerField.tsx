import { useState, type ChangeEvent, type ReactNode } from 'react'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { translateCompliantStatus } from '@/lib/enumLabels'
import {
  CURRENCY_CODES,
  currencySchema,
  dateSchema,
  numberSchema,
  percentageSchema,
  urlSchema,
} from '@/features/vendor-portal/responseTypeSchemas'
import type { VendorRequirementResponse } from '@/api/client'

const COMPLIANCE_VALUES = ['compliant', 'partially_compliant', 'non_compliant'] as const

interface CurrencyValue {
  amount: number
  currency_code: (typeof CURRENCY_CODES)[number]
}

interface AnswerFieldProps {
  requirement: VendorRequirementResponse
  value: unknown
  vendorComment: string | null
  onCommit: (value: unknown, vendorComment?: string) => void
  disabled: boolean
  readOnly: boolean
  error?: string
}

/** Exported for reuse by ScoringPage.tsx (Fase 28 defecto real): only
 * `response_type` was ever read from the requirement, so this takes that
 * string directly rather than a full requirement object - `RequirementResponse`
 * (buyer side) and `VendorRequirementResponse` (vendor side) are two
 * separately orval-generated types for what's the same backend enum, and a
 * plain string param sidesteps relying on their literal unions staying
 * structurally identical. */
export function formatReadOnlyValue(responseType: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return 'Sin responder'
  switch (responseType) {
    case 'compliant_status':
      return translateCompliantStatus(String(value))
    case 'multi_choice':
      return Array.isArray(value) ? value.join(', ') : String(value)
    case 'percentage':
      return `${value}%`
    case 'date':
      return new Date(String(value)).toLocaleDateString('es-MX')
    case 'currency': {
      const currency = value as CurrencyValue
      return `${currency.amount} ${currency.currency_code}`
    }
    default:
      return String(value)
  }
}

/** Registry-style renderer keyed by `response_type` (brief §19/§12): each
 * branch below owns its control, its client validation, and its read-only
 * rendering - the 10 values are the exhaustive, real backend enum.
 *
 * Every control keeps its own *local* draft state and updates it
 * optimistically on change/blur, independent of the `value` prop (which
 * only catches up once the autosave write round-trips and the query cache
 * is refreshed - see AnswerAutosaveController's onDetail callback). Without
 * this, a controlled radio/checkbox bound directly to `value` would visibly
 * "snap back" between the click and the server response.
 *
 * All local draft state is declared unconditionally up front (Rules of
 * Hooks) even though only one branch's state is ever read for a given
 * requirement - `response_type` is fixed for the lifetime of a mounted
 * instance (each requirement gets its own instance, keyed by id). */
export function AnswerField({
  requirement,
  value,
  vendorComment,
  onCommit,
  disabled,
  readOnly,
  error,
}: AnswerFieldProps) {
  const [comment, setComment] = useState(vendorComment ?? '')
  const [localError, setLocalError] = useState<string | null>(null)

  const [complianceDraft, setComplianceDraft] = useState(typeof value === 'string' ? value : '')
  const [choiceDraft, setChoiceDraft] = useState(typeof value === 'string' ? value : '')
  const [multiDraft, setMultiDraft] = useState<string[]>(
    Array.isArray(value) ? (value as string[]) : [],
  )
  const [textDraft, setTextDraft] = useState(typeof value === 'string' ? value : '')
  const [numberDraft, setNumberDraft] = useState(
    value === null || value === undefined ? '' : String(value),
  )
  const [percentageDraft, setPercentageDraft] = useState(
    value === null || value === undefined ? '' : String(value),
  )
  const [dateDraft, setDateDraft] = useState(typeof value === 'string' ? value : '')
  const [urlDraft, setUrlDraft] = useState(typeof value === 'string' ? value : '')
  const currencyValue = (value as CurrencyValue | null) ?? null
  const [amountDraft, setAmountDraft] = useState(currencyValue ? String(currencyValue.amount) : '')
  const [codeDraft, setCodeDraft] = useState<string>(currencyValue?.currency_code ?? 'MXN')

  const fieldId = `answer-${requirement.id}`
  const commentId = `${fieldId}-comment`
  // The requirement's own <h2> (VendorProposalDetailPage.tsx) is this
  // field's accessible name - `fieldset`/`legend` already gives the
  // radio/checkbox groups below a name of their own, but the bare
  // Textarea/Input controls (text, number, percentage, date, url,
  // currency) have no visible <label> anywhere (only their secondary
  // "Comentario" field does) - found by axe-core (Fase 26, checkA11y)
  // flagging a real `<textarea id="answer-...">` with no accessible name
  // at all.
  const titleId = `requirement-title-${requirement.id}`

  /** The comment textarea commits on its own blur, independent of the main
   * control - it must resend whatever the *current local draft* value is,
   * not the (possibly stale) `value` prop, or a value change still in
   * flight could be silently reverted by a same-requirement comment save
   * that lands after it (both write to the same queue slot, keyed by
   * requirement id). */
  const currentDraftValue = (): unknown => {
    switch (requirement.response_type) {
      case 'compliant_status':
        return complianceDraft || null
      case 'single_choice':
        return choiceDraft || null
      case 'multi_choice':
        return multiDraft.length > 0 ? multiDraft : null
      case 'text':
      case 'comment':
        return textDraft || null
      case 'number':
        return numberDraft === '' ? null : Number(numberDraft)
      case 'percentage':
        return percentageDraft === '' ? null : Number(percentageDraft)
      case 'date':
        return dateDraft || null
      case 'url':
        return urlDraft || null
      case 'currency':
        return amountDraft === '' ? null : { amount: Number(amountDraft), currency_code: codeDraft }
      default:
        return value
    }
  }

  const commitComment = () => onCommit(currentDraftValue(), comment.trim() || undefined)

  if (readOnly) {
    return (
      <div className="text-sm text-foreground">
        {requirement.response_type === 'url' && typeof value === 'string' && value ? (
          <a href={value} target="_blank" rel="noopener noreferrer" className="underline">
            {value}
          </a>
        ) : (
          <p>{formatReadOnlyValue(requirement.response_type, value)}</p>
        )}
        {vendorComment && (
          <p className="mt-1 text-xs text-muted-foreground">Comentario: {vendorComment}</p>
        )}
      </div>
    )
  }

  const options = requirement.options ?? []
  const showError = error ?? localError
  const errorId = showError ? `${fieldId}-error` : undefined

  const wrap = (control: ReactNode) => (
    <div>
      {control}
      {showError && (
        <p id={errorId} className="mt-1 text-sm text-destructive" role="alert">
          {showError}
        </p>
      )}
      <div className="mt-2">
        <Label htmlFor={commentId} className="text-xs text-muted-foreground">
          Comentario (opcional)
        </Label>
        <Textarea
          id={commentId}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          onBlur={commitComment}
          disabled={disabled}
          className="mt-1"
        />
      </div>
    </div>
  )

  switch (requirement.response_type) {
    case 'compliant_status':
      return wrap(
        <fieldset aria-describedby={errorId}>
          <legend className="sr-only">{requirement.title}</legend>
          <div className="flex gap-4">
            {COMPLIANCE_VALUES.map((option) => (
              <label key={option} className="flex items-center gap-1.5 text-sm">
                <input
                  type="radio"
                  name={fieldId}
                  value={option}
                  checked={complianceDraft === option}
                  disabled={disabled}
                  onChange={() => {
                    setComplianceDraft(option)
                    onCommit(option, comment.trim() || undefined)
                  }}
                />
                {translateCompliantStatus(option)}
              </label>
            ))}
          </div>
        </fieldset>,
      )

    case 'text':
    case 'comment':
      return wrap(
        <Textarea
          id={fieldId}
          aria-labelledby={titleId}
          value={textDraft}
          disabled={disabled}
          aria-describedby={errorId}
          onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setTextDraft(event.target.value)}
          onBlur={() => onCommit(textDraft || null, comment.trim() || undefined)}
        />,
      )

    case 'single_choice':
      return wrap(
        <fieldset aria-describedby={errorId}>
          <legend className="sr-only">{requirement.title}</legend>
          <div className="flex flex-col gap-1.5">
            {options.map((option) => (
              <label key={option} className="flex items-center gap-1.5 text-sm">
                <input
                  type="radio"
                  name={fieldId}
                  value={option}
                  checked={choiceDraft === option}
                  disabled={disabled}
                  onChange={() => {
                    setChoiceDraft(option)
                    onCommit(option, comment.trim() || undefined)
                  }}
                />
                {option}
              </label>
            ))}
          </div>
        </fieldset>,
      )

    case 'multi_choice':
      return wrap(
        <fieldset aria-describedby={errorId}>
          <legend className="sr-only">{requirement.title}</legend>
          <div className="flex flex-col gap-1.5">
            {options.map((option) => (
              <label key={option} className="flex items-center gap-1.5 text-sm">
                <input
                  type="checkbox"
                  value={option}
                  checked={multiDraft.includes(option)}
                  disabled={disabled}
                  onChange={(event) => {
                    const next = event.target.checked
                      ? [...multiDraft, option]
                      : multiDraft.filter((v) => v !== option)
                    setMultiDraft(next)
                    onCommit(next, comment.trim() || undefined)
                  }}
                />
                {option}
              </label>
            ))}
          </div>
        </fieldset>,
      )

    case 'number':
      return wrap(
        <Input
          id={fieldId}
          aria-labelledby={titleId}
          type="number"
          value={numberDraft}
          disabled={disabled}
          aria-invalid={Boolean(showError)}
          aria-describedby={errorId}
          onChange={(event) => setNumberDraft(event.target.value)}
          onBlur={() => {
            if (numberDraft === '') {
              onCommit(null, comment.trim() || undefined)
              return
            }
            const result = numberSchema.safeParse(numberDraft)
            if (!result.success) {
              setLocalError('Ingresa un número válido')
              return
            }
            setLocalError(null)
            onCommit(result.data, comment.trim() || undefined)
          }}
        />,
      )

    case 'percentage':
      return wrap(
        <div className="flex items-center gap-2">
          <Input
            id={fieldId}
            aria-labelledby={titleId}
            type="number"
            value={percentageDraft}
            disabled={disabled}
            aria-invalid={Boolean(showError)}
            aria-describedby={errorId}
            className="w-28"
            onChange={(event) => setPercentageDraft(event.target.value)}
            onBlur={() => {
              if (percentageDraft === '') {
                onCommit(null, comment.trim() || undefined)
                return
              }
              const result = percentageSchema.safeParse(percentageDraft)
              if (!result.success) {
                setLocalError(result.error.issues[0]?.message ?? 'Valor inválido')
                return
              }
              setLocalError(null)
              onCommit(result.data, comment.trim() || undefined)
            }}
          />
          <span className="text-sm text-muted-foreground">%</span>
        </div>,
      )

    case 'date':
      return wrap(
        <Input
          id={fieldId}
          aria-labelledby={titleId}
          type="date"
          value={dateDraft}
          disabled={disabled}
          aria-invalid={Boolean(showError)}
          aria-describedby={errorId}
          onChange={(event) => setDateDraft(event.target.value)}
          onBlur={() => {
            if (dateDraft === '') {
              onCommit(null, comment.trim() || undefined)
              return
            }
            const result = dateSchema.safeParse(dateDraft)
            if (!result.success) {
              setLocalError(result.error.issues[0]?.message ?? 'Fecha inválida')
              return
            }
            setLocalError(null)
            onCommit(dateDraft, comment.trim() || undefined)
          }}
        />,
      )

    case 'url':
      return wrap(
        <Input
          id={fieldId}
          aria-labelledby={titleId}
          type="url"
          placeholder="https://"
          value={urlDraft}
          disabled={disabled}
          aria-invalid={Boolean(showError)}
          aria-describedby={errorId}
          onChange={(event) => setUrlDraft(event.target.value)}
          onBlur={() => {
            if (urlDraft === '') {
              onCommit(null, comment.trim() || undefined)
              return
            }
            const result = urlSchema.safeParse(urlDraft)
            if (!result.success) {
              setLocalError(result.error.issues[0]?.message ?? 'URL inválida')
              return
            }
            setLocalError(null)
            onCommit(urlDraft, comment.trim() || undefined)
          }}
        />,
      )

    case 'currency': {
      const commitCurrency = (nextAmount: string, nextCode: string) => {
        if (nextAmount === '') {
          onCommit(null, comment.trim() || undefined)
          return
        }
        const result = currencySchema.safeParse({ amount: nextAmount, currency_code: nextCode })
        if (!result.success) {
          setLocalError(result.error.issues[0]?.message ?? 'Monto inválido')
          return
        }
        setLocalError(null)
        onCommit(result.data, comment.trim() || undefined)
      }

      return wrap(
        <div className="flex items-center gap-2">
          <Input
            id={fieldId}
            aria-labelledby={titleId}
            type="number"
            step="0.01"
            value={amountDraft}
            disabled={disabled}
            aria-invalid={Boolean(showError)}
            aria-describedby={errorId}
            className="w-32"
            onChange={(event) => setAmountDraft(event.target.value)}
            onBlur={() => commitCurrency(amountDraft, codeDraft)}
          />
          <select
            aria-label="Moneda"
            value={codeDraft}
            disabled={disabled}
            className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
            onChange={(event) => {
              setCodeDraft(event.target.value)
              commitCurrency(amountDraft, event.target.value)
            }}
          >
            {CURRENCY_CODES.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </div>,
      )
    }

    default:
      return null
  }
}
