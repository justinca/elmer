import { useEffect, useState, useCallback, useRef, useMemo } from "react"
import { useNavigate } from "react-router-dom"
import { Dialog, DialogContent } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { navigation } from "@/lib/nav"
import { searchKnowledge, searchNotes, getAgents } from "@/lib/api"
import {
  Search,
  FileText,
  Bot,
  StickyNote,
  MessageSquare,
  RefreshCw,
  type LucideIcon,
} from "lucide-react"

interface PaletteItem {
  id: string
  label: string
  description?: string
  icon: LucideIcon
  category: string
  action: () => void
}

interface CommandPaletteProps {
  open: boolean
  onClose: () => void
}

export function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const navigate = useNavigate()
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<PaletteItem[]>([])
  const [selectedIdx, setSelectedIdx] = useState(0)
  const [searching, setSearching] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Static page items from nav
  const pageItems: PaletteItem[] = useMemo(
    () =>
      navigation.flatMap((group) =>
        group.items.map((item) => ({
          id: `page-${item.path}`,
          label: item.label,
          description: group.label,
          icon: item.icon,
          category: "Pages",
          action: () => {
            navigate(item.path)
            onClose()
          },
        })),
      ),
    [navigate, onClose],
  )

  // Quick actions
  const quickActions: PaletteItem[] = useMemo(
    () => [
      {
        id: "action-chat",
        label: "New Chat",
        description: "Start a new conversation",
        icon: MessageSquare,
        category: "Actions",
        action: () => {
          navigate("/chat")
          onClose()
        },
      },
      {
        id: "action-search",
        label: "Search Knowledge",
        description: "Semantic search across documents",
        icon: Search,
        category: "Actions",
        action: () => {
          navigate("/search")
          onClose()
        },
      },
      {
        id: "action-sync",
        label: "Sync Notes",
        description: "Trigger Obsidian note sync",
        icon: RefreshCw,
        category: "Actions",
        action: () => {
          navigate("/notes")
          onClose()
        },
      },
    ],
    [navigate, onClose],
  )

  // Search API for agents, notes, knowledge
  const doSearch = useCallback(
    async (q: string) => {
      if (!q.trim()) {
        setResults([])
        setSearching(false)
        return
      }
      setSearching(true)
      const apiResults: PaletteItem[] = []

      const [agentsRes, notesRes, knowledgeRes] = await Promise.allSettled([
        getAgents(),
        searchNotes(q, 5),
        searchKnowledge(q, 5),
      ])

      if (agentsRes.status === "fulfilled") {
        const agents = agentsRes.value.data || []
        for (const a of agents) {
          const name = a.display_name || a.name
          if (name?.toLowerCase().includes(q.toLowerCase())) {
            apiResults.push({
              id: `agent-${a.name}`,
              label: name,
              description: a.description?.slice(0, 60),
              icon: Bot,
              category: "Agents",
              action: () => {
                navigate("/agents")
                onClose()
              },
            })
          }
        }
      }

      if (notesRes.status === "fulfilled") {
        const notes = notesRes.value.data || []
        for (const n of notes) {
          apiResults.push({
            id: `note-${n.id}`,
            label: n.title || n.filename || "Note",
            description: (n.preview || n.content || "").slice(0, 60),
            icon: StickyNote,
            category: "Notes",
            action: () => {
              navigate("/notes")
              onClose()
            },
          })
        }
      }

      if (knowledgeRes.status === "fulfilled") {
        const docs = knowledgeRes.value.data?.results || knowledgeRes.value.data || []
        for (const d of docs) {
          apiResults.push({
            id: `doc-${d.source || d.title}`,
            label: d.title || d.source || "Document",
            description: (d.content || d.text || "").slice(0, 60),
            icon: FileText,
            category: "Knowledge",
            action: () => {
              navigate("/documents")
              onClose()
            },
          })
        }
      }

      setResults(apiResults.slice(0, 15))
      setSearching(false)
    },
    [navigate, onClose],
  )

  // Debounced search
  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => doSearch(query), 300)
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [query, doSearch])

  // Filter pages and actions by query
  const filteredPages = useMemo(() => {
    if (!query.trim()) return [...quickActions, ...pageItems]
    const q = query.toLowerCase()
    return pageItems.filter(
      (p) =>
        p.label.toLowerCase().includes(q) ||
        p.description?.toLowerCase().includes(q),
    )
  }, [query, pageItems, quickActions])

  const allItems = useMemo(
    () => [...filteredPages, ...results],
    [filteredPages, results],
  )

  // Reset selection when items change
  useEffect(() => {
    setSelectedIdx(0)
  }, [allItems.length])

  // Reset on open
  useEffect(() => {
    if (open) {
      setQuery("")
      setResults([])
      setSelectedIdx(0)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault()
      setSelectedIdx((prev) => Math.min(prev + 1, allItems.length - 1))
    } else if (e.key === "ArrowUp") {
      e.preventDefault()
      setSelectedIdx((prev) => Math.max(prev - 1, 0))
    } else if (e.key === "Enter" && allItems[selectedIdx]) {
      e.preventDefault()
      allItems[selectedIdx].action()
    }
  }

  // Group items by category for display
  const grouped = useMemo(() => {
    const groups: Record<string, PaletteItem[]> = {}
    for (const item of allItems) {
      if (!groups[item.category]) groups[item.category] = []
      groups[item.category].push(item)
    }
    return groups
  }, [allItems])

  let flatIdx = 0

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg p-0 gap-0 overflow-hidden">
        <div className="flex items-center border-b px-3">
          <Search className="h-4 w-4 text-muted-foreground shrink-0" />
          <Input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search pages, agents, notes..."
            className="border-0 shadow-none focus-visible:ring-0 h-11"
          />
          <kbd className="hidden sm:inline-flex h-5 items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] text-muted-foreground">
            ESC
          </kbd>
        </div>
        <ScrollArea className="max-h-[360px]">
          {Object.keys(grouped).length === 0 && !searching && query && (
            <div className="px-4 py-8 text-center text-sm text-muted-foreground">
              No results found
            </div>
          )}
          {searching && (
            <div className="px-4 py-3 text-xs text-muted-foreground">
              Searching...
            </div>
          )}
          {Object.entries(grouped).map(([category, items]) => (
            <div key={category}>
              <div className="px-3 py-1.5">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {category}
                </p>
              </div>
              {items.map((item) => {
                const idx = flatIdx++
                return (
                  <button
                    key={item.id}
                    className={`flex items-center gap-3 w-full px-3 py-2 text-left text-sm transition-colors ${
                      idx === selectedIdx
                        ? "bg-accent text-accent-foreground"
                        : "hover:bg-accent/50"
                    }`}
                    onClick={item.action}
                    onMouseEnter={() => setSelectedIdx(idx)}
                  >
                    <item.icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <div className="flex-1 min-w-0">
                      <span className="font-medium">{item.label}</span>
                      {item.description && (
                        <span className="ml-2 text-xs text-muted-foreground truncate">
                          {item.description}
                        </span>
                      )}
                    </div>
                    {item.category !== "Pages" && item.category !== "Actions" && (
                      <Badge variant="secondary" className="text-[10px] shrink-0">
                        {item.category}
                      </Badge>
                    )}
                  </button>
                )
              })}
            </div>
          ))}
        </ScrollArea>
        <div className="border-t px-3 py-2 flex items-center gap-3 text-[10px] text-muted-foreground">
          <span>
            <kbd className="rounded border bg-muted px-1 py-0.5 font-mono">↑↓</kbd> Navigate
          </span>
          <span>
            <kbd className="rounded border bg-muted px-1 py-0.5 font-mono">↵</kbd> Select
          </span>
          <span>
            <kbd className="rounded border bg-muted px-1 py-0.5 font-mono">ESC</kbd> Close
          </span>
        </div>
      </DialogContent>
    </Dialog>
  )
}
