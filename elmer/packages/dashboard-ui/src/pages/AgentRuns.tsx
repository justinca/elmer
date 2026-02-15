import { useState, useEffect, useCallback, useMemo } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { queryKeys } from "@/lib/queryKeys"
import { STALE_TIMES } from "@/lib/queryClient"
import { useDocumentTitle } from "@/hooks/useDocumentTitle"
import { toast } from "sonner"
import { getAgentRun, getAgents } from "@/lib/api"
import { PageHeader } from "@/components/PageHeader"
import { StatCard } from "@/components/StatCard"
import { TagBadge } from "@/components/TagBadge"
import { RunRow } from "@/components/agents/RunRow"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { PlayCircle, CheckCircle2, Timer, TrendingUp, RefreshCw, ChevronLeft, ChevronRight } from "lucide-react"
import { getAllRuns } from "@/lib/api"

interface RunSummary {
  id: number
  agent_name: string
  trigger_type: string
  status: string
  started_at: string | null
  completed_at: string | null
  duration_seconds: number | null
}

interface RunDetail {
  input_data?: Record<string, unknown>
  output_data?: Record<string, unknown>
  trigger_data?: Record<string, unknown>
  error?: string | null
}

const ALL_STATUSES = ["completed", "failed", "running", "pending", "timeout"]
const PAGE_SIZE = 20

