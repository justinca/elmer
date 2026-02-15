import { useState, useCallback, useMemo } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { queryKeys } from "@/lib/queryKeys"
import { STALE_TIMES } from "@/lib/queryClient"
import { useDocumentTitle } from "@/hooks/useDocumentTitle"
import { PageHeader } from "@/components/PageHeader"
import { SearchBar } from "@/components/SearchBar"
import { TagBadge } from "@/components/TagBadge"
import { SlidePanel } from "@/components/SlidePanel"
import { MarkdownRenderer } from "@/components/MarkdownRenderer"
import { LoadingSpinner } from "@/components/LoadingSpinner"
import { EmptyState } from "@/components/EmptyState"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  getNotes,
  getNote,
  getNoteTags,
  searchNotes,
  syncNotes,
  syncNotesIncremental,
  searchKnowledge,
} from "@/lib/api"
import {
  StickyNote,
  RefreshCw,
  LayoutGrid,
  List,
  Search,
  Loader2,
  ArrowUpDown,
} from "lucide-react"
import { formatDistanceToNow, format } from "date-fns"
import { toast } from "sonner"
import { Skeleton } from "@/components/ui/skeleton"

interface NoteItem {
  id: number
  source_path: string
  title: string
  tags: string[]
  updated_at: string | null
  created_at: string | null
}

interface NoteDetail {
  id: number
  source: string | null
  source_path: string
  title: string
  content: string
  tags: string[]
  metadata: Record<string, unknown>
  updated_at: string | null
  created_at: string | null
}

interface SyncResult {
  added: number
  updated: number
  deleted: number
  unchanged: number
  errors: number
  duration_seconds: number
}

type SortKey = "title" | "updated_at" | "created_at"
type ViewMode = "grid" | "list"

