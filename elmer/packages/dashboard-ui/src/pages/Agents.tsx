import { useState, useCallback, useMemo } from "react"
import { useNavigate } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { queryKeys } from "@/lib/queryKeys"
import { STALE_TIMES } from "@/lib/queryClient"
import { useDocumentTitle } from "@/hooks/useDocumentTitle"
import { toast } from "sonner"
import { cn } from "@/lib/utils"
import {
  getAgents,
  getAllRuns,
  getAgentRuns,
  enableAgent,
  disableAgent,
  triggerAgent,
  deleteAgent,
} from "@/lib/api"
import { PageHeader } from "@/components/PageHeader"
import { SearchBar } from "@/components/SearchBar"
import { EmptyState } from "@/components/EmptyState"
import { ConfirmDialog } from "@/components/ConfirmDialog"
import { SlidePanel } from "@/components/SlidePanel"
import { TagBadge } from "@/components/TagBadge"
import { AgentCard } from "@/components/agents/AgentCard"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Plus, Bot, ChevronRight, Pencil, Trash2 } from "lucide-react"
import { formatDistanceToNow } from "date-fns"

interface AgentDef {
  name: string
  display_name: string
  description: string
  system_prompt: string
  model: string
  temperature: number | null
  enabled: boolean
  tools: Array<{ name: string; description?: string; config?: Record<string, unknown> }>
  triggers: Array<{
    type: string
    topic?: string
    cron?: string
    interval_seconds?: number
    event_type?: string
    payload_filter?: Record<string, unknown>
    config?: Record<string, unknown>
  }>
  output_channels: string[]
  max_concurrent: number
  timeout_seconds: number
  config?: Record<string, unknown>
  created_at?: string
  updated_at?: string
}

interface RunSummary {
  id: number
  agent_name: string
  trigger_type: string
  status: string
  started_at: string | null
  completed_at: string | null
  duration_seconds: number | null
}

const statusColors: Record<string, string> = {
  completed: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20",
  failed: "bg-destructive/10 text-destructive border-destructive/20",
  timeout: "bg-amber-500/10 text-amber-600 border-amber-500/20",
  running: "bg-blue-500/10 text-blue-600 border-blue-500/20",
  pending: "bg-muted text-muted-foreground",
}

