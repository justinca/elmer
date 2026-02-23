import { useState, useEffect } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { queryKeys } from "@/lib/queryKeys"
import { STALE_TIMES } from "@/lib/queryClient"
import { useDocumentTitle } from "@/hooks/useDocumentTitle"
import { toast } from "sonner"
import { cn } from "@/lib/utils"
import {
  getUpcomingContests, getContestHistory, getContestDashboard, getContestBandRec,
} from "@/lib/api"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/EmptyState"
import { SlidePanel } from "@/components/SlidePanel"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import {
  Trophy, Calendar, Clock, ExternalLink, RefreshCw,
  Zap,
} from "lucide-react"
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis,
} from "recharts"
import { format, isPast, isFuture } from "date-fns"

interface Contest {
  name: string
  full_name: string
  start_utc: string
  end_utc: string
  mode: string
  bands: string[]
  exchange: string
  rules_url: string
  sponsor: string
  is_major: boolean
  source: string
}

interface ContestDash {
  contest_name: string
  total_qsos: number
  unique_calls: number
  unique_countries: number
  bands_worked: Record<string, number>
  rate_last_10: { rate_per_hour: number }
  rate_last_60: { rate_per_hour: number }
  multipliers: number
  estimated_score: number
  elapsed_hours: number
}

interface PastContest {
  name?: string
  contest?: string
  date?: string
  qsos?: number
  score?: number
  mults?: number
  [key: string]: unknown
}

function isActive(c: Contest): boolean {
  return isPast(new Date(c.start_utc)) && isFuture(new Date(c.end_utc))
}

