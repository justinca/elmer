import { useState, useEffect } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { queryKeys } from "@/lib/queryKeys"
import { STALE_TIMES } from "@/lib/queryClient"
import { useDocumentTitle } from "@/hooks/useDocumentTitle"
import { cn } from "@/lib/utils"
import { getDxSummary, getBands } from "@/lib/api"
import { PageHeader } from "@/components/PageHeader"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import {
  Play, Pause, SkipForward, RefreshCw, Activity,
} from "lucide-react"
import { format } from "date-fns"

interface BandActivity {
  band: string
  spots: number
  condition_day: string
  condition_night: string
}

interface ScanEntry {
  id: number
  time: Date
  band: string
  frequency: number
}

const SCAN_BANDS = ["80m", "40m", "30m", "20m", "17m", "15m", "12m", "10m"]
const BAND_FREQS: Record<string, number> = {
  "80m": 3573, "40m": 7074, "30m": 10136, "20m": 14074,
  "17m": 18100, "15m": 21074, "12m": 24915, "10m": 28074,
}
const DWELL_OPTIONS = [5, 10, 15, 20, 30]

function BandScanner() {
  useDocumentTitle("Band Scanner")
  const queryClient = useQueryClient()

  const [scanning, setScanning] = useState(false)
  const [currentBandIdx, setCurrentBandIdx] = useState(0)
  const [dwellMinutes, setDwellMinutes] = useState(10)
  const [dwellRemaining, setDwellRemaining] = useState(0)
  const [scanLog, setScanLog] = useState<ScanEntry[]>([])
  const [manualFreq, setManualFreq] = useState("")

  const currentBand = SCAN_BANDS[currentBandIdx]
  const currentFreq = BAND_FREQS[currentBand] || 14074

  const { data: summaryData } = useQuery<{ bands: Record<string, number> } | null>({
    queryKey: queryKeys.dx.summary(),
    queryFn: () => getDxSummary().then((r) => r.data),
    staleTime: STALE_TIMES.bandScanner,
    refetchInterval: 30_000,
  })

  const { data: bandsData } = useQuery<Record<string, { day?: string; night?: string }> | null>({
    queryKey: queryKeys.propagation.bands(),
    queryFn: () => getBands().then((r) => r.data),
    staleTime: STALE_TIMES.bandScanner,
    refetchInterval: 30_000,
  })

  const bandActivity: BandActivity[] = SCAN_BANDS.map((b) => {
    const spots = summaryData?.bands?.[b] || 0
    const cond = bandsData?.[b]
    return {
      band: b,
      spots,
      condition_day: cond?.day || "—",
      condition_night: cond?.night || "—",
    }
  })

  const isActivityLoading = !summaryData && !bandsData

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.dx.summary() })
    queryClient.invalidateQueries({ queryKey: queryKeys.propagation.bands() })
  }

  // Scan timer
  useEffect(() => {
    if (!scanning) return
    setDwellRemaining(dwellMinutes * 60)

    const id = setInterval(() => {
      setDwellRemaining((prev) => {
        if (prev <= 1) {
          // Move to next band
          setCurrentBandIdx((idx) => {
            const nextIdx = (idx + 1) % SCAN_BANDS.length
            const nextBand = SCAN_BANDS[nextIdx]
            setScanLog((log) => [
              { id: Date.now(), time: new Date(), band: nextBand, frequency: BAND_FREQS[nextBand] },
              ...log.slice(0, 49),
            ])
            return nextIdx
          })
          return dwellMinutes * 60
        }
        return prev - 1
      })
    }, 1000)
    return () => clearInterval(id)
  }, [scanning, dwellMinutes])

  const handleStart = () => {
    setScanning(true)
    setScanLog((log) => [
      { id: Date.now(), time: new Date(), band: currentBand, frequency: currentFreq },
      ...log.slice(0, 49),
    ])
  }

  const handleStop = () => {
    setScanning(false)
    setDwellRemaining(0)
  }

  const handleSkip = () => {
    const nextIdx = (currentBandIdx + 1) % SCAN_BANDS.length
    setCurrentBandIdx(nextIdx)
    setDwellRemaining(dwellMinutes * 60)
    const nextBand = SCAN_BANDS[nextIdx]
    setScanLog((log) => [
      { id: Date.now(), time: new Date(), band: nextBand, frequency: BAND_FREQS[nextBand] },
      ...log.slice(0, 49),
    ])
  }

  const handleTune = (band: string) => {
    const idx = SCAN_BANDS.indexOf(band)
    if (idx >= 0) {
      setCurrentBandIdx(idx)
      if (scanning) setDwellRemaining(dwellMinutes * 60)
      setScanLog((log) => [
        { id: Date.now(), time: new Date(), band, frequency: BAND_FREQS[band] },
        ...log.slice(0, 49),
      ])
    }
  }

  const handleManualTune = () => {
    const freq = parseFloat(manualFreq)
    if (isNaN(freq) || freq < 1000) return
    // Find closest band
    let closestBand = "20m"
    let closestDist = Infinity
    Object.entries(BAND_FREQS).forEach(([b, f]) => {
      const dist = Math.abs(freq - f)
      if (dist < closestDist) { closestDist = dist; closestBand = b }
    })
    const idx = SCAN_BANDS.indexOf(closestBand)
    if (idx >= 0) setCurrentBandIdx(idx)
    setScanLog((log) => [
      { id: Date.now(), time: new Date(), band: closestBand, frequency: freq },
      ...log.slice(0, 49),
    ])
    setManualFreq("")
  }

  const formatRemaining = (s: number) => {
    const m = Math.floor(s / 60)
    const sec = s % 60
    return `${m}:${sec.toString().padStart(2, "0")}`
  }

  const isNight = new Date().getHours() < 6 || new Date().getHours() >= 18

  return (
    <div className="space-y-6">
      <PageHeader
        title="Band Scanner"
        description="Automated HF band scanning and monitoring"
        actions={
          <Button variant="outline" size="sm" onClick={handleRefresh}>
            <RefreshCw className="mr-2 h-4 w-4" /> Refresh
          </Button>
        }
      />

      {/* Current status */}
      <Card className={cn(scanning && "border-primary/50")}>
        <CardContent className="p-6">
          <div className="flex flex-col items-center gap-4 sm:flex-row sm:justify-between">
            <div className="text-center sm:text-left">
              <div className="flex items-center gap-3">
                {scanning && (
                  <span className="relative flex h-3 w-3">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75" />
                    <span className="relative inline-flex h-3 w-3 rounded-full bg-primary" />
                  </span>
                )}
                <p className="text-4xl font-bold tabular-nums font-mono">
                  {currentFreq.toFixed(0)} kHz
                </p>
              </div>
              <div className="flex items-center gap-2 mt-1">
                <Badge variant="outline" className="text-lg px-3">{currentBand}</Badge>
                {scanning && (
                  <span className="text-sm text-muted-foreground tabular-nums">
                    {formatRemaining(dwellRemaining)} remaining
                  </span>
                )}
              </div>
            </div>

            {/* Controls */}
            <div className="flex items-center gap-2">
              {!scanning ? (
                <Button onClick={handleStart}>
                  <Play className="mr-2 h-4 w-4" /> Start Scan
                </Button>
              ) : (
                <>
                  <Button variant="outline" onClick={handleStop}>
                    <Pause className="mr-2 h-4 w-4" /> Stop
                  </Button>
                  <Button variant="outline" onClick={handleSkip}>
                    <SkipForward className="mr-2 h-4 w-4" /> Skip
                  </Button>
                </>
              )}
            </div>
          </div>

          {/* Scan order visualization */}
          <div className="mt-6">
            <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
              {SCAN_BANDS.map((band, idx) => (
                <button
                  key={band}
                  onClick={() => handleTune(band)}
                  className={cn(
                    "flex flex-col items-center rounded-lg border px-3 py-2 transition-all min-w-[60px]",
                    idx === currentBandIdx
                      ? "border-primary bg-primary/10 ring-2 ring-primary/30"
                      : "hover:bg-accent/50",
                    idx < currentBandIdx && scanning && "opacity-50",
                  )}
                >
                  <span className="text-xs font-semibold">{band}</span>
                  <span className="text-[10px] text-muted-foreground tabular-nums">
                    {BAND_FREQS[band]}
                  </span>
                </button>
              ))}
            </div>
            {scanning && (
              <div className="mt-2 h-1 rounded-full bg-muted overflow-hidden">
                <div
                  className="h-full bg-primary transition-all duration-1000"
                  style={{
                    width: `${((currentBandIdx + (1 - dwellRemaining / (dwellMinutes * 60))) / SCAN_BANDS.length) * 100}%`,
                  }}
                />
              </div>
            )}
          </div>

          {/* Dwell time selector */}
          <div className="mt-4 flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Dwell:</span>
            {DWELL_OPTIONS.map((d) => (
              <Button
                key={d}
                variant={dwellMinutes === d ? "default" : "outline"}
                size="sm"
                className="h-7 text-xs"
                onClick={() => setDwellMinutes(d)}
              >
                {d}m
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Band activity */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Activity className="h-4 w-4" /> Band Activity
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isActivityLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-8" />)}
              </div>
            ) : (
              <div className="space-y-1.5">
                {bandActivity.map((b) => (
                  <div
                    key={b.band}
                    className={cn(
                      "flex items-center gap-3 rounded-md px-3 py-1.5 cursor-pointer hover:bg-accent/50",
                      b.band === currentBand && "bg-primary/10",
                    )}
                    onClick={() => handleTune(b.band)}
                  >
                    <span className="text-sm font-mono w-10 font-medium">{b.band}</span>
                    <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full bg-primary rounded-full transition-all"
                        style={{ width: `${Math.min((b.spots / 20) * 100, 100)}%` }}
                      />
                    </div>
                    <span className="text-xs tabular-nums w-8 text-right text-muted-foreground">
                      {b.spots}
                    </span>
                    <Badge
                      variant="outline"
                      className={cn(
                        "text-[10px] w-12 justify-center",
                        (isNight ? b.condition_night : b.condition_day).toLowerCase() === "good"
                          ? "text-blue-500"
                          : (isNight ? b.condition_night : b.condition_day).toLowerCase() === "fair"
                            ? "text-amber-500"
                            : "text-red-500",
                      )}
                    >
                      {isNight ? b.condition_night : b.condition_day}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          {/* Manual tune */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Manual Tune</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex gap-1">
                <Input
                  value={manualFreq}
                  onChange={(e) => setManualFreq(e.target.value)}
                  placeholder="Frequency (kHz)"
                  type="number"
                  className="font-mono"
                  onKeyDown={(e) => e.key === "Enter" && handleManualTune()}
                />
                <Button onClick={handleManualTune}>Tune</Button>
              </div>
              <div className="flex flex-wrap gap-1">
                {["80m", "40m", "20m", "15m", "10m"].map((b) => (
                  <Button
                    key={b}
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => handleTune(b)}
                  >
                    {b}
                  </Button>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Scan history */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Scan History</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <ScrollArea className="h-[280px]">
                {scanLog.length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-8">
                    Start scanning to see history
                  </p>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs">Time</TableHead>
                        <TableHead className="text-xs">Band</TableHead>
                        <TableHead className="text-xs">Freq (kHz)</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {scanLog.map((entry) => (
                        <TableRow key={entry.id}>
                          <TableCell className="text-xs text-muted-foreground tabular-nums">
                            {format(entry.time, "HH:mm:ss")}
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline" className="text-xs">{entry.band}</Badge>
                          </TableCell>
                          <TableCell className="text-xs font-mono tabular-nums">{entry.frequency}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </ScrollArea>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}

export default BandScanner
