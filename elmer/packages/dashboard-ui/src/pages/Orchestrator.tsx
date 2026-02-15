import { useState, useEffect } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { queryKeys } from "@/lib/queryKeys"
import { STALE_TIMES } from "@/lib/queryClient"
import { useDocumentTitle } from "@/hooks/useDocumentTitle"
import { toast } from "sonner"
import { cn } from "@/lib/utils"
import { getOrchestratorStatus, getScheduledJobs, getAllRuns, reloadOrchestrator } from "@/lib/api"
import { PageHeader } from "@/components/PageHeader"
import { StatCard } from "@/components/StatCard"
import { EmptyState } from "@/components/EmptyState"
import { ActivityFeed } from "@/components/agents/ActivityFeed"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Inbox, Zap, Bot, BarChart3, RefreshCw, AlertTriangle, Calendar, Loader2 } from "lucide-react"
import { format, formatDistanceToNow } from "date-fns"
import cronstrue from "cronstrue"

interface OrchestratorStatus {
  running: boolean
  agents_registered: number
  queue_size: number
  queue_capacity: number
  workers: number
  running_agents: Record<string, string> // run_id -> agent_name
  agents: string[]
  total_runs: number
  total_failures: number
  failure_counts: Record<string, number>
}

interface ScheduledJob {
  job_id: string
  agent_name: string
  cron: string | null
  interval_seconds: number | null
  next_run_time: string | null
}

interface RunSummary {
  id: number
  agent_name: string
  trigger_type: string
  status: string
  started_at: string | null
  duration_seconds: number | null
}

function describeCron(cron: string | null): string {
  if (!cron) return ""
  try {
    return cronstrue.toString(cron, { use24HourTimeFormat: true })
  } catch {
    return cron
  }
}

