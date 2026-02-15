import { useEffect, useState, useCallback } from "react"
import { PageHeader } from "@/components/PageHeader"
import { StatCard } from "@/components/StatCard"
import { NodeCard } from "@/components/NodeCard"
import { LoadingSpinner } from "@/components/LoadingSpinner"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { getHealth, getNodes, getOrchestratorStatus, getKnowledgeSources } from "@/lib/api"
import { Server, Bot, Database, Radio, RefreshCw, Clock } from "lucide-react"
import { formatDistanceToNow } from "date-fns"
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
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

function mapStatus(s: string): "healthy" | "degraded" | "down" | "unknown" {
  if (s === "healthy" || s === "online" || s === "ok") return "healthy"
  if (s === "degraded" || s === "warning") return "degraded"
  if (s === "down" || s === "offline" || s === "error") return "down"
  return "unknown"
}

export default function SystemStatus() {
  const [health, setHealth] = useState<HealthData | null>(null)
  const [nodes, setNodes] = useState<NodeData[]>([])
  const [orchestrator, setOrchestrator] = useState<Record<string, unknown> | null>(null)
  const [knowledgeSources, setKnowledgeSources] = useState<number>(0)
  const [events, setEvents] = useState<EventItem[]>([])
  const [uptimeHistory, setUptimeHistory] = useState<{ time: string; uptime: number }[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const fetchData = useCallback(async () => {
    try {
      const [healthRes, nodesRes, orchRes, knowledgeRes] = await Promise.allSettled([
        getHealth(),
        getNodes(),
        getOrchestratorStatus(),
        getKnowledgeSources(),
      ])

      if (healthRes.status === "fulfilled") {
        const h = healthRes.value.data
        setHealth(h)
        setUptimeHistory((prev) => {
          const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
          const next = [...prev, { time: now, uptime: Math.round(h.uptime_seconds / 60) }]
          return next.slice(-30)
        })
      }

      if (nodesRes.status === "fulfilled") {
        const data = nodesRes.value.data
        setNodes(data.nodes || data || [])
        // Extract events from node history if present
        const allEvents: EventItem[] = []
        for (const node of (data.nodes || data || [])) {
          if (node.metadata?.recent_events) {
            for (const evt of node.metadata.recent_events as EventItem[]) {
              allEvents.push({ ...evt, source: node.name || node.node_id })
            }
          }
        }
        if (allEvents.length > 0) {
          allEvents.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
          setEvents(allEvents.slice(0, 20))
        }
      }

      if (orchRes.status === "fulfilled") {
        setOrchestrator(orchRes.value.data)
      }

      if (knowledgeRes.status === "fulfilled") {
        const sources = knowledgeRes.value.data
        setKnowledgeSources(Array.isArray(sources) ? sources.length : 0)
      }
    } catch (err) {
      console.error("Failed to fetch system status:", err)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const id = setInterval(fetchData, 30000)
    return () => clearInterval(id)
  }, [fetchData])

  const handleRefresh = () => {
    setRefreshing(true)
    fetchData()
  }

  if (loading) return <LoadingSpinner label="Loading system status..." />

  const healthyNodes = nodes.filter((n) => mapStatus(n.status) === "healthy").length
  const totalNodes = nodes.length

  return (
    <div className="space-y-6">
      <PageHeader
        title="System Status"
        description="Overview of all Elmer services and nodes"
        actions={
          <Button variant="outline" size="sm" onClick={handleRefresh} disabled={refreshing}>
            <RefreshCw className={`mr-2 h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        }
      />

      {/* Summary Cards */}
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
          {nodes.length === 0 && (
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
                <Line
                  type="monotone"
                  dataKey="uptime"
                  stroke="hsl(var(--primary))"
                  strokeWidth={2}
                  dot={false}
                />
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
          {events.length > 0 ? (
            <div className="space-y-2">
              {events.map((evt, i) => (
                <div key={evt.id || i} className="flex items-start gap-3 text-sm">
                  <Clock className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-xs">
                        {evt.source}
                      </Badge>
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
