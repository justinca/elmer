import { useState, useMemo } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { queryKeys } from "@/lib/queryKeys"
import { STALE_TIMES } from "@/lib/queryClient"
import { useDocumentTitle } from "@/hooks/useDocumentTitle"
import { cn } from "@/lib/utils"
import { getPropagation, getPropForecast, getPropHistory } from "@/lib/api"
import { PageHeader } from "@/components/PageHeader"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Sun, Activity, Zap, Shield, Wind, TrendingUp, TrendingDown,
  Minus, RefreshCw, Clock,
} from "lucide-react"
import {
  ResponsiveContainer, ComposedChart, Line, Area,
  XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, Legend,
} from "recharts"
import { format } from "date-fns"

interface PropData {
  solar_flux: number | null
  sunspot_number: number | null
  a_index: number | null
  k_index: number | null
  x_ray_flux: string | null
  geomag_storm: string | null
  geomag_field: string | null
  signal_noise: string | null
  solar_wind: number | null
  bands: Record<string, { day: string; night: string }>
  updated: string | null
}

interface ForecastData {
  geomag_field: string | null
  signal_noise: string | null
  muf: string | null
  solar_flux_trend: string | null
  k_index_trend: string | null
  updated: string | null
}

interface HistoryPoint {
  timestamp: string
  solar_flux: number | null
  k_index: number | null
  a_index: number | null
}

const BAND_ORDER = ["160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m"]

function conditionColor(cond: string) {
  const c = cond?.toLowerCase()
  if (c === "good") return "bg-blue-500/15 text-blue-600 border-blue-500/30"
  if (c === "fair") return "bg-amber-500/15 text-amber-600 border-amber-500/30"
  if (c === "poor") return "bg-red-500/15 text-red-600 border-red-500/30"
  return "bg-muted text-muted-foreground"
}

function kColor(k: number | null) {
  if (k === null) return "text-muted-foreground"
  if (k < 3) return "text-blue-500"
  if (k <= 5) return "text-amber-500"
  return "text-red-500"
}

function aColor(a: number | null) {
  if (a === null) return "text-muted-foreground"
  if (a < 10) return "text-blue-500"
  if (a <= 20) return "text-amber-500"
  return "text-red-500"
}

function sfiColor(sfi: number | null) {
  if (sfi === null) return "text-muted-foreground"
  if (sfi >= 150) return "text-blue-500"
  if (sfi >= 100) return "text-amber-500"
  return "text-red-500"
}

function SolarCard({ label, value, icon: Icon, color, subtitle }: {
  label: string; value: string | number; icon: typeof Sun; color: string; subtitle?: string
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-muted-foreground">{label}</span>
          <Icon className="h-4 w-4 text-muted-foreground" />
        </div>
        <p className={cn("text-2xl font-bold tabular-nums mt-1", color)}>{value}</p>
        {subtitle && <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>}
      </CardContent>
    </Card>
  )
}

