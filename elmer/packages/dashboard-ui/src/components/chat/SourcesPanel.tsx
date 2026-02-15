import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { BookOpen, Globe, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { SourceUsed, WebSource } from "./MessageBubble"

interface SourcesPanelProps {
  sources: SourceUsed[]
  webSources: WebSource[]
  onClose: () => void
}

export function SourcesPanel({ sources, webSources, onClose }: SourcesPanelProps) {
  const hasSources = sources.length > 0 || webSources.length > 0

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h3 className="text-sm font-semibold">Sources</h3>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>
      <ScrollArea className="flex-1">
        {!hasSources ? (
          <div className="p-4 text-center text-sm text-muted-foreground">
            Click "Used N sources" on a message to view its sources
          </div>
        ) : (
          <div className="space-y-4 p-4">
            {sources.length > 0 && (
              <div>
                <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted-foreground">
                  <BookOpen className="h-3.5 w-3.5" /> Knowledge Sources
                </div>
                <div className="space-y-3">
                  {sources.map((src, i) => (
                    <div key={i} className="space-y-1 rounded-md border p-3">
                      <div className="flex items-center justify-between gap-2">
                        <Badge variant="outline" className="text-xs">
                          {src.source}
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                          {(src.score * 100).toFixed(0)}%
                        </span>
                      </div>
                      <Progress value={src.score * 100} className="h-1" />
                      {src.source_path && (
                        <p className="text-xs text-muted-foreground">{src.source_path}</p>
                      )}
                      {src.snippet && (
                        <p className="text-xs text-foreground/80">{src.snippet}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {webSources.length > 0 && (
              <div>
                <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted-foreground">
                  <Globe className="h-3.5 w-3.5" /> Web Sources
                </div>
                <div className="space-y-3">
                  {webSources.map((src, i) => (
                    <div key={i} className="space-y-1 rounded-md border p-3">
                      <a
                        href={src.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm font-medium text-primary hover:underline"
                      >
                        {src.title}
                      </a>
                      <p className="text-xs text-muted-foreground break-all">{src.url}</p>
                      {src.snippet && (
                        <p className="text-xs text-foreground/80">{src.snippet}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </ScrollArea>
    </div>
  )
}
