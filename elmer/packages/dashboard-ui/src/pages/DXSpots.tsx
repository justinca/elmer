import { useState, useMemo } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { queryKeys } from "@/lib/queryKeys"
import { STALE_TIMES } from "@/lib/queryClient"
import { useDocumentTitle } from "@/hooks/useDocumentTitle"
import { toast } from "sonner"
import { cn } from "@/lib/utils"
import {
  getDxSpots, getDxSummary, getNeeds, addNeed, deleteNeed,
  getClusterStatus, lookupCallsign,
} from "@/lib/api"
import { PageHeader } from "@/components/PageHeader"
import { TagBadge } from "@/components/TagBadge"
import { ConfirmDialog } from "@/components/ConfirmDialog"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Wifi, WifiOff, Plus, Trash2, ChevronRight, Search, RefreshCw,
} from "lucide-react"
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip as RTooltip } from "recharts"
import { formatDistanceToNow } from "date-fns"

interface DxSpot {
  id: number
  timestamp: string
  spotter: string
  dx_call: string
  frequency: number
  band: string
  mode: string
  comment: string
  dx_entity: string
}

interface NeedItem {
  id: number
  entity: string
  band: string | null
  mode: string | null
  priority: number
  needed: boolean
}

interface ClusterStat {
  connected: boolean
  spots_in_memory: number
  total_spots_received: number
}

interface EntityLookup {
  callsign: string
  entity_name: string
  continent: string
  cq_zone: number
}

const BANDS = ["160m", "80m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m"]
const MODES = ["CW", "SSB", "FT8", "FT4", "RTTY"]