export default function Notes() {
  useDocumentTitle("Notes")
  const queryClient = useQueryClient()

  const { data: notes = [], isLoading: loading } = useQuery({
    queryKey: queryKeys.notes.list({ limit: 200 }),
    queryFn: () => getNotes({ limit: 200 }).then((r) => (Array.isArray(r.data) ? r.data : []) as NoteItem[]),
    staleTime: STALE_TIMES.notes,
    refetchInterval: 60_000,
  })

  const { data: allTags = [] } = useQuery({
    queryKey: queryKeys.notes.tags(),
    queryFn: () => getNoteTags().then((r) => (r.data.tags || []) as string[]),
    staleTime: STALE_TIMES.notes,
    refetchInterval: 60_000,
  })

  const [searching, setSearching] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [lastSync, setLastSync] = useState<SyncResult | null>(null)

  const [searchQuery, setSearchQuery] = useState("")
  const [searchResults, setSearchResults] = useState<NoteItem[] | null>(null)
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [sortBy, setSortBy] = useState<SortKey>("updated_at")
  const [viewMode, setViewMode] = useState<ViewMode>("grid")

  const [selectedNote, setSelectedNote] = useState<NoteDetail | null>(null)
  const [panelOpen, setPanelOpen] = useState(false)
  const [loadingNote, setLoadingNote] = useState(false)

  const handleSearch = useCallback(async (query: string) => {
    setSearchQuery(query)
    if (!query) {
      setSearchResults(null)
      return
    }
    setSearching(true)
    try {
      const res = await searchNotes(query, 20)
      setSearchResults(Array.isArray(res.data) ? res.data : [])
    } catch (err) {
      console.error("Search failed:", err)
      toast.error("Search failed")
    } finally {
      setSearching(false)
    }
  }, [])

  const handleSync = async (full: boolean) => {
    setSyncing(true)
    try {
      const res = full ? await syncNotes() : await syncNotesIncremental()
      setLastSync(res.data)
      toast.success(
        `Sync complete: ${res.data.added} added, ${res.data.updated} updated, ${res.data.deleted} deleted`,
      )
      queryClient.invalidateQueries({ queryKey: queryKeys.notes.all })
    } catch {
      toast.error("Sync failed")
    } finally {
      setSyncing(false)
    }
  }

  const openNote = async (id: number) => {
    setLoadingNote(true)
    setPanelOpen(true)
    try {
      const res = await getNote(id)
      setSelectedNote(res.data)
    } catch {
      toast.error("Failed to load note")
      setPanelOpen(false)
    } finally {
      setLoadingNote(false)
    }
  }

  const handleSearchSimilar = async (title: string) => {
    setPanelOpen(false)
    try {
      const res = await searchKnowledge(title, 10)
      toast.info(`Found ${res.data.results?.length || 0} similar documents`)
    } catch {
      toast.error("Similar search failed")
    }
  }

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
    )
  }

  const displayNotes = useMemo(() => {
    let list = searchResults ?? notes

    if (selectedTags.length > 0) {
      list = list.filter((n) => selectedTags.some((t) => n.tags.includes(t)))
    }

    const sorted = [...list].sort((a, b) => {
      if (sortBy === "title") return a.title.localeCompare(b.title)
      const aDate = a[sortBy] ? new Date(a[sortBy]!).getTime() : 0
      const bDate = b[sortBy] ? new Date(b[sortBy]!).getTime() : 0
      return bDate - aDate
    })

    return sorted
  }, [notes, searchResults, selectedTags, sortBy])

  // Tag frequency for cloud
  const tagCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const note of notes) {
      for (const tag of note.tags) {
        counts[tag] = (counts[tag] || 0) + 1
      }
    }
    return counts
  }, [notes])

  if (loading) return <LoadingSpinner label="Loading notes..." />

  return (
    <div className="space-y-6">
      <PageHeader
        title="Notes"
        description="Obsidian vault sync and browsing"
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleSync(false)}
              disabled={syncing}
            >
              {syncing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
              Incremental
            </Button>
            <Button size="sm" onClick={() => handleSync(true)} disabled={syncing}>
              {syncing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
              Full Sync
            </Button>
          </div>
        }
      />

      {/* Sync result */}
      {lastSync && (
        <Card>
          <CardContent className="flex items-center gap-4 p-3 text-sm">
            <Badge variant="outline">Sync Result</Badge>
            <span className="text-muted-foreground">
              +{lastSync.added} added, ~{lastSync.updated} updated, -{lastSync.deleted} deleted,
              {" "}{lastSync.unchanged} unchanged
              {lastSync.errors > 0 && `, ${lastSync.errors} errors`}
              {" "}in {lastSync.duration_seconds.toFixed(1)}s
            </span>
          </CardContent>
        </Card>
      )}

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3">
        <SearchBar
          placeholder="Search notes..."
          onSearch={handleSearch}
          loading={searching}
          className="flex-1 min-w-[200px]"
        />
        <Select value={sortBy} onValueChange={(v) => setSortBy(v as SortKey)}>
          <SelectTrigger className="w-[160px]">
            <ArrowUpDown className="mr-2 h-4 w-4" />
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="updated_at">Modified</SelectItem>
            <SelectItem value="created_at">Created</SelectItem>
            <SelectItem value="title">Title</SelectItem>
          </SelectContent>
        </Select>
        <div className="flex rounded-md border">
          <Button
            variant={viewMode === "grid" ? "secondary" : "ghost"}
            size="icon"
            className="h-9 w-9 rounded-r-none"
            onClick={() => setViewMode("grid")}
          >
            <LayoutGrid className="h-4 w-4" />
          </Button>
          <Button
            variant={viewMode === "list" ? "secondary" : "ghost"}
            size="icon"
            className="h-9 w-9 rounded-l-none"
            onClick={() => setViewMode("list")}
          >
            <List className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Tag Cloud */}
      {allTags.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Tags</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-1.5">
              {allTags.map((tag) => (
                <TagBadge
                  key={tag}
                  tag={`${tag} (${tagCounts[tag] || 0})`}
                  onClick={() => toggleTag(tag)}
                  active={selectedTags.includes(tag)}
                  size={tagCounts[tag] > 5 ? "md" : "sm"}
                />
              ))}
            </div>
            {selectedTags.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                className="mt-2"
                onClick={() => setSelectedTags([])}
              >
                Clear filters
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {/* Notes */}
      {displayNotes.length === 0 ? (
        <EmptyState
          icon={StickyNote}
          title="No notes found"
          description={searchQuery ? "Try a different search" : "Sync your Obsidian vault to get started"}
        />
      ) : viewMode === "grid" ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {displayNotes.map((note) => (
            <Card
              key={note.id}
              className="cursor-pointer transition-colors hover:bg-accent/50"
              onClick={() => openNote(note.id)}
            >
              <CardContent className="p-4">
                <h3 className="mb-1 font-medium leading-tight">{note.title}</h3>
                {note.tags.length > 0 && (
                  <div className="mb-2 flex flex-wrap gap-1">
                    {note.tags.slice(0, 4).map((t) => (
                      <TagBadge key={t} tag={t} size="sm" />
                    ))}
                    {note.tags.length > 4 && (
                      <Badge variant="secondary" className="text-xs">+{note.tags.length - 4}</Badge>
                    )}
                  </div>
                )}
                <p className="text-xs text-muted-foreground">
                  {note.updated_at
                    ? format(new Date(note.updated_at), "MMM d, yyyy")
                    : "\u2014"}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Title</TableHead>
                  <TableHead>Tags</TableHead>
                  <TableHead>Modified</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {displayNotes.map((note) => (
                  <TableRow
                    key={note.id}
                    className="cursor-pointer"
                    onClick={() => openNote(note.id)}
                  >
                    <TableCell className="font-medium">{note.title}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {note.tags.slice(0, 3).map((t) => (
                          <TagBadge key={t} tag={t} size="sm" />
                        ))}
                        {note.tags.length > 3 && (
                          <span className="text-xs text-muted-foreground">+{note.tags.length - 3}</span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {note.updated_at
                        ? formatDistanceToNow(new Date(note.updated_at), { addSuffix: true })
                        : "\u2014"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Note Detail Panel */}
      <SlidePanel
        open={panelOpen}
        onClose={() => {
          setPanelOpen(false)
          setSelectedNote(null)
        }}
        title={selectedNote?.title || "Note"}
      >
        {loadingNote ? (
          <div className="space-y-4">
            <Skeleton className="h-6 w-3/4" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        ) : selectedNote ? (
          <div className="space-y-4">
            {/* Metadata */}
            <div className="space-y-1 text-sm text-muted-foreground">
              <p>Path: {selectedNote.source_path}</p>
              {selectedNote.updated_at && (
                <p>Modified: {format(new Date(selectedNote.updated_at), "PPpp")}</p>
              )}
              {selectedNote.created_at && (
                <p>Created: {format(new Date(selectedNote.created_at), "PPpp")}</p>
              )}
            </div>

            {selectedNote.tags.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {selectedNote.tags.map((t) => (
                  <TagBadge key={t} tag={t} size="md" />
                ))}
              </div>
            )}

            <Button
              variant="outline"
              size="sm"
              onClick={() => handleSearchSimilar(selectedNote.title)}
            >
              <Search className="mr-2 h-4 w-4" /> Search similar
            </Button>

            <MarkdownRenderer content={selectedNote.content} />
          </div>
        ) : null}
      </SlidePanel>
    </div>
  )
}
