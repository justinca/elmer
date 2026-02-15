import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { CheckCircle2, XCircle, Loader2, AlertTriangle, Clock } from "lucide-react"
import { formatDistanceToNow } from "date-fns"

interface ActivityItem {
  id: number
  agent_name: string
  trigger_type: string
  status: string
  started_at: string | null
  duration_seconds: number | null
}

interface ActivityFeedProps {
  items: ActivityItem[]
  maxItems?: number
  className?: string
}

const statusIcon: Record<string, { icon: typeof CheckCircle2; color: string; label: string }> = {
  completed: { icon: CheckCircle2, color: "text-emerald-500", label: "completed" },
  failed: { icon: XCircle, color: "text-destructive", label: "failed" },
  running: { icon: Loader2, color: "text-blue-500", label: "running" },
  timeout: { icon: AlertTriangle, color: "text-amber-500", label: "timeout" },
  pending: { icon: Clock, color: "text-muted-foreground", label: "pending" },
}

export function ActivityFeed({ items, maxItems = 50, className }: ActivityFeedProps) {
  const display = items.slice(0, maxItems)

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">Activity Feed</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <ScrollArea className="h-[400px]">
          <div className="space-y-0 px-4 pb-4">
            {display.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">No recent activity</p>
            ) : (
              display.map((item) => {
                const cfg = statusIcon[item.status] || statusIcon.pending
                const Icon = cfg.icon
                return (
                  <div
                    key={item.id}
                    className="flex items-center gap-3 py-2 border-b last:border-0"
                  >
                    <Icon
                      className={cn(
                        "h-4 w-4 shrink-0",
                        cfg.color,
                        item.status === "running" && "animate-spin",
                      )}
                    />
                    <div className="flex-1 min-w-0">
                      <span className="text-sm font-medium">{item.agent_name}</span>
                      <span className="text-sm text-muted-foreground">
                        {" "}
                        {cfg.label}
                        {item.duration_seconds != null && ` (${item.duration_seconds.toFixed(1)}s)`}
                      </span>
                    </div>
                    <Badge variant="outline" className="text-[10px] shrink-0 capitalize">
                      {item.trigger_type}
                    </Badge>
                    <span className="text-[10px] text-muted-foreground/60 shrink-0 w-20 text-right">
                      {item.started_at
                        ? formatDistanceToNow(new Date(item.started_at), { addSuffix: true })
                        : ""}
                    </span>
                  </div>
                )
              })
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}
