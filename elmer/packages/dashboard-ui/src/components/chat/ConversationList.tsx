import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Plus, Trash2, MessageSquare } from "lucide-react"
import { formatDistanceToNow } from "date-fns"

export interface ConversationSummary {
  id: number
  message_count: number
  created_at: string | null
  updated_at: string | null
  preview?: string
}

interface ConversationListProps {
  conversations: ConversationSummary[]
  activeId: number | null
  loading: boolean
  onSelect: (id: number) => void
  onNew: () => void
  onDelete: (id: number) => void
}

export function ConversationList({
  conversations,
  activeId,
  loading,
  onSelect,
  onNew,
  onDelete,
}: ConversationListProps) {
  return (
    <div className="flex h-full flex-col">
      <div className="border-b p-3">
        <Button size="sm" className="w-full" onClick={onNew}>
          <Plus className="mr-2 h-4 w-4" /> New Conversation
        </Button>
      </div>
      <ScrollArea className="flex-1">
        <div className="space-y-0.5 p-2">
          {loading ? (
            Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-16 rounded-md" />
            ))
          ) : conversations.length === 0 ? (
            <div className="p-4 text-center text-sm text-muted-foreground">
              No conversations yet
            </div>
          ) : (
            conversations.map((conv) => (
              <div
                key={conv.id}
                className={cn(
                  "group flex cursor-pointer items-start gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                  "hover:bg-accent",
                  activeId === conv.id && "bg-accent",
                )}
                onClick={() => onSelect(conv.id)}
              >
                <MessageSquare className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">
                    {conv.preview || `Conversation #${conv.id}`}
                  </p>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span>{conv.message_count} msgs</span>
                    {conv.updated_at && (
                      <span>{formatDistanceToNow(new Date(conv.updated_at), { addSuffix: true })}</span>
                    )}
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 shrink-0 opacity-0 group-hover:opacity-100"
                  onClick={(e) => {
                    e.stopPropagation()
                    onDelete(conv.id)
                  }}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
