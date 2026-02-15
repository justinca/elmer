import { cn } from "@/lib/utils"
import { MarkdownRenderer } from "@/components/MarkdownRenderer"
import { WebSearchBadge } from "./WebSearchBadge"
import { Bot, User, BookOpen, AlertCircle, RotateCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { formatDistanceToNow } from "date-fns"

export interface SourceUsed {
  source: string
  source_path?: string
  score: number
  snippet: string
}

export interface WebSource {
  title: string
  url: string
  snippet: string
}

export interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: Date
  conversationId?: number
  sourcesUsed?: SourceUsed[]
  webSearchPerformed?: boolean
  webSearchQuery?: string
  webSources?: WebSource[]
  error?: string
}

interface MessageBubbleProps {
  message: ChatMessage
  onShowSources?: (sources: SourceUsed[], webSources: WebSource[]) => void
  onRetry?: () => void
}

export function MessageBubble({ message, onShowSources, onRetry }: MessageBubbleProps) {
  const isUser = message.role === "user"
  const hasSources = (message.sourcesUsed?.length ?? 0) > 0
  const hasWebSources = (message.webSources?.length ?? 0) > 0

  return (
    <div className={cn("flex items-start gap-3", isUser && "flex-row-reverse")}>
      {/* Avatar */}
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
          isUser ? "bg-primary text-primary-foreground" : "bg-muted",
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4 text-muted-foreground" />}
      </div>

      {/* Content */}
      <div className={cn("max-w-[75%] space-y-1", isUser && "items-end")}>
        {/* Web search badge */}
        {message.webSearchPerformed && message.webSearchQuery && (
          <WebSearchBadge query={message.webSearchQuery} />
        )}

        {/* Bubble */}
        <div
          className={cn(
            "rounded-2xl px-4 py-2.5",
            isUser
              ? "rounded-tr-sm bg-primary text-primary-foreground"
              : "rounded-tl-sm bg-muted",
            message.error && "border border-destructive/50 bg-destructive/10",
          )}
        >
          {message.error ? (
            <div className="flex items-start gap-2">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
              <div>
                <p className="text-sm text-destructive">{message.error}</p>
                {onRetry && (
                  <Button variant="ghost" size="sm" className="mt-1 h-7 text-xs" onClick={onRetry}>
                    <RotateCcw className="mr-1 h-3 w-3" /> Retry
                  </Button>
                )}
              </div>
            </div>
          ) : isUser ? (
            <p className="text-sm whitespace-pre-wrap">{message.content}</p>
          ) : (
            <MarkdownRenderer content={message.content} />
          )}
        </div>

        {/* Sources indicator */}
        {(hasSources || hasWebSources) && onShowSources && (
          <button
            onClick={() => onShowSources(message.sourcesUsed || [], message.webSources || [])}
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <BookOpen className="h-3 w-3" />
            Used {(message.sourcesUsed?.length ?? 0) + (message.webSources?.length ?? 0)} sources
          </button>
        )}

        {/* Timestamp */}
        <p className={cn("text-[10px] text-muted-foreground/60", isUser && "text-right")}>
          {formatDistanceToNow(message.timestamp, { addSuffix: true })}
        </p>
      </div>
    </div>
  )
}