function Agents() {
  useDocumentTitle("Agents")
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: agents = [], isLoading: loading } = useQuery({
    queryKey: queryKeys.agents.list(),
    queryFn: () => getAgents().then((r) => (r.data || []) as AgentDef[]),
    staleTime: STALE_TIMES.agents,
    refetchInterval: 60_000,
  })

  const { data: lastRuns = {} } = useQuery({
    queryKey: queryKeys.agents.allRuns({ limit: 50 }),
    queryFn: () =>
      getAllRuns({ limit: 50 }).then((r) => {
        const runs: RunSummary[] = r.data || []
        const map: Record<string, RunSummary> = {}
        for (const run of runs) {
          if (!map[run.agent_name]) map[run.agent_name] = run
        }
        return map
      }),
    staleTime: STALE_TIMES.agents,
    refetchInterval: 60_000,
  })

  const [searchQuery, setSearchQuery] = useState("")
  const [statusFilter, setStatusFilter] = useState("all")

  // Detail panel
  const [selectedAgent, setSelectedAgent] = useState<AgentDef | null>(null)
  const [selectedRuns, setSelectedRuns] = useState<RunSummary[]>([])
  const [panelOpen, setPanelOpen] = useState(false)
  const [promptOpen, setPromptOpen] = useState(false)

  // Delete
  const [deleteName, setDeleteName] = useState<string | null>(null)

  const filtered = useMemo(() => {
    let list = agents
    if (statusFilter === "enabled") list = list.filter((a) => a.enabled)
    if (statusFilter === "disabled") list = list.filter((a) => !a.enabled)
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      list = list.filter(
        (a) =>
          a.name.toLowerCase().includes(q) ||
          a.display_name.toLowerCase().includes(q) ||
          a.description.toLowerCase().includes(q),
      )
    }
    return list
  }, [agents, statusFilter, searchQuery])

  const handleToggleEnabled = useCallback(
    async (name: string, enabled: boolean) => {
      try {
        await (enabled ? enableAgent(name) : disableAgent(name))
        toast.success(`${name} ${enabled ? "enabled" : "disabled"}`)
        queryClient.invalidateQueries({ queryKey: queryKeys.agents.all })
      } catch {
        toast.error("Failed to toggle agent")
      }
    },
    [queryClient],
  )

  const handleRunNow = useCallback(
    async (name: string) => {
      try {
        await triggerAgent(name)
        toast.success(`${name} triggered`)
        setTimeout(() => queryClient.invalidateQueries({ queryKey: queryKeys.agents.all }), 2000)
      } catch {
        toast.error("Failed to trigger agent")
      }
    },
    [queryClient],
  )

  const handleSelect = useCallback(
    async (name: string) => {
      const agent = agents.find((a) => a.name === name)
      if (!agent) return
      setSelectedAgent(agent)
      setPanelOpen(true)
      try {
        const res = await getAgentRuns(name, 5)
        setSelectedRuns(res.data || [])
      } catch {
        setSelectedRuns([])
      }
    },
    [agents],
  )

  const handleDelete = useCallback(async () => {
    if (!deleteName) return
    try {
      await deleteAgent(deleteName)
      toast.success(`${deleteName} deleted`)
      setPanelOpen(false)
      setSelectedAgent(null)
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.all })
    } catch {
      toast.error("Failed to delete agent")
    } finally {
      setDeleteName(null)
    }
  }, [deleteName, queryClient])

  return (
    <div className="space-y-6">
      <PageHeader
        title="Agents"
        description="Manage autonomous agent definitions"
        actions={
          <Button onClick={() => navigate("/agents/builder")}>
            <Plus className="mr-2 h-4 w-4" /> Create Agent
          </Button>
        }
      />

      {/* Filters */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <SearchBar
          placeholder="Search agents..."
          onSearch={setSearchQuery}
          className="flex-1"
        />
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[150px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="enabled">Enabled</SelectItem>
            <SelectItem value="disabled">Disabled</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Agent grid */}
      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-44 rounded-lg" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={Bot}
          title="No agents found"
          description={searchQuery ? "Try a different search" : "Create your first agent to get started"}
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((agent) => (
            <AgentCard
              key={agent.name}
              agent={agent}
              lastRun={lastRuns[agent.name]}
              onToggleEnabled={handleToggleEnabled}
              onRunNow={handleRunNow}
              onSelect={handleSelect}
            />
          ))}
        </div>
      )}

      {/* Detail panel */}
      <SlidePanel
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        title={selectedAgent?.display_name || selectedAgent?.name || "Agent"}
      >
        {selectedAgent && (
          <div className="space-y-6">
            {/* Description */}
            <div>
              <p className="text-sm">{selectedAgent.description || "No description"}</p>
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
                <span>Model: {selectedAgent.model}</span>
                {selectedAgent.temperature != null && (
                  <span>Temp: {selectedAgent.temperature}</span>
                )}
                <span>Timeout: {selectedAgent.timeout_seconds}s</span>
                <span>Max concurrent: {selectedAgent.max_concurrent}</span>
              </div>
            </div>

            {/* System prompt */}
            <Collapsible open={promptOpen} onOpenChange={setPromptOpen}>
              <CollapsibleTrigger className="flex items-center gap-1 text-sm font-semibold">
                <ChevronRight className={cn("h-4 w-4 transition-transform", promptOpen && "rotate-90")} />
                System Prompt
              </CollapsibleTrigger>
              <CollapsibleContent>
                <pre className="mt-2 whitespace-pre-wrap rounded-md bg-muted p-3 text-xs font-mono max-h-64 overflow-auto">
                  {selectedAgent.system_prompt || "None"}
                </pre>
              </CollapsibleContent>
            </Collapsible>

            {/* Tools */}
            <div>
              <p className="text-sm font-semibold mb-2">Tools</p>
              <div className="flex flex-wrap gap-1">
                {selectedAgent.tools.length === 0 ? (
                  <span className="text-xs text-muted-foreground">None</span>
                ) : (
                  selectedAgent.tools.map((t) => (
                    <TagBadge key={t.name} tag={t.name} size="sm" />
                  ))
                )}
              </div>
            </div>

            {/* Triggers */}
            <div>
              <p className="text-sm font-semibold mb-2">Triggers</p>
              {selectedAgent.triggers.length === 0 ? (
                <span className="text-xs text-muted-foreground">None configured</span>
              ) : (
                <div className="space-y-2">
                  {selectedAgent.triggers.map((t, i) => (
                    <div key={i} className="rounded-md border p-2 text-xs space-y-1">
                      <Badge variant="outline" className="capitalize text-xs">
                        {t.type}
                      </Badge>
                      {t.type === "mqtt" && t.topic && (
                        <p className="text-muted-foreground font-mono">{t.topic}</p>
                      )}
                      {t.type === "schedule" && t.cron && (
                        <p className="text-muted-foreground font-mono">{t.cron}</p>
                      )}
                      {t.type === "schedule" && t.interval_seconds && (
                        <p className="text-muted-foreground">Every {t.interval_seconds}s</p>
                      )}
                      {t.type === "event" && t.event_type && (
                        <p className="text-muted-foreground">{t.event_type}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Output channels */}
            <div>
              <p className="text-sm font-semibold mb-2">Output Channels</p>
              <div className="flex flex-wrap gap-1">
                {selectedAgent.output_channels.length === 0 ? (
                  <span className="text-xs text-muted-foreground">None</span>
                ) : (
                  selectedAgent.output_channels.map((c) => (
                    <TagBadge key={c} tag={c} size="sm" />
                  ))
                )}
              </div>
            </div>

            {/* Recent runs */}
            <div>
              <p className="text-sm font-semibold mb-2">Recent Runs</p>
              {selectedRuns.length === 0 ? (
                <span className="text-xs text-muted-foreground">No runs yet</span>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">Status</TableHead>
                      <TableHead className="text-xs">Trigger</TableHead>
                      <TableHead className="text-xs">When</TableHead>
                      <TableHead className="text-xs">Duration</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {selectedRuns.map((r) => (
                      <TableRow key={r.id}>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className={cn("text-xs capitalize", statusColors[r.status])}
                          >
                            {r.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs capitalize">{r.trigger_type}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {r.started_at
                            ? formatDistanceToNow(new Date(r.started_at), { addSuffix: true })
                            : "-"}
                        </TableCell>
                        <TableCell className="text-xs tabular-nums">
                          {r.duration_seconds != null ? `${r.duration_seconds.toFixed(1)}s` : "-"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>

            {/* Actions */}
            <div className="flex gap-2 border-t pt-4">
              <Button
                variant="outline"
                size="sm"
                onClick={() => navigate(`/agents/builder?edit=${selectedAgent.name}`)}
              >
                <Pencil className="mr-1 h-3 w-3" /> Edit
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="text-destructive hover:text-destructive"
                onClick={() => setDeleteName(selectedAgent.name)}
              >
                <Trash2 className="mr-1 h-3 w-3" /> Delete
              </Button>
            </div>
          </div>
        )}
      </SlidePanel>

      <ConfirmDialog
        open={deleteName !== null}
        title="Delete agent?"
        description={`This will permanently delete "${deleteName}" and all its configuration.`}
        onConfirm={handleDelete}
        onCancel={() => setDeleteName(null)}
        destructive
      />
    </div>
  )
}

export default Agents
