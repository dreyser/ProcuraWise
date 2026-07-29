const SCORE_VALUES = [0, 1, 2, 3, 4, 5] as const

interface ScoreInputProps {
  requirementId: string
  value: number | null
  onChange: (value: number) => void
  disabled?: boolean
}

/** Segmented 0-5 control - deliberately not a free-text/number input, to
 * avoid fat-finger out-of-range values before the backend even validates
 * (brief §11). */
export function ScoreInput({ requirementId, value, onChange, disabled }: ScoreInputProps) {
  const groupId = `score-${requirementId}`
  return (
    <fieldset aria-label="Calificación de 0 a 5">
      <div id={groupId} className="flex gap-1.5">
        {SCORE_VALUES.map((option) => (
          <label
            key={option}
            className={`flex size-9 cursor-pointer items-center justify-center rounded-md border text-sm ${
              value === option
                ? 'border-foreground bg-foreground text-background'
                : 'border-border text-foreground hover:bg-muted'
            } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
          >
            <input
              type="radio"
              name={groupId}
              value={option}
              checked={value === option}
              disabled={disabled}
              onChange={() => onChange(option)}
              className="sr-only"
            />
            {option}
          </label>
        ))}
      </div>
    </fieldset>
  )
}