function AgentRuns() {
  useDocumentTitle("Agent Runs")
  const queryClient = useQueryClient()

  const { data: runs = [], isLoading: loading } = useQuery({
    queryKey: queryKeys.agents.allRuns({ limit: 200 }),
    queryFn: () => getAllRuns({ limit: 200 }).then((r) => (r.data || []) as RunSummary[]),
    staleTime: STALE_TIMES.agents,
    refetchInterval: 15_000,
  })

  const { data: agentNames = [] } = useQuery({
    queryKey: queryKeys.agents.list(),
    queryFn: () =>
      getAgents().then((r) => {
        const agents = r.data || []
        return (agents.map((a: { name: string }) => a.name) as string[]).sort()
      }),
    staleTime: STALE_TIMES.agents,
    refetchInterval: 60_000,
  })

  // Filters
  const [agentFilter, setAgentFilter] = useState("all")
  const [statusFilter, setStatusFilter] = useState<string[]>([])
  const [page, setPage] = useState(0)

  // Expanded detail
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<RunDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  // Filtering
  const filtered = useMemo(() => {
    let list = runs
    if (agentFilter !== "all") list = list.filter((r) => r.agent_name === agentFilter)
    if (statusFilter.length > 0) list = list.filter((r) => statusFilter.includes(r.status))
    return list
  }, [runs, agentFilter, statusFilter])

  // Pagination
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)
  const paged = useMemo(
    () => filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE),
    [filtered, page],
  )

  // Reset page when filters change
  useEffect(() => {
    setPage(0)
  }, [agentFilter, statusFilter])

  // Stats
  const stats = useMemo(() => {
    const total = runs.length
    const succeeded = runs.filter((r) => r.status === "completed").length
    const withDuration = runs.filter((r) => r.duration_seconds != null)
    const avgDuration =
      withDuration.length > 0
        ? withDuration.reduce((s, r) => s + r.duration_seconds!, 0) / withDuration.length
        : 0
    const agentCounts: Record<string, number> = {}
    runs.forEach((r) => {
      agentCounts[r.agent_name] = (agentCounts[r.agent_name] || 0) + 1
    })
    const mostActive = Object.entries(agentCounts).sort((a, b) => b[1] - a[1])[0]
    return {
      total,
      successRate: total > 0 ? Math.round((succeeded / total) * 100) : 0,
      avgDuration: avgDuration.toFixed(1),
      mostActive: mostActive ? `${mostActive[0]} (${mostActive[1]})` : "None",
    }
  }, [runs])

  // Status distribution bar
  const distribution = useMemo(() => {
    if (runs.length === 0) return null
    const counts: Record<string, number> = {}
    runs.forEach((r) => {
      counts[r.status] = (counts[r.status] || 0) + 1
    })
    return {
      completed: ((counts.completed || 0) / runs.length) * 100,
      failed: ((counts.failed || 0) / runs.length) * 100,
      timeout: ((counts.timeout || 0) / runs.length) * 100,
      running: ((counts.running || 0) / runs.length) * 100,
      pending: ((counts.pending || 0) / runs.length) * 100,
    }
  }, [runs])

  // Expand handler
  const handleExpand = useCallback(
    async (runId: number) => {
      if (expandedId === runId) {
        setExpandedId(null)
        setDetail(null)
        return
      }
      setExpandedId(runId)
      setLoadingDetail(true)
      try {
        const res = await getAgentRun(runId)
        setDetail(res.data)
      } catch {
        toast.error("Failed to load run details")
        setExpandedId(null)
      } finally {
        setLoadingDetail(false)
      }
    },
    [expandedId],
  )

  const toggleStatus = (status: string) => {
    setStatusFilter((prev) =>
      prev.includes(status) ? prev.filter((s) => s !== status) : [...prev, status],
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Agent Runs"
        description="Execution history across all agents"
        actions={
          <Button variant="outline" size="sm" onClick={() => queryClient.invalidateQueries({ queryKey: queryKeys.agents.all })}>
            <RefreshCw className="mr-2 h-4 w-4" /> Refresh
          </Button>
        }
      />

      {/* Stats */}
      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-lg" />
          ))}
        </div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Total Runs" value={stats.total} icon={PlayCircle} />
            <StatCard label="Success Rate" value={`${stats.successRate}%`} icon={CheckCircle2} />
            <StatCard label="Avg Duration" value={`${stats.avgDuration}s`} icon={Timer} />
            <StatCard label="Most Active" value={stats.mostActive} icon={TrendingUp} />
          </div>

          {/* Distribution bar */}
          {distribution && (
            <Card>
              <CardContent className="p-4">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-medium text-muted-foreground w-20">Distribution</span>
                  <div className="flex h-3 flex-1 overflow-hidden rounded-full bg-muted">
                    {distribution.completed > 0 && (
                      <div
                        className="bg-emerald-500 transition-all"
                        style={{ width: `${distribution.completed}%` }}
                      />
                    )}
                    {distribution.failed > 0 && (
                      <div
                        className="bg-red-500 transition-all"
                        style={{ width: `${distribution.failed}%` }}
                      />
                    )}
                    {distribution.timeout > 0 && (
                      <div
                        className="bg-amber-500 transition-all"
                        style={{ width: `${distribution.timeout}%` }}
                      />
                    )}
                    {distribution.running > 0 && (
                      <div
                        className="bg-blue-500 transition-all"
                        style={{ width: `${distribution.running}%` }}
                      />
                    )}
                    {distribution.pending > 0 && (
                      <div
                        className="bg-gray-400 transition-all"
                        style={{ width: `${distribution.pending}%` }}
                      />
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap gap-3 mt-2">
                  <span className="flex items-center gap-1 text-xs">
                    <span className="h-2 w-2 rounded-full bg-emerald-500" /> Completed
                  </span>
                  <span className="flex items-center gap-1 text-xs">
                    <span className="h-2 w-2 rounded-full bg-red-500" /> Failed
                  </span>
                  <span className="flex items-center gap-1 text-xs">
                    <span className="h-2 w-2 rounded-full bg-amber-500" /> Timeout
                  </span>
                  <span className="flex items-center gap-1 text-xs">
                    <span className="h-2 w-2 rounded-full bg-blue-500" /> Running
                  </span>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {/* Filters */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <Select value={agentFilter} onValueChange={setAgentFilter}>
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="All agents" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Agents</SelectItem>
            {agentNames.map((n) => (
              <SelectItem key={n} value={n}>
                {n}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="flex flex-wrap gap-1">
          {ALL_STATUSES.map((s) => (
            <TagBadge
              key={s}
              tag={s}
              active={statusFilter.includes(s)}
              onClick={toggleStatus}
              size="sm"
            />
          ))}
        </div>
      </div>

      {/* Runs table */}
      <Card>
        <CardHeader className="pb-0">
          <CardTitle className="text-sm">
            {filtered.length} run{filtered.length !== 1 ? "s" : ""}
            {agentFilter !== "all" && ` for ${agentFilter}`}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-4 space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : paged.length === 0 ? (
            <div className="p-8 text-center text-sm text-muted-foreground">
              No runs match the current filters
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8" />
                  <TableHead>Agent</TableHead>
                  <TableHead>Trigger</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Duration</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paged.map((run) => (
                  <RunRow
                    key={run.id}
                    run={run}
                    expanded={expandedId === run.id}
                    onToggle={() => handleExpand(run.id)}
                    detail={expandedId === run.id ? detail : null}
                    loadingDetail={expandedId === run.id && loadingDetail}
                  />
                ))}
              </TableBody>
            </Table>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between border-t px-4 py-3">
              <span className="text-xs text-muted-foreground">
                Showing {page * PAGE_SIZE + 1}-{Math.min((page + 1) * PAGE_SIZE, filtered.length)} of{" "}
                {filtered.length}
              </span>
              <div className="flex gap-1">
                <Button
                  variant="outline"
                  size="icon"
                  className="h-7 w-7"
                  disabled={page === 0}
                  onClick={() => setPage((p) => p - 1)}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  className="h-7 w-7"
                  disabled={page >= totalPages - 1}
                  onClick={() => setPage((p) => p + 1)}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

export default AgentRuns