function Contests() {
  useDocumentTitle("Contests")
  const queryClient = useQueryClient()

  const [daysRange, setDaysRange] = useState(30)

  // Live dashboard
  const [activeContest, setActiveContest] = useState<Contest | null>(null)
  const [bandRec, setBandRec] = useState<string | null>(null)

  // Detail panel
  const [panelContest, setPanelContest] = useState<Contest | null>(null)
  const [panelOpen, setPanelOpen] = useState(false)

  const { data: upcoming = [], isLoading } = useQuery<Contest[]>({
    queryKey: queryKeys.contests.upcoming(daysRange),
    queryFn: () => getUpcomingContests(daysRange).then((r) => r.data || []),
    staleTime: STALE_TIMES.contests,
    refetchInterval: 60_000,
  })

  const { data: history = [] } = useQuery<PastContest[]>({
    queryKey: queryKeys.contests.history(),
    queryFn: () => getContestHistory().then((r) => r.data || []),
    staleTime: STALE_TIMES.contests,
    refetchInterval: 60_000,
  })

  // Auto-detect active contest when upcoming data changes
  useEffect(() => {
    const active = upcoming.find((c) => isActive(c))
    if (active) setActiveContest(active)
  }, [upcoming])

  // Conditional dashboard query: only runs when there's an active contest
  const { data: dashboard, isLoading: dashLoading } = useQuery<ContestDash | null>({
    queryKey: queryKeys.contests.dashboard(activeContest?.name || ""),
    queryFn: () => getContestDashboard(activeContest!.name).then((r) => r.data),
    staleTime: STALE_TIMES.contests,
    refetchInterval: 30_000,
    enabled: !!activeContest,
  })

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.contests.all })
  }

  const handleBandRec = async () => {
    if (!activeContest || !dashboard) return
    try {
      const currentBand = Object.entries(dashboard.bands_worked)
        .sort((a, b) => b[1] - a[1])[0]?.[0] || "20m"
      const res = await getContestBandRec(currentBand, activeContest.name)
      setBandRec(`${res.data.suggested_band}: ${res.data.reason}`)
    } catch {
      toast.error("Band recommendation unavailable")
    }
  }

  const bandChartData = dashboard
    ? Object.entries(dashboard.bands_worked).map(([band, count]) => ({ band, count }))
    : []

  return (
    <div className="space-y-6">
      <PageHeader
        title="Contests"
        description="Contest calendar, live dashboard, and results"
        actions={
          <div className="flex gap-2">
            <Select value={String(daysRange)} onValueChange={(v) => setDaysRange(Number(v))}>
              <SelectTrigger className="w-[120px] h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="7">Next 7 days</SelectItem>
                <SelectItem value="30">Next 30 days</SelectItem>
                <SelectItem value="90">Next 90 days</SelectItem>
              </SelectContent>
            </Select>
            <Button variant="outline" size="sm" onClick={handleRefresh}>
              <RefreshCw className="mr-2 h-4 w-4" /> Refresh
            </Button>
          </div>
        }
      />

      {/* Live contest dashboard */}
      {activeContest && (
        <Card className="border-primary/50">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm flex items-center gap-2">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
                </span>
                Live: {activeContest.full_name}
              </CardTitle>
              <Button variant="outline" size="sm" className="h-7 text-xs" onClick={handleBandRec}>
                <Zap className="mr-1 h-3 w-3" /> Band Rec
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {dashLoading && !dashboard ? (
              <div className="grid gap-3 sm:grid-cols-4">
                {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-16" />)}
              </div>
            ) : dashboard ? (
              <div className="space-y-4">
                <div className="grid gap-3 sm:grid-cols-4">
                  <div className="text-center">
                    <p className="text-2xl font-bold tabular-nums">{dashboard.total_qsos}</p>
                    <p className="text-xs text-muted-foreground">QSOs</p>
                  </div>
                  <div className="text-center">
                    <p className="text-2xl font-bold tabular-nums">{dashboard.rate_last_10?.rate_per_hour?.toFixed(0) ?? 0}</p>
                    <p className="text-xs text-muted-foreground">Rate/hr (10m)</p>
                  </div>
                  <div className="text-center">
                    <p className="text-2xl font-bold tabular-nums">{dashboard.multipliers}</p>
                    <p className="text-xs text-muted-foreground">Multipliers</p>
                  </div>
                  <div className="text-center">
                    <p className="text-2xl font-bold tabular-nums">{dashboard.estimated_score?.toLocaleString()}</p>
                    <p className="text-xs text-muted-foreground">Est. Score</p>
                  </div>
                </div>

                {bandChartData.length > 0 && (
                  <ResponsiveContainer width="100%" height={120}>
                    <BarChart data={bandChartData} layout="vertical">
                      <XAxis type="number" tick={{ fontSize: 10 }} />
                      <YAxis type="category" dataKey="band" tick={{ fontSize: 11 }} width={40} />
                      <Bar dataKey="count" fill="#2563EB" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}

                {bandRec && (
                  <div className="rounded-md border border-primary/30 bg-primary/5 p-2 text-sm">
                    <Zap className="inline h-3.5 w-3.5 mr-1 text-primary" />
                    {bandRec}
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-4">
                Dashboard data not available for this contest
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Upcoming contests */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Calendar className="h-4 w-4" /> Upcoming Contests
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-4 space-y-2">
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20" />)}
            </div>
          ) : upcoming.length === 0 ? (
            <EmptyState
              icon={Calendar}
              title="No upcoming contests"
              description="No contests found in the selected time range"
              className="py-8"
            />
          ) : (
            <ScrollArea className="max-h-[500px]">
              <div className="divide-y">
                {upcoming.map((c) => {
                  const active = isActive(c)
                  return (
                    <div
                      key={c.name}
                      className={cn(
                        "flex items-start gap-4 p-4 hover:bg-accent/50 cursor-pointer",
                        active && "bg-primary/5",
                      )}
                      onClick={() => { setPanelContest(c); setPanelOpen(true) }}
                    >
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                        <Trophy className={cn("h-5 w-5", c.is_major ? "text-primary" : "text-muted-foreground")} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="font-semibold text-sm truncate">{c.full_name}</p>
                          {active && (
                            <Badge variant="default" className="text-xs shrink-0">Live</Badge>
                          )}
                          {c.is_major && !active && (
                            <Badge variant="outline" className="text-xs shrink-0">Major</Badge>
                          )}
                        </div>
                        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-xs text-muted-foreground">
                          <span className="flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            {format(new Date(c.start_utc), "MMM d")} — {format(new Date(c.end_utc), "MMM d")}
                          </span>
                          <Badge variant="secondary" className="text-xs">{c.mode}</Badge>
                          {c.sponsor && <span>{c.sponsor}</span>}
                        </div>
                      </div>
                      {c.rules_url && (
                        <a
                          href={c.rules_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="shrink-0 text-muted-foreground hover:text-primary"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <ExternalLink className="h-4 w-4" />
                        </a>
                      )}
                    </div>
                  )
                })}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </Card>

      {/* Past results */}
      {history.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Past Results</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Contest</TableHead>
                  <TableHead className="text-xs">Date</TableHead>
                  <TableHead className="text-xs">QSOs</TableHead>
                  <TableHead className="text-xs">Score</TableHead>
                  <TableHead className="text-xs">Mults</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.map((h, i) => (
                  <TableRow key={i}>
                    <TableCell className="text-sm font-medium">{h.name || h.contest || "—"}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{h.date || "—"}</TableCell>
                    <TableCell className="text-xs tabular-nums">{h.qsos ?? "—"}</TableCell>
                    <TableCell className="text-xs tabular-nums">{h.score?.toLocaleString() ?? "—"}</TableCell>
                    <TableCell className="text-xs tabular-nums">{h.mults ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Contest detail panel */}
      <SlidePanel
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        title={panelContest?.full_name || "Contest"}
      >
        {panelContest && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-muted-foreground">Start</p>
                <p className="text-sm font-medium">{format(new Date(panelContest.start_utc), "PPpp")}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">End</p>
                <p className="text-sm font-medium">{format(new Date(panelContest.end_utc), "PPpp")}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Mode</p>
                <Badge variant="secondary">{panelContest.mode}</Badge>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Sponsor</p>
                <p className="text-sm">{panelContest.sponsor || "—"}</p>
              </div>
            </div>
            <div>
              <p className="text-xs text-muted-foreground mb-1">Exchange</p>
              <p className="text-sm font-mono">{panelContest.exchange || "—"}</p>
            </div>
            {panelContest.bands?.length > 0 && (
              <div>
                <p className="text-xs text-muted-foreground mb-1">Bands</p>
                <div className="flex flex-wrap gap-1">
                  {panelContest.bands.map((b) => (
                    <Badge key={b} variant="outline" className="text-xs">{b}</Badge>
                  ))}
                </div>
              </div>
            )}
            {panelContest.rules_url && (
              <a
                href={panelContest.rules_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
              >
                <ExternalLink className="h-3.5 w-3.5" /> View Rules
              </a>
            )}
          </div>
        )}
      </SlidePanel>
    </div>
  )
}

export default Contests
