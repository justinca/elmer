import { useState, useMemo, useCallback } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { queryKeys } from "@/lib/queryKeys"
import { STALE_TIMES } from "@/lib/queryClient"
import { useDocumentTitle } from "@/hooks/useDocumentTitle"
import { toast } from "sonner"
import { getPotaSpots, searchParks, getNearbyParks, getParkPlan } from "@/lib/api"
import { PageHeader } from "@/components/PageHeader"
import { SearchBar } from "@/components/SearchBar"
import { TagBadge } from "@/components/TagBadge"
import { SlidePanel } from "@/components/SlidePanel"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  MapPin, RefreshCw, Loader2, Navigation,
} from "lucide-react"
import { formatDistanceToNow } from "date-fns"

interface PotaSpot {
  spot_id: number
  activator: string
  frequency: string
  mode: string
  reference: string
  park_name: string
  location_desc: string
  spotter: string
  comments: string
  spot_time: string
}

interface Park {
  reference: string
  name: string
  grid4: string
  grid6: string
  latitude: number
  longitude: number
  location_desc: string
  park_type: string
  activations: number
  distance_miles: number | null
}

interface ParkPlanData {
  park: Park
  distance_miles: number
  bearing: number
  band_recommendations: Array<{
    band: string
    mode: string
    time_window: string
    condition: string
    rationale: string
  }>
  nearby_parks: Park[]
  notes: string[]
}

const BANDS = ["160m", "80m", "40m", "20m", "15m", "10m"]

