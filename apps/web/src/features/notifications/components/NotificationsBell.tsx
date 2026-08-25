import { Bell } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { type NotificationResponse } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { translateNotificationEvent } from '@/lib/enumLabels'
import {
  resolveNotificationTarget,
  type NotificationAudience,
} from '@/features/notifications/notificationTarget'

interface NotificationsBellProps {
  items: NotificationResponse[]
  unreadCount: number
  isLoading: boolean
  audience: NotificationAudience
  onMarkRead: (notificationId: string) => void
  onMarkAllRead: () => void
}

/**
 * Presentation-only dropdown shared by BuyerNotificationsBell/
 * VendorNotificationsBell (Fase 24 plan S5.5) - the last ~20 notifications
 * (server-side limit, notifications/repository.py::list_for_recipient),
 * with a "marcar todas" action.
 *
 * UAT-13 (R4): clicking an item now navigates to the relevant page (via
 * resolveNotificationTarget), in addition to marking it read - still no
 * dedicated /notifications page, the dropdown itself remains the only
 * "centro de notificaciones" surface (Fase 24, NFR-003's ≤50-concurrent-
 * users scale).
 */
export function NotificationsBell({
  items,
  unreadCount,
  isLoading,
  audience,
  onMarkRead,
  onMarkAllRead,
}: NotificationsBellProps) {
  const navigate = useNavigate()
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label={
            unreadCount > 0 ? `Notificaciones (${unreadCount} sin leer)` : 'Notificaciones'
          }
          className="relative"
        >
          <Bell className="size-4" />
          {unreadCount > 0 && (
            <Badge
              variant="destructive"
              className="absolute -top-1 -right-1 h-4 min-w-4 justify-center px-1 text-[10px]"
            >
              {unreadCount > 99 ? '99+' : unreadCount}
            </Badge>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <div className="flex items-center justify-between px-2 py-1.5">
          <DropdownMenuLabel className="p-0">Notificaciones</DropdownMenuLabel>
          {unreadCount > 0 && (
            <button
              type="button"
              onClick={onMarkAllRead}
              className="text-xs text-muted-foreground underline hover:text-foreground"
            >
              Marcar todas
            </button>
          )}
        </div>
        <DropdownMenuSeparator />
        {isLoading ? (
          <p className="px-2 py-4 text-center text-sm text-muted-foreground">Cargando…</p>
        ) : items.length === 0 ? (
          <p className="px-2 py-4 text-center text-sm text-muted-foreground">
            No tienes notificaciones
          </p>
        ) : (
          <div className="max-h-96 overflow-y-auto">
            {items.map((item) => {
              const target = resolveNotificationTarget(item, audience)
              return (
                <DropdownMenuItem
                  key={item.id}
                  onSelect={(event) => {
                    event.preventDefault()
                    if (!item.read_at) onMarkRead(item.id)
                    if (target) navigate(target)
                  }}
                  className="flex flex-col items-start gap-0.5 whitespace-normal"
                >
                  <div className="flex w-full items-center justify-between gap-2">
                    <span className="text-xs font-medium text-foreground">
                      {translateNotificationEvent(item.event)}
                    </span>
                    {!item.read_at && (
                      <span className="size-1.5 shrink-0 rounded-full bg-primary" />
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">{item.title}</p>
                </DropdownMenuItem>
              )
            })}
          </div>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
