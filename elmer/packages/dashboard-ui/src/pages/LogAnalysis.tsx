import { useState, useMemo, useCallback } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { queryKeys } from "@/lib/queryKeys"
import { STALE_TIMES } from "@/lib/queryClient"
import { useDocumentTitle } from "@/hooks/useDocumentTitle"
import { toast } from "sonner"
import { cn } from "@/lib/utils"
import { getLogStats, getRecentQsos, getDxcc, analyzeLog, searchLog } from "@/lib/api"
import { PageHeader } from "@/components/PageHeader"
import { StatCard } from "@/components/StatCard"
import { SearchBar } from "@/components/SearchBar"
import { MarkdownRenderer } from "@/components/MarkdownRenderer"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Progress } from "@/components/ui/progress"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import {
  Radio, Globe, Grid3X3, Trophy, Sparkles, ChevronRight, RefreshCw, Loader2,
} from "lucide-react"
import {
  ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip as RTooltip,
} from "recharts"
import { formatDistanceToNow } from "date-fns"

interface LogStats {
  total_qsos?: number
  unique_entities?: number
  unique_grids?: number
  bands?: Record<string, number>
  modes?: Record<string, number>
  monthly?: Array<{ month: string; count: number }>
  [key: string]: unknown
}

interface QsoRecord {
  id?: number
  date?: string
  call?: string
  band?: string
  mode?: string
  country?: string
  grid?: string
  contest?: string
  rst_sent?: string
  rst_rcvd?: string
  [key: string]: unknown
}

interface DxccEntry {
  entity?: string
  country?: string
  confirmed?: boolean
  bands?: string[]
  modes?: string[]
  [key: string]: unknown
}

const CHART_COLORS = [
  "#2563EB", // signal blue
  "#0EA5E9", // elmer teal
  "#F59E0B", // rf amber
  "#10B981", // tx green
  "#EF4444", // qrm red
  "#EAB308", // standby yellow
  "#94A3B8", // slate
]

