import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { TableCell, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { MarkdownRenderer } from "@/components/MarkdownRenderer"
import { cn } from "@/lib/utils"
import { ChevronRight } from "lucide-react"
import { formatDistanceToNow } from "date-fns"

interface RunSummary {
  id: number
  agent_name: string
  trigger_type: string
  status: string
  started_at: string | null
  completed_at: string | null
  duration_seconds: number | null
}

interface RunDetail {
  input_data?: Record<string, unknown>
  output_data?: Record<string, unknown>
  trigger_data?: Record<string, unknown>
  error?: string | null
}

interface RunRowProps {
  run: RunSummary
  expanded: boolean
  onToggle: () => void
  detail: RunDetail | null
  loadingDetail: boolean
}

const statusColors: Record<string, string> = {
  completed: "bg-blue-500/10 text-blue-600 border-blue-500/20",
  failed: "bg-destructive/10 text-destructive border-destructive/20",
  timeout: "bg-amber-500/10 text-amber-600 border-amber-500/20",
  running: "bg-blue-500/10 text-blue-600 border-blue-500/20",
  pending: "bg-muted text-muted-foreground",
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "-"
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}m ${s}s`
}

export function RunRow({ run, expanded, onToggle, detail, loadingDetail }: RunRowProps) {
  return (
    <Collapsible open={expanded} onOpenChange={onToggle} asChild>
      <>
        <CollapsibleTrigger asChild>
          <TableRow className="cursor-pointer hover:bg-accent/50">
            <TableCell className="w-8">
              <ChevronRight
                className={cn("h-4 w-4 transition-transform", expanded && "rotate-90")}
              />
            </TableCell>
            <TableCell className="font-medium">{run.agent_name}</TableCell>
            <TableCell>
              <Badge variant="outline" className="text-xs capitalize">
                {run.trigger_type}
              </Badge>
            </TableCell>
            <TableCell>
              <Badge variant="outline" className={cn("text-xs capitalize", statusColors[run.status])}>
                {run.status}
              </Badge>
            </TableCell>
            <TableCell className="text-sm text-muted-foreground">
              {run.started_at
                ? formatDistanceToNow(new Date(run.started_at), { addSuffix: true })
                : "-"}
            </TableCell>
            <TableCell className="text-sm tabular-nums">
              {formatDuration(run.duration_seconds)}
            </TableCell>
          </TableRow>
        </CollapsibleTrigger>
        <CollapsibleContent asChild>
          <TableRow className="bg-muted/30 hover:bg-muted/30">
            <TableCell colSpan={6} className="p-4">
              {loadingDetail ? (
                <div className="space-y-2">
                  <Skeleton className="h-4 w-48" />
                  <Skeleton className="h-20 w-full" />
                </div>
              ) : detail ? (
                <div className="space-y-4">
                  {/* Error */}
                  {detail.error && (
                    <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3">
                      <p className="text-sm font-medium text-destructive">Error</p>
                      <p className="text-sm text-destructive/80 whitespace-pre-wrap">{detail.error}</p>
                    </div>
                  )}

                  {/* Output */}
                  {detail.output_data && Object.keys(detail.output_data).length > 0 && (
                    <div>
                      <p className="text-xs font-semibold uppercase text-muted-foreground mb-1">Output</p>
                      {typeof detail.output_data.response === "string" ? (
                        <div className="rounded-md border p-3">
                          <MarkdownRenderer content={detail.output_data.response} />
                        </div>
                      ) : (
                        <pre className="text-xs bg-muted rounded-md p-3 overflow-auto max-h-64">
                          {JSON.stringify(detail.output_data, null, 2)}
                        </pre>
                      )}
                    </div>
                  )}

                  {/* Tool calls */}
                  {Array.isArray(detail.output_data?.tool_calls_made) &&
                    (detail.output_data.tool_calls_made as string[]).length > 0 && (
                      <div>
                        <p className="text-xs font-semibold uppercase text-muted-foreground mb-1">
                          Tool Calls
                        </p>
                        <div className="flex flex-wrap gap-1">
                          {(detail.output_data.tool_calls_made as string[]).map((t, i) => (
                            <Badge key={i} variant="secondary" className="text-xs">
                              {String(t)}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}

                  {/* Input data */}
                  {detail.input_data && Object.keys(detail.input_data).length > 0 && (
                    <div>
                      <p className="text-xs font-semibold uppercase text-muted-foreground mb-1">Input</p>
                      <pre className="text-xs bg-muted rounded-md p-3 overflow-auto max-h-40">
                        {JSON.stringify(detail.input_data, null, 2)}
                      </pre>
                    </div>
                  )}

                  {/* Trigger data */}
                  {detail.trigger_data && Object.keys(detail.trigger_data).length > 0 && (
                    <div>
                      <p className="text-xs font-semibold uppercase text-muted-foreground mb-1">Trigger Data</p>
                      <pre className="text-xs bg-muted rounded-md p-3 overflow-auto max-h-40">
                        {JSON.stringify(detail.trigger_data, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No detail available</p>
              )}
            </TableCell>
          </TableRow>
        </CollapsibleContent>
      </>
    </Collapsible>
  )
}
