import { Badge } from '@/components/ui/badge'
import { translatePriority } from '@/lib/enumLabels'

/** `priority=mandatory` and `required=true` are distinct concepts (brief
 * §18) - this badge only ever renders priority, never conflated with
 * required-to-answer. */
export function PriorityBadge({ priority }: { priority: string }) {
  const variant = priority === 'mandatory' ? 'secondary' : 'outline'
  return <Badge variant={variant}>{translatePriority(priority)}</Badge>
}
