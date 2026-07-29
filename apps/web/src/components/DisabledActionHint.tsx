/** Explains why a primary action is disabled, right next to it - never a
 * silently-disabled button (brief §23). */
export function DisabledActionHint({ reasons }: { reasons: string[] }) {
  if (reasons.length === 0) return null
  return (
    <ul className="mt-2 list-inside list-disc text-sm text-muted-foreground">
      {reasons.map((reason) => (
        <li key={reason}>{reason}</li>
      ))}
    </ul>
  )
}
