import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { StatusDot } from "./StatusDot"
import { cn } from "@/lib/utils"

interface NodeService {
  name: string
  status: "healthy" | "degraded" | "down" | "unknown"
}

interface NodeCardProps {
  name: string
  status: "healthy" | "degraded" | "down" | "unknown"
  services: NodeService[]
  uptime?: string
  ip?: string
  className?: string
}

export function NodeCard({ name, status, services, uptime, ip, className }: NodeCardProps) {
  return (
    <Card className={cn("transition-colors", className)}>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <div className="flex items-center gap-2">
          <StatusDot status={status} />
          <CardTitle className="text-base">{name}</CardTitle>
        </div>
        <Badge variant={status === "healthy" ? "default" : "destructive"} className="text-xs">
          {status}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        {ip && <p className="text-xs text-muted-foreground">{ip}</p>}
        {uptime && <p className="text-xs text-muted-foreground">Uptime: {uptime}</p>}
        <div className="space-y-1">
          {services.map((svc) => (
            <div key={svc.name} className="flex items-center justify-between text-sm">
              <span>{svc.name}</span>
              <StatusDot status={svc.status} size="sm" />
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