function DXSpots() {
  useDocumentTitle("DX Spots")
  const queryClient = useQueryClient()

  // Filters
  const [bandFilter, setBandFilter] = useState<string[]>([])
  const [modeFilter, setModeFilter] = useState<string[]>([])
  const [needsOnly, setNeedsOnly] = useState(false)

  // Add need form
  const [needsOpen, setNeedsOpen] = useState(false)
  const [newEntity, setNewEntity] = useState("")
  const [newBand, setNewBand] = useState("")
  const [newMode, setNewMode] = useState("")
  const [deleteId, setDeleteId] = useState<number | null>(null)

  // Callsign lookup
  const [lookupCall, setLookupCall] = useState("")
  const [lookupResult, setLookupResult] = useState<EntityLookup | null>(null)
  const [lookupLoading, setLookupLoading] = useState(false)

  const { data: spots = [], isLoading } = useQuery<DxSpot[]>({
    queryKey: queryKeys.dx.spots({ limit: 100 }),
    queryFn: () => getDxSpots({ limit: 100 }).then((r) => r.data || []),
    staleTime: STALE_TIMES.dxSpots,
    refetchInterval: 30_000,
  })

  const { data: summary } = useQuery<{ bands: Record<string, number> } | null>({
    queryKey: queryKeys.dx.summary(),
    queryFn: () => getDxSummary().then((r) => r.data),
    staleTime: STALE_TIMES.dxSpots,
    refetchInterval: 30_000,
  })

  const { data: needs = [] } = useQuery<NeedItem[]>({
    queryKey: queryKeys.dx.needs(),
    queryFn: () => getNeeds().then((r) => r.data || []),
    staleTime: STALE_TIMES.dxSpots,
    refetchInterval: 30_000,
  })

  const { data: cluster } = useQuery<ClusterStat | null>({
    queryKey: queryKeys.dx.cluster(),
    queryFn: () => getClusterStatus().then((r) => r.data),
    staleTime: STALE_TIMES.dxSpots,
    refetchInterval: 30_000,
  })

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.dx.all })
  }

  const needEntities = useMemo(() => {
    const set = new Set<string>()
    needs.forEach((n) => set.add(n.entity.toLowerCase()))
    return set
  }, [needs])

  const filtered = useMemo(() => {
    let list = spots
    if (bandFilter.length > 0) list = list.filter((s) => bandFilter.includes(s.band))
    if (modeFilter.length > 0) list = list.filter((s) => modeFilter.includes(s.mode))
    if (needsOnly) list = list.filter((s) => needEntities.has(s.dx_entity?.toLowerCase()))
    return list
  }, [spots, bandFilter, modeFilter, needsOnly, needEntities])

  const bandChartData = useMemo(() => {
    if (!summary?.bands) return []
    return BANDS.map((b) => ({ band: b, count: summary.bands[b] || 0 })).filter((d) => d.count > 0)
  }, [summary])

  const handleAddNeed = async () => {
    if (!newEntity.trim()) return
    try {
      await addNeed({
        entity: newEntity.trim(),
        band: newBand || undefined,
        mode: newMode || undefined,
        priority: 5,
      })
      toast.success("Need added")
      setNewEntity("")
      setNewBand("")
      setNewMode("")
      queryClient.invalidateQueries({ queryKey: queryKeys.dx.needs() })
    } catch {
      toast.error("Failed to add need")
    }
  }

  const handleDeleteNeed = async () => {
    if (deleteId === null) return
    try {
      await deleteNeed(deleteId)
      toast.success("Need removed")
      queryClient.invalidateQueries({ queryKey: queryKeys.dx.needs() })
    } catch {
      toast.error("Failed to delete need")
    } finally {
      setDeleteId(null)
    }
  }

  const handleLookup = async () => {
    if (!lookupCall.trim()) return
    setLookupLoading(true)
    try {
      const res = await lookupCallsign(lookupCall.trim().toUpperCase())
      setLookupResult(res.data)
    } catch {
      toast.error("Callsign not found")
      setLookupResult(null)
    } finally {
      setLookupLoading(false)
    }
  }

  const toggleBand = (b: string) =>
    setBandFilter((p) => (p.includes(b) ? p.filter((x) => x !== b) : [...p, b]))
  const toggleMode = (m: string) =>
    setModeFilter((p) => (p.includes(m) ? p.filter((x) => x !== m) : [...p, m]))

  return (
    <div className="space-y-6">
      <PageHeader
        title="DX Spots"
        description="Live DX cluster feed"
        actions={
          <div className="flex items-center gap-3">
            {cluster && (
              <Badge variant="outline" className={cn("text-xs", cluster.connected ? "text-emerald-500" : "text-destructive")}>
                {cluster.connected ? <Wifi className="mr-1 h-3 w-3" /> : <WifiOff className="mr-1 h-3 w-3" />}
                {cluster.connected ? "Connected" : "Disconnected"}
              </Badge>
            )}
            <Button variant="outline" size="sm" onClick={handleRefresh}>
              <RefreshCw className="mr-2 h-4 w-4" /> Refresh
            </Button>
          </div>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <div className="space-y-4">
          {/* Filters */}
          <Card>
            <CardContent className="p-3">
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex flex-wrap gap-1">
                  <span className="text-xs text-muted-foreground mr-1 self-center">Band:</span>
                  {BANDS.map((b) => (
                    <TagBadge key={b} tag={b} active={bandFilter.includes(b)} onClick={toggleBand} size="sm" />
                  ))}
                </div>
                <div className="flex flex-wrap gap-1">
                  <span className="text-xs text-muted-foreground mr-1 self-center">Mode:</span>
                  {MODES.map((m) => (
                    <TagBadge key={m} tag={m} active={modeFilter.includes(m)} onClick={toggleMode} size="sm" />
                  ))}
                </div>
                <div className="flex items-center gap-2 ml-auto">
                  <Switch checked={needsOnly} onCheckedChange={setNeedsOnly} id="needs-only" />
                  <Label htmlFor="needs-only" className="text-xs">Needs only</Label>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Spots table */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">{filtered.length} spots</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {isLoading ? (
                <div className="p-4 space-y-2">
                  {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-8" />)}
                </div>
              ) : (
                <ScrollArea className="h-[500px]">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs">Time</TableHead>
                        <TableHead className="text-xs">DX Call</TableHead>
                        <TableHead className="text-xs">Freq</TableHead>
                        <TableHead className="text-xs">Band</TableHead>
                        <TableHead className="text-xs">Mode</TableHead>
                        <TableHead className="text-xs">Entity</TableHead>
                        <TableHead className="text-xs">Spotter</TableHead>
                        <TableHead className="text-xs hidden lg:table-cell">Comment</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filtered.map((spot) => {
                        const isNeed = needEntities.has(spot.dx_entity?.toLowerCase())
                        return (
                          <TableRow
                            key={spot.id}
                            className={cn(isNeed && "bg-primary/5 hover:bg-primary/10")}
                          >
                            <TableCell className="text-xs text-muted-foreground tabular-nums">
                              {formatDistanceToNow(new Date(spot.timestamp), { addSuffix: true })}
                            </TableCell>
                            <TableCell className={cn("font-mono font-semibold text-sm", isNeed && "text-primary")}>
                              {spot.dx_call}
                            </TableCell>
                            <TableCell className="text-xs font-mono tabular-nums">
                              {spot.frequency?.toFixed(1)}
                            </TableCell>
                            <TableCell>
                              <Badge variant="outline" className="text-xs">{spot.band}</Badge>
                            </TableCell>
                            <TableCell>
                              <Badge variant="secondary" className="text-xs">{spot.mode}</Badge>
                            </TableCell>
                            <TableCell className="text-xs">{spot.dx_entity}</TableCell>
                            <TableCell className="text-xs font-mono text-muted-foreground">{spot.spotter}</TableCell>
                            <TableCell className="text-xs text-muted-foreground hidden lg:table-cell max-w-[200px] truncate">
                              {spot.comment}
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
        </div>

        {/* Right sidebar */}
        <div className="space-y-4">
          {/* Band activity chart */}
          {bandChartData.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Band Activity (1h)</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={bandChartData} layout="vertical">
                    <XAxis type="number" tick={{ fontSize: 10 }} />
                    <YAxis type="category" dataKey="band" tick={{ fontSize: 11 }} width={40} />
                    <RTooltip
                      contentStyle={{
                        backgroundColor: "hsl(var(--card))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: "8px",
                        fontSize: "12px",
                      }}
                    />
                    <Bar dataKey="count" fill="hsl(var(--primary))" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          {/* Callsign lookup */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Callsign Lookup</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex gap-1">
                <Input
                  value={lookupCall}
                  onChange={(e) => setLookupCall(e.target.value.toUpperCase())}
                  placeholder="JA1ABC"
                  className="font-mono text-sm"
                  onKeyDown={(e) => e.key === "Enter" && handleLookup()}
                />
                <Button size="icon" variant="outline" onClick={handleLookup} disabled={lookupLoading}>
                  <Search className="h-4 w-4" />
                </Button>
              </div>
              {lookupResult && (
                <div className="rounded-md border p-2 space-y-1 text-xs">
                  <p className="font-semibold">{lookupResult.callsign}</p>
                  <p>{lookupResult.entity_name}</p>
                  <p className="text-muted-foreground">
                    {lookupResult.continent} / CQ {lookupResult.cq_zone}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Needs list */}
          <Collapsible open={needsOpen} onOpenChange={setNeedsOpen}>
            <Card>
              <CollapsibleTrigger asChild>
                <CardHeader className="pb-2 cursor-pointer hover:bg-accent/50 rounded-t-lg">
                  <CardTitle className="text-sm flex items-center gap-1">
                    <ChevronRight className={cn("h-4 w-4 transition-transform", needsOpen && "rotate-90")} />
                    Needs List ({needs.length})
                  </CardTitle>
                </CardHeader>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <CardContent className="space-y-3">
                  {/* Add form */}
                  <div className="space-y-2">
                    <Input
                      value={newEntity}
                      onChange={(e) => setNewEntity(e.target.value)}
                      placeholder="Entity name"
                      className="text-sm"
                    />
                    <div className="flex gap-1">
                      <Select value={newBand} onValueChange={setNewBand}>
                        <SelectTrigger className="text-xs h-8">
                          <SelectValue placeholder="Band" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="any">Any</SelectItem>
                          {BANDS.map((b) => <SelectItem key={b} value={b}>{b}</SelectItem>)}
                        </SelectContent>
                      </Select>
                      <Select value={newMode} onValueChange={setNewMode}>
                        <SelectTrigger className="text-xs h-8">
                          <SelectValue placeholder="Mode" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="any">Any</SelectItem>
                          {MODES.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
                        </SelectContent>
                      </Select>
                      <Button size="sm" className="h-8" onClick={handleAddNeed}>
                        <Plus className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                  {/* Needs table */}
                  <ScrollArea className="h-[200px]">
                    <div className="space-y-1">
                      {needs.map((n) => (
                        <div
                          key={n.id}
                          className="flex items-center justify-between rounded border px-2 py-1"
                        >
                          <div className="text-xs">
                            <span className="font-medium">{n.entity}</span>
                            {n.band && <Badge variant="outline" className="ml-1 text-[10px]">{n.band}</Badge>}
                            {n.mode && <Badge variant="secondary" className="ml-1 text-[10px]">{n.mode}</Badge>}
                          </div>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6"
                            onClick={() => setDeleteId(n.id)}
                          >
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                </CardContent>
              </CollapsibleContent>
            </Card>
          </Collapsible>
        </div>
      </div>

      <ConfirmDialog
        open={deleteId !== null}
        title="Remove need?"
        description="This will remove this entity from your needs list."
        onConfirm={handleDeleteNeed}
        onCancel={() => setDeleteId(null)}
        destructive
      />
    </div>
  )
}

export default DXSpots