function POTA() {
  useDocumentTitle("POTA")
  const queryClient = useQueryClient()

  const [searchResults, setSearchResults] = useState<Park[]>([])
  const [searching, setSearching] = useState(false)

  // Spot filters
  const [bandFilter, setBandFilter] = useState<string[]>([])

  // Park plan
  const [planRef, setPlanRef] = useState("")
  const [plan, setPlan] = useState<ParkPlanData | null>(null)
  const [planLoading, setPlanLoading] = useState(false)
  const [panelOpen, setPanelOpen] = useState(false)

  const { data: spots = [], isLoading } = useQuery<PotaSpot[]>({
    queryKey: queryKeys.pota.spots(),
    queryFn: () => getPotaSpots().then((r) => r.data || []),
    staleTime: STALE_TIMES.pota,
    refetchInterval: 60_000,
  })

  const { data: nearby = [] } = useQuery<Park[]>({
    queryKey: queryKeys.pota.nearby("DN70", 50),
    queryFn: () => getNearbyParks("DN70", 50).then((r) => r.data || []),
    staleTime: STALE_TIMES.pota,
    refetchInterval: 60_000,
  })

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.pota.all })
  }

  const filteredSpots = useMemo(() => {
    if (bandFilter.length === 0) return spots
    return spots.filter((s) => {
      const freq = parseFloat(s.frequency)
      if (isNaN(freq)) return true
      // Simple band matching from frequency
      for (const b of bandFilter) {
        if (b === "160m" && freq >= 1800 && freq < 2000) return true
        if (b === "80m" && freq >= 3500 && freq < 4000) return true
        if (b === "40m" && freq >= 7000 && freq < 7300) return true
        if (b === "20m" && freq >= 14000 && freq < 14350) return true
        if (b === "15m" && freq >= 21000 && freq < 21450) return true
        if (b === "10m" && freq >= 28000 && freq < 29700) return true
      }
      return false
    })
  }, [spots, bandFilter])

  const handleParkSearch = useCallback(async (q: string) => {
    if (!q.trim()) {
      setSearchResults([])
      return
    }
    setSearching(true)
    try {
      const res = await searchParks({ name: q })
      setSearchResults(res.data || [])
    } catch {
      toast.error("Park search failed")
    } finally {
      setSearching(false)
    }
  }, [])

  const handleGeneratePlan = async (ref: string) => {
    setPlanLoading(true)
    try {
      const res = await getParkPlan(ref)
      setPlan(res.data)
      setPanelOpen(true)
    } catch {
      toast.error("Failed to generate plan")
    } finally {
      setPlanLoading(false)
    }
  }

  const toggleBand = (b: string) =>
    setBandFilter((p) => (p.includes(b) ? p.filter((x) => x !== b) : [...p, b]))

  return (
    <div className="space-y-6">
      <PageHeader
        title="POTA"
        description="Parks on the Air — spots, parks, and activation planning"
        actions={
          <Button variant="outline" size="sm" onClick={handleRefresh}>
            <RefreshCw className="mr-2 h-4 w-4" /> Refresh
          </Button>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          {/* Current POTA spots */}
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">
                  Live Spots ({filteredSpots.length})
                </CardTitle>
                <div className="flex gap-1">
                  {BANDS.map((b) => (
                    <TagBadge key={b} tag={b} active={bandFilter.includes(b)} onClick={toggleBand} size="sm" />
                  ))}
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {isLoading ? (
                <div className="p-4 space-y-2">
                  {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-8" />)}
                </div>
              ) : filteredSpots.length === 0 ? (
                <div className="py-8 text-center text-sm text-muted-foreground">No active spots</div>
              ) : (
                <ScrollArea className="h-[420px]">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs">Activator</TableHead>
                        <TableHead className="text-xs">Park</TableHead>
                        <TableHead className="text-xs">Freq</TableHead>
                        <TableHead className="text-xs">Mode</TableHead>
                        <TableHead className="text-xs">Time</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredSpots.map((spot) => (
                        <TableRow key={spot.spot_id}>
                          <TableCell className="font-mono font-semibold text-sm">{spot.activator}</TableCell>
                          <TableCell>
                            <div>
                              <span className="text-xs font-medium">{spot.reference}</span>
                              <p className="text-xs text-muted-foreground truncate max-w-[200px]">
                                {spot.park_name}
                              </p>
                            </div>
                          </TableCell>
                          <TableCell className="text-xs font-mono tabular-nums">{spot.frequency}</TableCell>
                          <TableCell><Badge variant="secondary" className="text-xs">{spot.mode}</Badge></TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {spot.spot_time
                              ? formatDistanceToNow(new Date(spot.spot_time), { addSuffix: true })
                              : "—"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </ScrollArea>
              )}
            </CardContent>
          </Card>

          {/* Park search */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Park Search</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <SearchBar
                placeholder="Search parks by name..."
                onSearch={handleParkSearch}
                loading={searching}
              />
              {searchResults.length > 0 && (
                <ScrollArea className="h-[250px]">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs">Reference</TableHead>
                        <TableHead className="text-xs">Name</TableHead>
                        <TableHead className="text-xs">Grid</TableHead>
                        <TableHead className="text-xs">Activations</TableHead>
                        <TableHead className="text-xs" />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {searchResults.map((p) => (
                        <TableRow key={p.reference}>
                          <TableCell className="font-mono font-semibold text-sm text-primary">
                            {p.reference}
                          </TableCell>
                          <TableCell className="text-xs">{p.name}</TableCell>
                          <TableCell className="text-xs font-mono">{p.grid4}</TableCell>
                          <TableCell className="text-xs tabular-nums">{p.activations}</TableCell>
                          <TableCell>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 text-xs"
                              onClick={() => handleGeneratePlan(p.reference)}
                            >
                              Plan
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </ScrollArea>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right sidebar */}
        <div className="space-y-4">
          {/* Activation planner */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Navigation className="h-4 w-4" /> Activation Planner
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex gap-1">
                <Input
                  value={planRef}
                  onChange={(e) => setPlanRef(e.target.value.toUpperCase())}
                  placeholder="US-1228"
                  className="font-mono text-sm"
                  onKeyDown={(e) => e.key === "Enter" && planRef && handleGeneratePlan(planRef)}
                />
                <Button
                  onClick={() => planRef && handleGeneratePlan(planRef)}
                  disabled={planLoading || !planRef}
                  size="sm"
                >
                  {planLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Plan"}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Enter a park reference to generate a plan with band recommendations and propagation data.
              </p>
            </CardContent>
          </Card>

          {/* Nearby parks */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <MapPin className="h-4 w-4" /> Nearby Parks (DN70)
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {nearby.length === 0 ? (
                <div className="py-8 text-center text-sm text-muted-foreground">
                  No nearby parks found
                </div>
              ) : (
                <ScrollArea className="h-[350px]">
                  <div className="space-y-0 px-4 pb-4">
                    {nearby.slice(0, 20).map((p) => (
                      <div
                        key={p.reference}
                        className="flex items-center justify-between gap-2 border-b py-2 last:border-0 cursor-pointer hover:bg-accent/50 -mx-2 px-2 rounded"
                        onClick={() => handleGeneratePlan(p.reference)}
                      >
                        <div className="min-w-0">
                          <p className="text-sm font-mono font-medium text-primary">{p.reference}</p>
                          <p className="text-xs text-muted-foreground truncate">{p.name}</p>
                        </div>
                        <div className="text-right shrink-0">
                          {p.distance_miles != null && (
                            <p className="text-xs tabular-nums">{p.distance_miles.toFixed(0)} mi</p>
                          )}
                          <p className="text-xs text-muted-foreground">{p.activations} acts</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Plan panel */}
      <SlidePanel
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        title={plan ? `${plan.park?.reference} — ${plan.park?.name}` : "Activation Plan"}
      >
        {plan && (
          <div className="space-y-6">
            <div className="flex flex-wrap gap-4 text-sm">
              {plan.distance_miles != null && (
                <div>
                  <p className="text-xs text-muted-foreground">Distance</p>
                  <p className="font-semibold">{plan.distance_miles.toFixed(1)} mi</p>
                </div>
              )}
              {plan.bearing != null && (
                <div>
                  <p className="text-xs text-muted-foreground">Bearing</p>
                  <p className="font-semibold">{plan.bearing.toFixed(0)}&deg;</p>
                </div>
              )}
              <div>
                <p className="text-xs text-muted-foreground">Grid</p>
                <p className="font-semibold font-mono">{plan.park?.grid6 || plan.park?.grid4}</p>
              </div>
            </div>

            {plan.band_recommendations?.length > 0 && (
              <div>
                <p className="text-sm font-semibold mb-2">Band Recommendations</p>
                <div className="space-y-2">
                  {plan.band_recommendations.map((rec, i) => (
                    <div key={i} className="rounded-md border p-3 space-y-1">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline">{rec.band}</Badge>
                        <Badge variant="secondary">{rec.mode}</Badge>
                        <span className="text-xs text-muted-foreground">{rec.time_window}</span>
                      </div>
                      <p className="text-xs">{rec.rationale}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {plan.notes?.length > 0 && (
              <div>
                <p className="text-sm font-semibold mb-2">Notes</p>
                <ul className="list-disc list-inside space-y-1 text-xs text-muted-foreground">
                  {plan.notes.map((n, i) => <li key={i}>{n}</li>)}
                </ul>
              </div>
            )}

            {plan.nearby_parks?.length > 0 && (
              <div>
                <p className="text-sm font-semibold mb-2">Nearby Parks</p>
                <div className="space-y-1">
                  {plan.nearby_parks.slice(0, 5).map((p) => (
                    <div key={p.reference} className="flex items-center justify-between text-xs border rounded px-2 py-1">
                      <span className="font-mono font-medium text-primary">{p.reference}</span>
                      <span className="text-muted-foreground truncate ml-2">{p.name}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </SlidePanel>
    </div>
  )
}

export default POTA
