import { useState, useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { queryKeys } from "@/lib/queryKeys"
import { STALE_TIMES } from "@/lib/queryClient"
import { getDeviceInventory, getServiceCatalog } from "@/lib/api"
import { mapStatus } from "@/lib/utils"
import { useDocumentTitle } from "@/hooks/useDocumentTitle"
import { PageHeader } from "@/components/PageHeader"
import { StatCard } from "@/components/StatCard"
import { StatusDot } from "@/components/StatusDot"
import { SlidePanel } from "@/components/SlidePanel"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Server, Cpu, HardDrive, MemoryStick, RefreshCw } from "lucide-react"
import { useQueryClient } from "@tanstack/react-query"
import { formatDistanceToNow } from "date-fns"

interface DeviceInfo {
  node_id: string
  name: string
  node_type: string
  status: string
  host: string
  port: number
  platform: string
  hostname: string
  cpu_percent: number | null
  ram_total_gb: number | null
  ram_used_gb: number | null
  disk_total_gb: number | null
  disk_used_gb: number | null
  last_seen: string | null
  metadata: Record<string, unknown>
}

interface ServiceInfo {
  name: string
  device: string
  host: string
  port: number
  status: string
  container: string
  health_endpoint: string
}

export default function Services() {
  useDocumentTitle("Services")
  const queryClient = useQueryClient()

  const [panelService, setPanelService] = useState<ServiceInfo | null>(null)
  const [panelOpen, setPanelOpen] = useState(false)

  const { data: inventoryData, isLoading: invLoading } = useQuery({
    queryKey: queryKeys.services.inventory(),
    queryFn: () => getDeviceInventory().then((r) => r.data),
    staleTime: STALE_TIMES.health,
    refetchInterval: 30_000,
  })

  const { data: catalogData, isLoading: catLoading } = useQuery({
    queryKey: queryKeys.services.catalog(),
    queryFn: () => getServiceCatalog().then((r) => r.data),
    staleTime: STALE_TIMES.health,
    refetchInterval: 30_000,
  })

  const devices: DeviceInfo[] = inventoryData?.devices || inventoryData || []
  const services: ServiceInfo[] = catalogData?.services || catalogData || []
  const loading = invLoading || catLoading

  const grouped = useMemo(() => {
    const groups: Record<string, DeviceInfo[]> = {}
    for (const d of devices) {
      const key = d.host || d.hostname || "unknown"
      if (!groups[key]) groups[key] = []
      groups[key].push(d)
    }
    return groups
  }, [devices])

  const healthyDevices = devices.filter((d) => mapStatus(d.status) === "healthy").length
  const healthyServices = services.filter((s) => mapStatus(s.status) === "healthy").length

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.services.all })
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Services"
        description="Service inventory, device health, and system catalog"
        actions={
          <Button variant="outline" size="sm" onClick={handleRefresh}>
            <RefreshCw className="mr-2 h-4 w-4" /> Refresh
          </Button>
        }
      />

      {/* Summary cards */}
      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Devices" value={devices.length} icon={Server} />
          <StatCard label="Services" value={services.length} icon={Cpu} />
          <StatCard
            label="Devices Healthy"
            value={`${healthyDevices}/${devices.length}`}
            icon={HardDrive}
            subtitle={healthyDevices === devices.length ? "All healthy" : `${devices.length - healthyDevices} issue(s)`}
          />
          <StatCard
            label="Services Healthy"
            value={`${healthyServices}/${services.length}`}
            icon={MemoryStick}
            subtitle={healthyServices === services.length ? "All healthy" : `${services.length - healthyServices} issue(s)`}
          />
        </div>
      )}

      {/* Device cards grouped by host */}
      {!loading && Object.keys(grouped).length > 0 && (
        <div className="space-y-4">
          {Object.entries(grouped).map(([host, hostDevices]) => (
            <div key={host}>
              <h3 className="mb-2 text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                {host}
              </h3>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {hostDevices.map((device) => {
                  const ramPct =
                    device.ram_total_gb && device.ram_used_gb
                      ? (device.ram_used_gb / device.ram_total_gb) * 100
                      : null
                  const diskPct =
                    device.disk_total_gb && device.disk_used_gb
                      ? (device.disk_used_gb / device.disk_total_gb) * 100
                      : null

                  return (
                    <Card key={device.node_id}>
                      <CardHeader className="pb-2">
                        <div className="flex items-center justify-between">
                          <CardTitle className="text-sm flex items-center gap-2">
                            <StatusDot status={mapStatus(device.status)} size="sm" />
                            {device.name}
                          </CardTitle>
                          <Badge variant="outline" className="text-xs">
                            {device.node_type}
                          </Badge>
                        </div>
                      </CardHeader>
                      <CardContent className="space-y-2">
                        {device.platform && (
                          <p className="text-xs text-muted-foreground">{device.platform}</p>
                        )}
                        {device.cpu_percent != null && (
                          <div>
                            <div className="flex items-center justify-between text-xs mb-1">
                              <span>CPU</span>
                              <span className="tabular-nums">{device.cpu_percent.toFixed(0)}%</span>
                            </div>
                            <Progress value={device.cpu_percent} className="h-1.5" />
                          </div>
                        )}
                        {ramPct != null && (
                          <div>
                            <div className="flex items-center justify-between text-xs mb-1">
                              <span>RAM</span>
                              <span className="tabular-nums">
                                {device.ram_used_gb?.toFixed(1)}/{device.ram_total_gb?.toFixed(1)} GB
                              </span>
                            </div>
                            <Progress value={ramPct} className="h-1.5" />
                          </div>
                        )}
                        {diskPct != null && (
                          <div>
                            <div className="flex items-center justify-between text-xs mb-1">
                              <span>Disk</span>
                              <span className="tabular-nums">
                                {device.disk_used_gb?.toFixed(0)}/{device.disk_total_gb?.toFixed(0)} GB
                              </span>
                            </div>
                            <Progress value={diskPct} className="h-1.5" />
                          </div>
                        )}
                        {device.last_seen && (
                          <p className="text-xs text-muted-foreground">
                            Seen {formatDistanceToNow(new Date(device.last_seen), { addSuffix: true })}
                          </p>
                        )}
                      </CardContent>
                    </Card>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Service catalog table */}
      {!loading && services.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Service Catalog</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Service</TableHead>
                  <TableHead className="text-xs">Device</TableHead>
                  <TableHead className="text-xs">Host:Port</TableHead>
                  <TableHead className="text-xs">Status</TableHead>
                  <TableHead className="text-xs">Container</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {services.map((svc) => (
                  <TableRow
                    key={svc.name}
                    className="cursor-pointer"
                    onClick={() => {
                      setPanelService(svc)
                      setPanelOpen(true)
                    }}
                  >
                    <TableCell className="text-sm font-medium">{svc.name}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{svc.device}</TableCell>
                    <TableCell className="text-xs font-mono">
                      {svc.host}:{svc.port}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <StatusDot status={mapStatus(svc.status)} size="sm" />
                        <span className="text-xs">{svc.status}</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{svc.container || "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {!loading && devices.length === 0 && services.length === 0 && (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            No service inventory data available — the system documentor may not have run yet
          </CardContent>
        </Card>
      )}

      {/* Service detail panel */}
      <SlidePanel
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        title={panelService?.name || "Service"}
      >
        {panelService && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-muted-foreground">Device</p>
                <p className="text-sm font-medium">{panelService.device}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Status</p>
                <div className="flex items-center gap-2">
                  <StatusDot status={mapStatus(panelService.status)} size="sm" />
                  <span className="text-sm">{panelService.status}</span>
                </div>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Host</p>
                <p className="text-sm font-mono">{panelService.host}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Port</p>
                <p className="text-sm font-mono">{panelService.port}</p>
              </div>
            </div>
            {panelService.container && (
              <div>
                <p className="text-xs text-muted-foreground">Container</p>
                <p className="text-sm font-mono">{panelService.container}</p>
              </div>
            )}
            {panelService.health_endpoint && (
              <div>
                <p className="text-xs text-muted-foreground">Health Endpoint</p>
                <p className="text-sm font-mono">{panelService.health_endpoint}</p>
              </div>
            )}
          </div>
        )}
      </SlidePanel>
    </div>
  )
}
