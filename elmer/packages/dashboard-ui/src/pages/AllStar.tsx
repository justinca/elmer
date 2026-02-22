import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { queryKeys } from "@/lib/queryKeys"
import { STALE_TIMES } from "@/lib/queryClient"
import { useDocumentTitle } from "@/hooks/useDocumentTitle"
import { cn } from "@/lib/utils"
import {
  getAllstarStatus,
  getAllstarConnections,
  getAllstarNodeInfo,
  postAllstarConnect,
  postAllstarDisconnect,
  postAllstarMonitor,
} from "@/lib/api"
import { PageHeader } from "@/components/PageHeader"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  RefreshCw, Radio, Link, Unlink, Headphones, Search,
  Activity, Mic, MicOff,
} from "lucide-react"
import { toast } from "sonner"

interface NodeStats {
  online: boolean
  uptime_seconds: number
  total_keyups: number
  total_tx_time: number
  total_kerchunks: number
  keyed: boolean
  version: string
  last_update: string
}

interface LinkedNode {
  node: number
  callsign: string
  description: string
  location: string
}

interface AllStarStatus {
  node: number
  callsign: string
  location: string
  latitude: string
  longitude: string
  stats: NodeStats
  connections: LinkedNode[]
  updated: string
}

interface NodeInfo {
  node: number
  callsign: string
  description: string
  location: string
}

