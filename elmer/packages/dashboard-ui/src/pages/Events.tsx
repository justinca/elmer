import { useState, useMemo, useCallback } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { queryKeys } from "@/lib/queryKeys"
import { STALE_TIMES } from "@/lib/queryClient"
import { getNodes, getNodeHistory } from "@/lib/api"
import { useDocumentTitle } from "@/hooks/useDocumentTitle"
import { PageHeader } from "@/components/PageHeader"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Activity, RefreshCw } from "lucide-react"
import {
  ResponsiveContainer, PieChart, Pie, Cell, Tooltip as RTooltip,
} from "recharts"
import { formatDistanceToNow } from "date-fns"

interface NodeEvent {
  id: number
  timestamp: string
  source: string
  event_type: string
  data?: Record<string, unknown>
}

const PIE_COLORS = [
  "hsl(var(--primary))",
  "hsl(142 71% 45%)",
  "hsl(48 96% 53%)",
  "hsl(0 84% 60%)",
  "hsl(217 91% 60%)",
  "hsl(280 65% 60%)",
  "hsl(25 95% 53%)",
  "hsl(173 80% 40%)",
]

const TIME_RANGES = [
  { label: "1 hour", value: 1 },
  { label: "6 hours", value: 6 },
  { label: "24 hours", value: 24 },
  { label: "7 days", value: 168 },
]

function getSeverity(eventType: string): "info" | "warning" | "error" {
  const lower = eventType.toLowerCase()
  if (lower.includes("error") || lower.includes("fail") || lower.includes("down")) return "error"
  if (lower.includes("warn") || lower.includes("degrad") || lower.includes("timeout")) return "warning"
  return "info"
}

const severityColors = {
  info: "text-blue-500 border-blue-500/30",
  warning: "text-amber-500 border-amber-500/30",
  error: "text-red-500 border-red-500/30",
}

export default function Events() {
  useDocumentTitle("Events")
  const queryClient = useQueryClient()

  const [sourceFilter, setSourceFilter] = useState("all")
  const [typeFilter, setTypeFilter] = useState("")
  const [hours, setHours] = useState(24)

  const { data: nodesData } = useQuery({
    queryKey: queryKeys.health.nodes(),
    queryFn: () => getNodes().then((r) => r.data.nodes || r.data || []),
    staleTime: STALE_TIMES.health,
  })

  const nodeIds: string[] = useMemo(
    () => (nodesData || []).map((n: { node_id: string }) => n.node_id),
    [nodesData],
  )

  const fetchAllHistory = useCallback(async () => {
    if (nodeIds.length === 0) return []
    const ids = sourceFilter === "all" ? nodeIds : [sourceFilter]
    const results = await Promise.allSettled(
      ids.map((id) => getNodeHistory(id, hours)),
    )
    const events: NodeEvent[] = []
    results.forEach((r) => {
      if (r.status === "fulfilled") {
        const data = r.value.data
        const hist = data?.events || data?.history || data || []
        if (Array.isArray(hist)) events.push(...hist)
      }
    })
    events.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
    return events
  }, [nodeIds, sourceFilter, hours])

  const { data: events = [], isLoading } = useQuery({
    queryKey: queryKeys.health.allHistory(hours),
    queryFn: fetchAllHistory,
    enabled: nodeIds.length > 0,
    staleTime: 10_000,
    refetchInterval: 15_000,
  })

  const filtered = useMemo(() => {
    let result = events
    if (sourceFilter !== "all") {
      result = result.filter((e) => e.source === sourceFilter)
    }
    if (typeFilter.trim()) {
      const q = typeFilter.toLowerCase()
      result = result.filter((e) => e.event_type.toLowerCase().includes(q))
    }
    return result
  }, [events, sourceFilter, typeFilter])

  const typeChart = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const e of filtered) {
      counts[e.event_type] = (counts[e.event_type] || 0) + 1
    }
    return Object.entries(counts)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 8)
  }, [filtered])

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.health.all })
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Events"
        description="System event log and activity timeline"
        actions={
          <Button variant="outline" size="sm" onClick={handleRefresh}>
            <RefreshCw className="mr-2 h-4 w-4" /> Refresh
          </Button>
        }
      />

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <Select value={sourceFilter} onValueChange={setSourceFilter}>
          <SelectTrigger className="w-[160px] h-9">
            <SelectValue placeholder="Source" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Sources</SelectItem>
            {nodeIds.map((id) => (
              <SelectItem key={id} value={id}>
                {id}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Input
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          placeholder="Filter event type..."
          className="w-[200px] h-9"
        />

        <div className="flex gap-1">
          {TIME_RANGES.map((tr) => (
            <Button
              key={tr.value}
              variant={hours === tr.value ? "default" : "outline"}
              size="sm"
              className="h-8 text-xs"
              onClick={() => setHours(tr.value)}
            >
              {tr.label}
            </Button>
          ))}
        </div>

        <Badge variant="secondary" className="ml-auto text-xs">
          {filtered.length} events
        </Badge>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        {/* Event table */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Activity className="h-4 w-4" /> Event Log
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="p-4 space-y-2">
                {Array.from({ length: 8 }).map((_, i) => (
                  <Skeleton key={i} className="h-8" />
                ))}
              </div>
            ) : filtered.length === 0 ? (
              <div className="py-12 text-center text-sm text-muted-foreground">
                No events found for the selected filters
              </div>
            ) : (
              <ScrollArea className="h-[600px]">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">Time</TableHead>
                      <TableHead className="text-xs">Source</TableHead>
                      <TableHead className="text-xs">Event Type</TableHead>
                      <TableHead className="text-xs">Severity</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filtered.map((evt) => {
                      const severity = getSeverity(evt.event_type)
                      return (
                        <TableRow key={evt.id}>
                          <TableCell className="text-xs text-muted-foreground tabular-nums">
                            {formatDistanceToNow(new Date(evt.timestamp), { addSuffix: true })}
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline" className="text-xs">
                              {evt.source}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs font-mono">{evt.event_type}</TableCell>
                          <TableCell>
                            <Badge
                              variant="outline"
                              className={`text-xs ${severityColors[severity]}`}
                            >
                              {severity}
                            </Badge>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </ScrollArea>
            )}
          </CardContent>
        </Card>

        {/* Type distribution chart */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Event Type Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            {typeChart.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie
                    data={typeChart}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    label={({ name, percent }) =>
                      `${(name ?? "").length > 12 ? (name ?? "").slice(0, 12) + "..." : name} ${((percent ?? 0) * 100).toFixed(0)}%`
                    }
                    labelLine={false}
                    fontSize={9}
                  >
                    {typeChart.map((_, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <RTooltip
                    contentStyle={{
                      backgroundColor: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "8px",
                      fontSize: "12px",
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="py-8 text-center text-xs text-muted-foreground">
                No event data to chart
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
