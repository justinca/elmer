import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { Clock, Radio, Zap, Globe, Play, CheckCircle2, XCircle, AlertTriangle, Timer } from "lucide-react"
import { formatDistanceToNow } from "date-fns"

interface AgentTrigger {
  type: string
  cron?: string
  topic?: string
  event_type?: string
}

interface RunSummary {
  status: string
  started_at: string | null
  duration_seconds: number | null
}

interface AgentDef {
  name: string
  display_name: string
  description: string
  enabled: boolean
  triggers: AgentTrigger[]
  tools: Array<{ name: string }>
  output_channels: string[]
  model: string
}

interface AgentCardProps {
  agent: AgentDef
  lastRun?: RunSummary | null
  onToggleEnabled: (name: string, enabled: boolean) => void
  onRunNow: (name: string) => void
  onSelect: (name: string) => void
  className?: string
}

const triggerIcons: Record<string, { icon: typeof Clock; label: string }> = {
  schedule: { icon: Clock, label: "Schedule" },
  mqtt: { icon: Radio, label: "MQTT" },
  event: { icon: Zap, label: "Event" },
  api: { icon: Globe, label: "API" },
}

const statusConfig: Record<string, { color: string; icon: typeof CheckCircle2 }> = {
  completed: { color: "text-emerald-500", icon: CheckCircle2 },
  failed: { color: "text-destructive", icon: XCircle },
  timeout: { color: "text-amber-500", icon: AlertTriangle },
  running: { color: "text-blue-500", icon: Timer },
  pending: { color: "text-muted-foreground", icon: Timer },
}

export function AgentCard({ agent, lastRun, onToggleEnabled, onRunNow, onSelect, className }: AgentCardProps) {
  const triggerTypes = [...new Set(agent.triggers.map((t) => t.type))]

  return (
    <Card
      className={cn("cursor-pointer transition-colors hover:bg-accent/50", className)}
      onClick={() => onSelect(agent.name)}
    >
      <CardContent className="p-4 space-y-3">
        {/* Header: name + switch */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="font-semibold truncate">{agent.display_name || agent.name}</p>
            {agent.display_name && agent.display_name !== agent.name && (
              <p className="text-xs text-muted-foreground truncate">{agent.name}</p>
            )}
          </div>
          <Switch
            checked={agent.enabled}
            onCheckedChange={(checked) => onToggleEnabled(agent.name, checked)}
            onClick={(e) => e.stopPropagation()}
            className="shrink-0"
          />
        </div>

        {/* Description */}
        <p className="text-sm text-muted-foreground line-clamp-2">{agent.description || "No description"}</p>

        {/* Trigger icons */}
        <div className="flex items-center gap-1.5">
          {triggerTypes.map((type) => {
            const cfg = triggerIcons[type]
            if (!cfg) return null
            const Icon = cfg.icon
            return (
              <Tooltip key={type}>
                <TooltipTrigger asChild>
                  <div className="flex h-6 w-6 items-center justify-center rounded bg-muted">
                    <Icon className="h-3.5 w-3.5 text-muted-foreground" />
                  </div>
                </TooltipTrigger>
                <TooltipContent>{cfg.label} trigger</TooltipContent>
              </Tooltip>
            )
          })}
          <div className="flex-1" />
          <Badge variant={agent.enabled ? "default" : "secondary"} className="text-xs">
            {agent.enabled ? "Enabled" : "Disabled"}
          </Badge>
        </div>

        {/* Last run + Run Now */}
        <div className="flex items-center justify-between gap-2 pt-1 border-t">
          {lastRun ? (
            <div className="flex items-center gap-1.5 min-w-0">
              {(() => {
                const cfg = statusConfig[lastRun.status] || statusConfig.pending
                const Icon = cfg.icon
                return <Icon className={cn("h-3.5 w-3.5 shrink-0", cfg.color)} />
              })()}
              <span className="text-xs text-muted-foreground truncate">
                {lastRun.started_at
                  ? formatDistanceToNow(new Date(lastRun.started_at), { addSuffix: true })
                  : lastRun.status}
              </span>
            </div>
          ) : (
            <span className="text-xs text-muted-foreground">No runs yet</span>
          )}
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs shrink-0"
            onClick={(e) => {
              e.stopPropagation()
              onRunNow(agent.name)
            }}
          >
            <Play className="mr-1 h-3 w-3" /> Run
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