function LogAnalysis() {
  useDocumentTitle("Log Analysis")
  const queryClient = useQueryClient()

  const [dxccOpen, setDxccOpen] = useState(false)

  // AI analysis
  const [analyzing, setAnalyzing] = useState(false)
  const [analysis, setAnalysis] = useState<string | null>(null)

  // Search
  const [searchResults, setSearchResults] = useState<QsoRecord[] | null>(null)
  const [searching, setSearching] = useState(false)

  const { data: stats, isLoading } = useQuery<LogStats | null>({
    queryKey: queryKeys.log.stats(),
    queryFn: () => getLogStats().then((r) => r.data),
    staleTime: STALE_TIMES.log,
    refetchInterval: 60_000,
  })

  const { data: recent = [] } = useQuery<QsoRecord[]>({
    queryKey: queryKeys.log.recent(30),
    queryFn: () => getRecentQsos(30).then((r) => r.data || []),
    staleTime: STALE_TIMES.log,
    refetchInterval: 60_000,
  })

  const { data: dxcc = [] } = useQuery<DxccEntry[]>({
    queryKey: queryKeys.log.dxcc(),
    queryFn: () => getDxcc().then((r) => r.data || []),
    staleTime: STALE_TIMES.log,
    refetchInterval: 60_000,
  })

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.log.all })
  }

  const bandData = useMemo(() => {
    if (!stats?.bands) return []
    return Object.entries(stats.bands)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
  }, [stats])

  const modeData = useMemo(() => {
    if (!stats?.modes) return []
    return Object.entries(stats.modes)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
  }, [stats])

  const monthlyData = useMemo(() => stats?.monthly || [], [stats])

  const dxccConfirmed = useMemo(() => dxcc.filter((d) => d.confirmed).length, [dxcc])

  const handleSearch = useCallback(async (q: string) => {
    if (!q.trim()) {
      setSearchResults(null)
      return
    }
    setSearching(true)
    try {
      const res = await searchLog(q)
      setSearchResults(res.data || [])
    } catch {
      toast.error("Search failed")
    } finally {
      setSearching(false)
    }
  }, [])

  const handleAnalyze = async () => {
    setAnalyzing(true)
    setAnalysis(null)
    try {
      const res = await analyzeLog(30)
      setAnalysis(res.data?.analysis || res.data?.response || JSON.stringify(res.data))
    } catch {
      toast.error("Analysis failed — agent may not be available")
    } finally {
      setAnalyzing(false)
    }
  }

  const displayQsos = searchResults ?? recent

  return (
    <div className="space-y-6">
      <PageHeader
        title="Log Analysis"
        description="QSO log statistics and DXCC tracking"
        actions={
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={handleAnalyze} disabled={analyzing}>
              {analyzing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}
              Analyze with AI
            </Button>
            <Button variant="outline" size="sm" onClick={handleRefresh}>
              <RefreshCw className="mr-2 h-4 w-4" /> Refresh
            </Button>
          </div>
        }
      />

      {/* Summary cards */}
      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24" />)}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Total QSOs" value={stats?.total_qsos ?? 0} icon={Radio} />
          <StatCard label="DXCC Entities" value={stats?.unique_entities ?? dxcc.length} icon={Globe} />
          <StatCard label="Unique Grids" value={stats?.unique_grids ?? 0} icon={Grid3X3} />
          <StatCard label="DXCC Confirmed" value={dxccConfirmed} icon={Trophy} subtitle={`of ${dxcc.length} worked`} />
        </div>
      )}

      {/* AI Analysis */}
      {analysis && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" /> AI Analysis
            </CardTitle>
          </CardHeader>
          <CardContent>
            <MarkdownRenderer content={analysis} />
          </CardContent>
        </Card>
      )}

      {/* Charts */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* Monthly QSOs */}
        {monthlyData.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">QSOs per Month</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={monthlyData}>
                  <XAxis dataKey="month" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <RTooltip
                    contentStyle={{
                      backgroundColor: "var(--card)",
                      border: "1px solid var(--border)",
                      borderRadius: "8px",
                      fontSize: "12px",
                    }}
                  />
                  <Bar dataKey="count" fill="#2563EB" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}

        {/* Band distribution */}
        {bandData.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">QSOs per Band</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie
                    data={bandData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
                    labelLine={false}
                    fontSize={10}
                  >
                    {bandData.map((_, i) => (
                      <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                    ))}
                  </Pie>
                  <RTooltip
                    contentStyle={{
                      backgroundColor: "var(--card)",
                      border: "1px solid var(--border)",
                      borderRadius: "8px",
                      fontSize: "12px",
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}

        {/* Mode distribution */}
        {modeData.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">QSOs per Mode</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie
                    data={modeData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
                    labelLine={false}
                    fontSize={10}
                  >
                    {modeData.map((_, i) => (
                      <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                    ))}
                  </Pie>
                  <RTooltip
                    contentStyle={{
                      backgroundColor: "var(--card)",
                      border: "1px solid var(--border)",
                      borderRadius: "8px",
                      fontSize: "12px",
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}

        {/* Placeholder for when no chart data */}
        {bandData.length === 0 && modeData.length === 0 && monthlyData.length === 0 && !isLoading && (
          <Card className="md:col-span-2">
            <CardContent className="py-12 text-center text-sm text-muted-foreground">
              No log statistics available — Log4OM may not be connected
            </CardContent>
          </Card>
        )}
      </div>

      {/* DXCC tracker */}
      <Collapsible open={dxccOpen} onOpenChange={setDxccOpen}>
        <Card>
          <CollapsibleTrigger asChild>
            <CardHeader className="cursor-pointer hover:bg-accent/50 rounded-t-lg pb-2">
              <CardTitle className="text-sm flex items-center gap-1">
                <ChevronRight className={cn("h-4 w-4 transition-transform", dxccOpen && "rotate-90")} />
                DXCC Progress
              </CardTitle>
            </CardHeader>
          </CollapsibleTrigger>
          <CardContent>
            <div className="space-y-3 mb-4">
              <div>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span>DXCC Mixed</span>
                  <span className="tabular-nums">{dxcc.length} / 100</span>
                </div>
                <Progress value={Math.min((dxcc.length / 100) * 100, 100)} className="h-2" />
              </div>
              <div>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span>Confirmed</span>
                  <span className="tabular-nums">{dxccConfirmed} / 100</span>
                </div>
                <Progress value={Math.min((dxccConfirmed / 100) * 100, 100)} className="h-2" />
              </div>
              <div>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span>Honor Roll</span>
                  <span className="tabular-nums">{dxcc.length} / 340</span>
                </div>
                <Progress value={Math.min((dxcc.length / 340) * 100, 100)} className="h-2" />
              </div>
            </div>
          </CardContent>
          <CollapsibleContent>
            <CardContent className="pt-0">
              <ScrollArea className="h-[300px]">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">Entity</TableHead>
                      <TableHead className="text-xs">Confirmed</TableHead>
                      <TableHead className="text-xs">Bands</TableHead>
                      <TableHead className="text-xs">Modes</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {dxcc.map((d, i) => (
                      <TableRow key={i}>
                        <TableCell className="text-sm">{d.entity || d.country}</TableCell>
                        <TableCell>
                          <Badge
                            variant={d.confirmed ? "default" : "secondary"}
                            className="text-xs"
                          >
                            {d.confirmed ? "Yes" : "No"}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs">
                          {(d.bands || []).join(", ") || "—"}
                        </TableCell>
                        <TableCell className="text-xs">
                          {(d.modes || []).join(", ") || "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </ScrollArea>
            </CardContent>
          </CollapsibleContent>
        </Card>
      </Collapsible>

      {/* Recent QSOs / Search */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between gap-4">
            <CardTitle className="text-sm">
              {searchResults ? `Search Results (${searchResults.length})` : "Recent QSOs"}
            </CardTitle>
            <SearchBar
              placeholder="Search callsign, entity..."
              onSearch={handleSearch}
              loading={searching}
              className="w-64"
            />
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <ScrollArea className="h-[400px]">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Date</TableHead>
                  <TableHead className="text-xs">Call</TableHead>
                  <TableHead className="text-xs">Band</TableHead>
                  <TableHead className="text-xs">Mode</TableHead>
                  <TableHead className="text-xs">Entity</TableHead>
                  <TableHead className="text-xs hidden md:table-cell">Grid</TableHead>
                  <TableHead className="text-xs hidden lg:table-cell">Contest</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {displayQsos.map((q, i) => (
                  <TableRow key={q.id ?? i}>
                    <TableCell className="text-xs text-muted-foreground">
                      {q.date ? formatDistanceToNow(new Date(q.date), { addSuffix: true }) : "—"}
                    </TableCell>
                    <TableCell className="font-mono font-semibold text-sm">{q.call || "—"}</TableCell>
                    <TableCell><Badge variant="outline" className="text-xs">{q.band || "—"}</Badge></TableCell>
                    <TableCell><Badge variant="secondary" className="text-xs">{q.mode || "—"}</Badge></TableCell>
                    <TableCell className="text-xs">{q.country || "—"}</TableCell>
                    <TableCell className="text-xs font-mono hidden md:table-cell">{q.grid || "—"}</TableCell>
                    <TableCell className="text-xs hidden lg:table-cell">{q.contest || "—"}</TableCell>
                  </TableRow>
                ))}
                {displayQsos.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center text-sm text-muted-foreground py-8">
                      {searchResults ? "No results found" : "No QSOs available"}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  )
}

export default LogAnalysis
