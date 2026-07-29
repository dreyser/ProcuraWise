import { Badge } from '@/components/ui/badge'

/** Neutral status label - never a color that implies a decision/adjudication
 * (brief §22/§27): every status uses the same outline variant. */
export function StatusBadge({ label }: { label: string }) {
  return <Badge variant="outline">{label}</Badge>
}
