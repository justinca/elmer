import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { queryKeys } from "@/lib/queryKeys"
import { STALE_TIMES } from "@/lib/queryClient"
import { getHealth, getNodes, getOrchestratorStatus, getKnowledgeSources } from "@/lib/api"
import { mapStatus } from "@/lib/utils"
import { useDocumentTitle } from "@/hooks/useDocumentTitle"
import { PageHeader } from "@/components/PageHeader"
import { StatCard } from "@/components/StatCard"
import { NodeCard } from "@/components/NodeCard"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Server, Bot, Database, Radio, RefreshCw, Clock } from "lucide-react"
import { formatDistanceToNow } from "date-fns"
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartsTooltip, ResponsiveContainer,
} from "recharts"

interface HealthData {
  status: string
  service: string
  version: string
  uptime_seconds: number
}

interface NodeData {
  node_id: string
  name: string
  status: string
  host?: string
  port?: number
  last_seen?: string
  node_type?: string
  metadata?: Record<string, unknown>
}

interface EventItem {
  id: string
  timestamp: string
  source: string
  event_type: string
  data?: Record<string, unknown>
}

function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  if (days > 0) return `${days}d ${hours}h ${mins}m`
  if (hours > 0) return `${hours}h ${mins}m`
  return `${mins}m`
}

export default function SystemStatus() {
  useDocumentTitle("System Status")
  const queryClient = useQueryClient()

  const [uptimeHistory, setUptimeHistory] = useState<{ time: string; uptime: number }[]>([])

  const { data: health, isLoading: healthLoading } = useQuery({
    queryKey: queryKeys.health.core(),
    queryFn: async () => {
      const r = await getHealth()
      const h = r.data as HealthData
      setUptimeHistory((prev) => {
        const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
        return [...prev, { time: now, uptime: Math.round(h.uptime_seconds / 60) }].slice(-30)
      })
      return h
    },
    staleTime: STALE_TIMES.health,
    refetchInterval: 30_000,
  })

  const { data: nodes = [], isLoading: nodesLoading } = useQuery({
    queryKey: queryKeys.health.nodes(),
    queryFn: () => getNodes().then((r) => {
      const data = r.data
      return (data.nodes || data || []) as NodeData[]
    }),
    staleTime: STALE_TIMES.health,
    refetchInterval: 30_000,
  })

  const { data: orchestrator } = useQuery({
    queryKey: queryKeys.agents.orchestrator(),
    queryFn: () => getOrchestratorStatus().then((r) => r.data as Record<string, unknown>),
    staleTime: STALE_TIMES.agents,
    refetchInterval: 30_000,
  })

  const { data: knowledgeSources = 0 } = useQuery({
    queryKey: queryKeys.knowledge.sources(),
    queryFn: () =>
      getKnowledgeSources().then((r) => {
        const sources = r.data
        return Array.isArray(sources) ? sources.length : 0
      }),
    staleTime: STALE_TIMES.knowledge,
    refetchInterval: 60_000,
  })

  const loading = healthLoading || nodesLoading

  // Extract events from node metadata
  const events: EventItem[] = []
  for (const node of nodes) {
    if (node.metadata?.recent_events) {
      for (const evt of node.metadata.recent_events as EventItem[]) {
        events.push({ ...evt, source: node.name || node.node_id })
      }
    }
  }
  events.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
  const recentEvents = events.slice(0, 20)

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.health.all })
    queryClient.invalidateQueries({ queryKey: queryKeys.agents.orchestrator() })
    queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.sources() })
  }

  const healthyNodes = nodes.filter((n) => mapStatus(n.status) === "healthy").length
  const totalNodes = nodes.length

  return (
    <div className="space-y-6">
      <PageHeader
        title="System Status"
        description="Overview of all Elmer services and nodes"
        actions={
          <Button variant="outline" size="sm" onClick={handleRefresh}>
            <RefreshCw className="mr-2 h-4 w-4" /> Refresh
          </Button>
        }
      />

      {/* Summary Cards */}
      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24" />)}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Core Service"
            value={health?.status === "ok" || health?.status === "healthy" ? "Online" : health?.status ?? "Unknown"}
            icon={Server}
            subtitle={health ? `Uptime: ${formatUptime(health.uptime_seconds)}` : undefined}
          />
          <StatCard
            label="Orchestrator"
            value={orchestrator?.running ? "Running" : "Stopped"}
            icon={Bot}
            subtitle={orchestrator?.running ? "Processing triggers" : "Not active"}
          />
          <StatCard
            label="Nodes"
            value={`${healthyNodes}/${totalNodes}`}
            icon={Radio}
            subtitle={healthyNodes === totalNodes ? "All healthy" : `${totalNodes - healthyNodes} issue(s)`}
          />
          <StatCard
            label="Knowledge Sources"
            value={knowledgeSources}
            icon={Database}
            subtitle="Document sources indexed"
          />
        </div>
      )}

      {/* Node Grid */}
      <div>
        <h2 className="mb-3 text-lg font-semibold">Nodes</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {nodes.map((node) => (
            <NodeCard
              key={node.node_id}
              name={node.name || node.node_id}
              status={mapStatus(node.status)}
              ip={node.host ? `${node.host}${node.port ? `:${node.port}` : ""}` : undefined}
              uptime={node.last_seen ? `Seen ${formatDistanceToNow(new Date(node.last_seen), { addSuffix: true })}` : undefined}
              services={
                Array.isArray(node.metadata?.services)
                  ? (node.metadata.services as Array<{ name: string; status: string }>).map((s) => ({
                      name: s.name,
                      status: mapStatus(s.status),
                    }))
                  : [{ name: node.node_type || "service", status: mapStatus(node.status) }]
              }
            />
          ))}
          {nodes.length === 0 && !loading && (
            <p className="col-span-full text-sm text-muted-foreground">No nodes registered yet.</p>
          )}
        </div>
      </div>

      {/* Health Timeline */}
      {uptimeHistory.length > 1 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Uptime History</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={uptimeHistory}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="time" className="text-xs" tick={{ fill: "currentColor" }} />
                <YAxis className="text-xs" tick={{ fill: "currentColor" }} label={{ value: "min", angle: -90, position: "insideLeft" }} />
                <RechartsTooltip
                  contentStyle={{
                    backgroundColor: "hsl(var(--card))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "0.5rem",
                    color: "hsl(var(--card-foreground))",
                  }}
                />
                <Line type="monotone" dataKey="uptime" stroke="hsl(var(--primary))" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Recent Events */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent Events</CardTitle>
        </CardHeader>
        <CardContent>
          {recentEvents.length > 0 ? (
            <div className="space-y-2">
              {recentEvents.map((evt, i) => (
                <div key={evt.id || i} className="flex items-start gap-3 text-sm">
                  <Clock className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-xs">{evt.source}</Badge>
                      <span className="text-xs text-muted-foreground">
                        {formatDistanceToNow(new Date(evt.timestamp), { addSuffix: true })}
                      </span>
                    </div>
                    <p className="text-muted-foreground">{evt.event_type}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No recent events. Events will appear as system activity is detected.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
