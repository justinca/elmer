import { useMemo } from "react"
import { useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { queryKeys } from "@/lib/queryKeys"
import { STALE_TIMES } from "@/lib/queryClient"
import { getNodes } from "@/lib/api"
import { Bell } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ScrollArea } from "@/components/ui/scroll-area"
import { formatDistanceToNow } from "date-fns"

interface EventItem {
  id: string
  timestamp: string
  source: string
  event_type: string
}

export function NotificationBell() {
  const navigate = useNavigate()

  const { data: nodesData } = useQuery({
    queryKey: queryKeys.health.nodes(),
    queryFn: () => getNodes().then((r) => r.data.nodes || r.data || []),
    staleTime: STALE_TIMES.health,
    refetchInterval: 30_000,
  })

  const events = useMemo(() => {
    const all: EventItem[] = []
    for (const node of nodesData || []) {
      if (node.metadata?.recent_events) {
        for (const evt of node.metadata.recent_events as EventItem[]) {
          all.push({ ...evt, source: node.name || node.node_id })
        }
      }
    }
    all.sort(
      (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
    )
    return all.slice(0, 15)
  }, [nodesData])

  // Track last seen count in localStorage
  const lastSeen = parseInt(localStorage.getItem("elmer-notif-seen") || "0", 10)
  const unread = Math.max(0, events.length - lastSeen)

  const handleOpen = (open: boolean) => {
    if (open) {
      localStorage.setItem("elmer-notif-seen", String(events.length))
    }
  }

  return (
    <DropdownMenu onOpenChange={handleOpen}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative h-8 w-8">
          <Bell className="h-4 w-4" />
          {unread > 0 && (
            <Badge
              className="absolute -right-1 -top-1 h-4 min-w-4 px-1 text-[10px] leading-none bg-blue-500 text-white border-0"
            >
              {unread}
            </Badge>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <div className="px-3 py-2 border-b">
          <p className="text-sm font-semibold">Notifications</p>
        </div>
        <ScrollArea className="max-h-[300px]">
          {events.length === 0 ? (
            <div className="px-3 py-6 text-center text-xs text-muted-foreground">
              No recent events
            </div>
          ) : (
            events.map((evt, i) => (
              <DropdownMenuItem
                key={evt.id || i}
                className="flex flex-col items-start gap-0.5 px-3 py-2 cursor-pointer"
                onClick={() => navigate("/events")}
              >
                <div className="flex items-center gap-2 w-full">
                  <Badge variant="outline" className="text-[10px] shrink-0">
                    {evt.source}
                  </Badge>
                  <span className="text-[10px] text-muted-foreground ml-auto">
                    {formatDistanceToNow(new Date(evt.timestamp), { addSuffix: true })}
                  </span>
                </div>
                <span className="text-xs text-muted-foreground">{evt.event_type}</span>
              </DropdownMenuItem>
            ))
          )}
        </ScrollArea>
        {events.length > 0 && (
          <div className="border-t px-3 py-2">
            <button
              onClick={() => navigate("/events")}
              className="text-xs text-primary hover:underline w-full text-center"
            >
              View all events
            </button>
          </div>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