function Orchestrator() {
  useDocumentTitle("Orchestrator")
  const queryClient = useQueryClient()

  const [reloading, setReloading] = useState(false)

  const { data: status = null, isLoading: loadingStatus } = useQuery({
    queryKey: queryKeys.agents.orchestrator(),
    queryFn: () => getOrchestratorStatus().then((r) => r.data as OrchestratorStatus),
    staleTime: STALE_TIMES.orchestrator,
    refetchInterval: 10_000,
  })

  const { data: schedule = [] } = useQuery({
    queryKey: queryKeys.agents.schedule(),
    queryFn: () => getScheduledJobs().then((r) => (r.data || []) as ScheduledJob[]),
    staleTime: STALE_TIMES.orchestrator,
    refetchInterval: 10_000,
  })

  const { data: recentRuns = [] } = useQuery({
    queryKey: queryKeys.agents.allRuns({ limit: 20 }),
    queryFn: () => getAllRuns({ limit: 20 }).then((r) => (r.data || []) as RunSummary[]),
    staleTime: STALE_TIMES.orchestrator,
    refetchInterval: 10_000,
  })

  const loading = loadingStatus

  // Live duration counter
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  const handleReload = async () => {
    setReloading(true)
    try {
      const res = await reloadOrchestrator()
      toast.success(`Definitions reloaded: ${res.data.agents_registered ?? 0} agents`)
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.all })
    } catch {
      toast.error("Failed to reload orchestrator")
    } finally {
      setReloading(false)
    }
  }

  const runningEntries = status ? Object.entries(status.running_agents) : []
  const failureEntries = status
    ? Object.entries(status.failure_counts).filter(([, v]) => v > 0)
    : []
  const sortedSchedule = [...schedule]
    .filter((j) => j.next_run_time)
    .sort((a, b) => new Date(a.next_run_time!).getTime() - new Date(b.next_run_time!).getTime())
    .slice(0, 10)

  // Find started_at for a running run ID
  const getRunStartedAt = (runId: string): string | null => {
    const run = recentRuns.find((r) => r.id === Number(runId))
    return run?.started_at || null
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Orchestrator"
        description="Agent execution engine status"
        actions={
          <Button variant="outline" size="sm" onClick={handleReload} disabled={reloading}>
            <RefreshCw className={cn("mr-2 h-4 w-4", reloading && "animate-spin")} />
            Reload Definitions
          </Button>
        }
      />

      {/* Not running alert */}
      {status && !status.running && (
        <Card className="border-destructive">
          <CardContent className="flex items-center gap-3 p-4">
            <AlertTriangle className="h-5 w-5 text-destructive" />
            <div>
              <p className="font-semibold text-destructive">Orchestrator is not running</p>
              <p className="text-sm text-muted-foreground">
                The agent execution engine is stopped. Try reloading definitions.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Status cards */}
      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-lg" />
          ))}
        </div>
      ) : status ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Queue"
            value={`${status.queue_size} / ${status.queue_capacity}`}
            icon={Inbox}
            subtitle={`${status.workers} workers`}
          />
          <StatCard
            label="Running Now"
            value={runningEntries.length}
            icon={Zap}
          />
          <StatCard
            label="Agents"
            value={`${status.agents.length} / ${status.agents_registered}`}
            icon={Bot}
            subtitle="enabled / total"
          />
          <StatCard
            label="Total Runs"
            value={status.total_runs}
            icon={BarChart3}
            subtitle={`${status.total_failures} failures`}
          />
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Currently running */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold">Currently Running</CardTitle>
          </CardHeader>
          <CardContent>
            {runningEntries.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">No agents running</p>
            ) : (
              <div className="space-y-3">
                {runningEntries.map(([runId, agentName]) => {
                  const startedAt = getRunStartedAt(runId)
                  const durationSec = startedAt
                    ? Math.floor((now - new Date(startedAt).getTime()) / 1000)
                    : null
                  return (
                    <div
                      key={runId}
                      className="flex items-center justify-between rounded-md border p-3"
                    >
                      <div className="flex items-center gap-3">
                        <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                        <div>
                          <p className="text-sm font-medium">{agentName}</p>
                          <p className="text-xs text-muted-foreground">Run #{runId}</p>
                        </div>
                      </div>
                      {durationSec !== null && (
                        <Badge variant="outline" className="tabular-nums">
                          {durationSec < 60
                            ? `${durationSec}s`
                            : `${Math.floor(durationSec / 60)}m ${durationSec % 60}s`}
                        </Badge>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Upcoming schedule */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm font-semibold">
              <Calendar className="h-4 w-4" /> Upcoming Schedule
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {sortedSchedule.length === 0 ? (
              <EmptyState
                icon={Calendar}
                title="No scheduled jobs"
                description="Agents with schedule triggers will appear here"
                className="py-6"
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs">Agent</TableHead>
                    <TableHead className="text-xs">Schedule</TableHead>
                    <TableHead className="text-xs">Next Run</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sortedSchedule.map((job) => (
                    <TableRow key={job.job_id}>
                      <TableCell className="text-sm font-medium">{job.agent_name}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {job.cron
                          ? describeCron(job.cron)
                          : job.interval_seconds
                            ? `Every ${job.interval_seconds}s`
                            : "-"}
                      </TableCell>
                      <TableCell className="text-xs">
                        {job.next_run_time ? (
                          <span title={format(new Date(job.next_run_time), "PPpp")}>
                            {formatDistanceToNow(new Date(job.next_run_time), { addSuffix: true })}
                          </span>
                        ) : (
                          "-"
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Circuit breaker status */}
      {failureEntries.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm font-semibold">
              <AlertTriangle className="h-4 w-4 text-amber-500" /> Circuit Breaker Status
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {failureEntries.map(([agent, count]) => (
                <div
                  key={agent}
                  className="flex items-center justify-between rounded-md border p-2"
                >
                  <span className="text-sm font-medium">{agent}</span>
                  <Badge
                    variant="outline"
                    className={cn(
                      "text-xs",
                      count >= 5
                        ? "bg-destructive/10 text-destructive border-destructive/20"
                        : count >= 3
                          ? "bg-amber-500/10 text-amber-600 border-amber-500/20"
                          : "",
                    )}
                  >
                    {count} / 5 failures
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Activity feed */}
      <ActivityFeed items={recentRuns} />
    </div>
  )
}

export default Orchestrator