function Propagation() {
  useDocumentTitle("Propagation")
  const queryClient = useQueryClient()

  const [historyRange, setHistoryRange] = useState(24)

  const { data, isLoading: propLoading } = useQuery<PropData>({
    queryKey: queryKeys.propagation.current(),
    queryFn: () => getPropagation().then((r) => r.data),
    staleTime: STALE_TIMES.propagation,
    refetchInterval: 300_000,
  })

  const { data: forecast } = useQuery<ForecastData>({
    queryKey: queryKeys.propagation.forecast(),
    queryFn: () => getPropForecast().then((r) => r.data),
    staleTime: STALE_TIMES.propagation,
    refetchInterval: 300_000,
  })

  const { data: history = [] } = useQuery<HistoryPoint[]>({
    queryKey: queryKeys.propagation.history(historyRange),
    queryFn: () => getPropHistory(historyRange).then((r) => r.data || []),
    staleTime: STALE_TIMES.propagation,
  })

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.propagation.all })
  }

  const chartData = useMemo(() =>
    history.map((h) => ({
      time: h.timestamp ? format(new Date(h.timestamp), "HH:mm") : "",
      fullTime: h.timestamp ? format(new Date(h.timestamp), "MMM d HH:mm") : "",
      sfi: h.solar_flux,
      k: h.k_index,
    })),
    [history],
  )

  const isNight = new Date().getHours() < 6 || new Date().getHours() >= 18

  if (propLoading) {
    return (
      <div className="space-y-6">
        <PageHeader title="Propagation" description="HF band conditions and solar data" />
        <div className="grid gap-4 grid-cols-2 lg:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-24" />)}
        </div>
        <Skeleton className="h-64" />
        <Skeleton className="h-80" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Propagation"
        description="HF band conditions and solar data"
        actions={
          <Button variant="outline" size="sm" onClick={handleRefresh}>
            <RefreshCw className="mr-2 h-4 w-4" /> Refresh
          </Button>
        }
      />

      {/* Solar data cards */}
      <div className="grid gap-3 grid-cols-2 md:grid-cols-3 lg:grid-cols-6">
        <SolarCard
          label="Solar Flux (SFI)"
          value={data?.solar_flux ?? "—"}
          icon={Sun}
          color={sfiColor(data?.solar_flux ?? null)}
          subtitle={data?.solar_flux ? (data.solar_flux >= 100 ? "Good" : "Low") : undefined}
        />
        <SolarCard
          label="Sunspot Number"
          value={data?.sunspot_number ?? "—"}
          icon={Sun}
          color="text-foreground"
        />
        <SolarCard
          label="A-Index"
          value={data?.a_index ?? "—"}
          icon={Activity}
          color={aColor(data?.a_index ?? null)}
          subtitle={data?.a_index != null ? (data.a_index < 10 ? "Quiet" : data.a_index <= 20 ? "Unsettled" : "Storm") : undefined}
        />
        <SolarCard
          label="K-Index"
          value={data?.k_index ?? "—"}
          icon={Zap}
          color={kColor(data?.k_index ?? null)}
          subtitle={
            data?.k_index != null ? (
              <span className="flex items-center gap-1">
                <span
                  className={cn(
                    "inline-block h-2 rounded-full",
                    data.k_index < 3 ? "bg-blue-500" : data.k_index <= 5 ? "bg-amber-500" : "bg-red-500",
                  )}
                  style={{ width: `${Math.min((data.k_index / 9) * 100, 100)}%`, minWidth: "4px" }}
                />
              </span>
            ) as unknown as string : undefined
          }
        />
        <SolarCard
          label="X-Ray Flux"
          value={data?.x_ray_flux || "—"}
          icon={Shield}
          color="text-foreground"
        />
        <SolarCard
          label="Geomag Storm"
          value={data?.geomag_storm || "None"}
          icon={Wind}
          color={data?.geomag_storm && data.geomag_storm !== "None" ? "text-red-500" : "text-blue-500"}
        />
      </div>

      {/* Band conditions grid */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold">Band Conditions</CardTitle>
            <Badge variant="outline" className="text-xs">
              <Clock className="mr-1 h-3 w-3" />
              {isNight ? "Night" : "Day"} conditions active
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-[auto_1fr_1fr] gap-x-4 gap-y-1.5">
            <span className="text-xs font-semibold text-muted-foreground">Band</span>
            <span className="text-xs font-semibold text-muted-foreground text-center">Day</span>
            <span className="text-xs font-semibold text-muted-foreground text-center">Night</span>
            {BAND_ORDER.map((band) => {
              const cond = data?.bands?.[band]
              return (
                <div key={band} className="contents">
                  <span className="text-sm font-mono font-medium py-0.5">{band}</span>
                  <div className="flex justify-center">
                    <Badge
                      variant="outline"
                      className={cn(
                        "text-xs w-16 justify-center",
                        conditionColor(cond?.day || ""),
                        !isNight && "ring-1 ring-primary/30",
                      )}
                    >
                      {cond?.day || "—"}
                    </Badge>
                  </div>
                  <div className="flex justify-center">
                    <Badge
                      variant="outline"
                      className={cn(
                        "text-xs w-16 justify-center",
                        conditionColor(cond?.night || ""),
                        isNight && "ring-1 ring-primary/30",
                      )}
                    >
                      {cond?.night || "—"}
                    </Badge>
                  </div>
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>

      {/* History chart */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold">Propagation History</CardTitle>
            <div className="flex gap-1">
              {[24, 168, 720].map((h) => (
                <Button
                  key={h}
                  variant={historyRange === h ? "default" : "outline"}
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => setHistoryRange(h)}
                >
                  {h === 24 ? "24h" : h === 168 ? "7d" : "30d"}
                </Button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {chartData.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-12">
              No history data available
            </p>
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                  dataKey={historyRange <= 24 ? "time" : "fullTime"}
                  tick={{ fontSize: 11 }}
                  className="text-muted-foreground"
                  interval="preserveStartEnd"
                />
                <YAxis
                  yAxisId="sfi"
                  tick={{ fontSize: 11 }}
                  className="text-muted-foreground"
                  label={{ value: "SFI", angle: -90, position: "insideLeft", fontSize: 11 }}
                />
                <YAxis
                  yAxisId="k"
                  orientation="right"
                  domain={[0, 9]}
                  tick={{ fontSize: 11 }}
                  className="text-muted-foreground"
                  label={{ value: "K-Index", angle: 90, position: "insideRight", fontSize: 11 }}
                />
                <RTooltip
                  contentStyle={{
                    backgroundColor: "var(--card)",
                    border: "1px solid var(--border)",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                />
                <Legend wrapperStyle={{ fontSize: "12px" }} />
                <Line
                  yAxisId="sfi"
                  type="monotone"
                  dataKey="sfi"
                  stroke="#2563EB"
                  strokeWidth={2}
                  dot={false}
                  name="Solar Flux"
                />
                <Area
                  yAxisId="k"
                  type="stepAfter"
                  dataKey="k"
                  fill="rgba(239, 68, 68, 0.2)"
                  stroke="#ef4444"
                  strokeWidth={1}
                  name="K-Index"
                />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* Forecast */}
      {forecast && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">Forecast</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {forecast.geomag_field && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Geomagnetic Field</p>
                  <p className="text-sm mt-0.5">{forecast.geomag_field}</p>
                </div>
              )}
              {forecast.signal_noise && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Signal/Noise</p>
                  <p className="text-sm mt-0.5">{forecast.signal_noise}</p>
                </div>
              )}
              {forecast.solar_flux_trend && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">SFI Trend</p>
                  <p className="text-sm mt-0.5 flex items-center gap-1">
                    {forecast.solar_flux_trend.includes("above") ? (
                      <TrendingUp className="h-3.5 w-3.5 text-blue-500" />
                    ) : forecast.solar_flux_trend.includes("below") ? (
                      <TrendingDown className="h-3.5 w-3.5 text-red-500" />
                    ) : (
                      <Minus className="h-3.5 w-3.5 text-muted-foreground" />
                    )}
                    {forecast.solar_flux_trend}
                  </p>
                </div>
              )}
              {forecast.muf && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">MUF</p>
                  <p className="text-sm mt-0.5">{forecast.muf}</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Updated timestamp */}
      {data?.updated && (
        <p className="text-xs text-muted-foreground text-right">
          Last updated: {format(new Date(data.updated), "PPpp")}
        </p>
      )}
    </div>
  )
}

export default Propagation