function formatUptime(seconds: number): string {
  if (!seconds) return "—"
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return `${d}d ${h}h ${m}m`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

function formatTxTime(seconds: number): string {
  if (!seconds) return "0s"
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

function StatCard({ label, value, icon: Icon, subtitle }: {
  label: string; value: string | number; icon: typeof Activity; subtitle?: string
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-muted-foreground">{label}</span>
          <Icon className="h-4 w-4 text-muted-foreground" />
        </div>
        <p className="text-2xl font-bold tabular-nums mt-1">{value}</p>
        {subtitle && <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>}
      </CardContent>
    </Card>
  )
}

function AllStar() {
  useDocumentTitle("AllStar")
  const queryClient = useQueryClient()

  const [connectNode, setConnectNode] = useState("")
  const [lookupNode, setLookupNode] = useState("")
  const [lookupResult, setLookupResult] = useState<NodeInfo | null>(null)
  const [lookupError, setLookupError] = useState("")

  const { data: status, isLoading } = useQuery<AllStarStatus>({
    queryKey: queryKeys.allstar.status(),
    queryFn: () => getAllstarStatus().then((r) => r.data),
    staleTime: STALE_TIMES.allstar,
    refetchInterval: 30_000,
  })

  const { data: connections = [] } = useQuery<LinkedNode[]>({
    queryKey: queryKeys.allstar.connections(),
    queryFn: () => getAllstarConnections().then((r) => r.data),
    staleTime: STALE_TIMES.allstar,
    refetchInterval: 30_000,
  })

  const handleRefresh = () => {
    // Fetch with refresh=true to bust server-side cache, then update query cache
    getAllstarStatus({ refresh: true }).then((r) => {
      queryClient.setQueryData(queryKeys.allstar.status(), r.data)
    })
    getAllstarConnections({ refresh: true }).then((r) => {
      queryClient.setQueryData(queryKeys.allstar.connections(), r.data)
    })
  }

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.allstar.all })
  }

  const connectMutation = useMutation({
    mutationFn: (node: number) => postAllstarConnect({ node }),
    onSuccess: (_, node) => {
      toast.success(`Connect command sent to node ${node}`)
      invalidateAll()
    },
    onError: () => toast.error("Connect failed"),
  })

  const disconnectMutation = useMutation({
    mutationFn: (node: number) => postAllstarDisconnect({ node }),
    onSuccess: (_, node) => {
      toast.success(`Disconnect command sent for node ${node}`)
      invalidateAll()
    },
    onError: () => toast.error("Disconnect failed"),
  })

  const monitorMutation = useMutation({
    mutationFn: (node: number) => postAllstarMonitor({ node }),
    onSuccess: (_, node) => {
      toast.success(`Monitor command sent for node ${node}`)
      invalidateAll()
    },
    onError: () => toast.error("Monitor failed"),
  })

  const handleConnect = () => {
    const n = parseInt(connectNode)
    if (n && n >= 1000) {
      connectMutation.mutate(n)
      setConnectNode("")
    }
  }

  const handleMonitor = () => {
    const n = parseInt(connectNode)
    if (n && n >= 1000) {
      monitorMutation.mutate(n)
      setConnectNode("")
    }
  }

  const handleDisconnectInput = () => {
    const n = parseInt(connectNode)
    if (n && n >= 1000) {
      disconnectMutation.mutate(n)
      setConnectNode("")
    }
  }

  const handleLookup = async () => {
    const n = parseInt(lookupNode)
    if (!n || n < 1000) return
    setLookupError("")
    setLookupResult(null)
    try {
      const resp = await getAllstarNodeInfo(n)
      setLookupResult(resp.data)
    } catch {
      setLookupError(`Node ${n} not found in directory`)
    }
  }

  const stats = status?.stats
  const online = stats?.online ?? false

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader title="AllStar" description="AllStarLink node status and control" />
        <Skeleton className="h-32" />
        <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24" />)}
        </div>
        <Skeleton className="h-48" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="AllStar"
        description="AllStarLink node status and control"
        actions={
          <Button variant="outline" size="sm" onClick={handleRefresh}>
            <RefreshCw className="mr-2 h-4 w-4" /> Refresh
          </Button>
        }
      />

      {/* Node status header card */}
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className={cn(
                "flex h-12 w-12 items-center justify-center rounded-full",
                online ? "bg-blue-500/15" : "bg-red-500/15",
              )}>
                <Radio className={cn("h-6 w-6", online ? "text-blue-500" : "text-red-500")} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-lg font-bold">Node {status?.node ?? "68498"}</h2>
                  <Badge variant={online ? "default" : "destructive"} className="text-xs">
                    {online ? "Online" : "Offline"}
                  </Badge>
                  {stats?.keyed && (
                    <Badge variant="outline" className="text-xs bg-red-500/15 text-red-600 border-red-500/30">
                      TX
                    </Badge>
                  )}
                </div>
                <p className="text-sm text-muted-foreground">
                  {status?.callsign ?? "W0ABE"} — {status?.location ?? ""}
                </p>
              </div>
            </div>
            <div className="text-right text-sm text-muted-foreground">
              <p>Uptime: {formatUptime(stats?.uptime_seconds ?? 0)}</p>
              <p className="text-xs">ASL v{stats?.version || "?"}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Stats cards */}
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Total Keyups"
          value={(stats?.total_keyups ?? 0).toLocaleString()}
          icon={Mic}
        />
        <StatCard
          label="TX Time"
          value={formatTxTime(stats?.total_tx_time ?? 0)}
          icon={Activity}
        />
        <StatCard
          label="Kerchunks"
          value={(stats?.total_kerchunks ?? 0).toLocaleString()}
          icon={MicOff}
        />
        <StatCard
          label="Status"
          value={stats?.keyed ? "Transmitting" : "Idle"}
          icon={stats?.keyed ? Mic : Radio}
          subtitle={stats?.keyed ? "Node is currently keyed" : "Standing by"}
        />
      </div>

      {/* Connected nodes */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Link className="h-4 w-4" />
              Connected Nodes
            </CardTitle>
            <Badge variant="outline" className="text-xs">
              {connections.length} connected
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          {connections.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">
              No connected nodes
            </p>
          ) : (
            <div className="space-y-2">
              {connections.map((c) => (
                <div
                  key={c.node}
                  className="flex items-center justify-between rounded-md border p-3"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-semibold">{c.node}</span>
                      {c.callsign && (
                        <Badge variant="outline" className="text-xs">{c.callsign}</Badge>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {c.description}{c.location ? ` — ${c.location}` : ""}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-red-500 hover:text-red-600 hover:bg-red-500/10"
                    onClick={() => disconnectMutation.mutate(c.node)}
                    disabled={disconnectMutation.isPending}
                  >
                    <Unlink className="h-4 w-4 mr-1" />
                    Disconnect
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Connect / Control */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold">Node Control</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            <Input
              placeholder="Enter node number..."
              value={connectNode}
              onChange={(e) => setConnectNode(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleConnect()}
              className="max-w-48 font-mono"
              type="number"
            />
            <Button
              size="sm"
              onClick={handleConnect}
              disabled={!connectNode || connectMutation.isPending}
            >
              <Link className="h-4 w-4 mr-1" />
              Connect
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={handleMonitor}
              disabled={!connectNode || monitorMutation.isPending}
            >
              <Headphones className="h-4 w-4 mr-1" />
              Monitor
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="text-red-500 hover:text-red-600"
              onClick={handleDisconnectInput}
              disabled={!connectNode || disconnectMutation.isPending}
            >
              <Unlink className="h-4 w-4 mr-1" />
              Disconnect
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Node Lookup */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold">Node Lookup</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2 mb-3">
            <Input
              placeholder="Node number..."
              value={lookupNode}
              onChange={(e) => setLookupNode(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleLookup()}
              className="max-w-48 font-mono"
              type="number"
            />
            <Button size="sm" variant="outline" onClick={handleLookup} disabled={!lookupNode}>
              <Search className="h-4 w-4 mr-1" />
              Lookup
            </Button>
          </div>
          {lookupResult && (
            <div className="rounded-md border p-3">
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-semibold">{lookupResult.node}</span>
                    {lookupResult.callsign && (
                      <Badge variant="outline" className="text-xs">{lookupResult.callsign}</Badge>
                    )}
                  </div>
                  <p className="text-sm">{lookupResult.description}</p>
                  <p className="text-xs text-muted-foreground">{lookupResult.location}</p>
                </div>
                <div className="flex gap-1">
                  <Button
                    size="sm"
                    onClick={() => connectMutation.mutate(lookupResult.node)}
                    disabled={connectMutation.isPending}
                  >
                    <Link className="h-4 w-4 mr-1" /> Connect
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => monitorMutation.mutate(lookupResult.node)}
                    disabled={monitorMutation.isPending}
                  >
                    <Headphones className="h-4 w-4 mr-1" /> Monitor
                  </Button>
                </div>
              </div>
            </div>
          )}
          {lookupError && (
            <p className="text-sm text-muted-foreground">{lookupError}</p>
          )}
        </CardContent>
      </Card>

      {/* Updated timestamp */}
      {status?.updated && (
        <p className="text-xs text-muted-foreground text-right">
          Last updated: {new Date(status.updated).toLocaleString()}
        </p>
      )}
    </div>
  )
}

export default AllStar
