import { useState, useCallback } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { queryKeys } from "@/lib/queryKeys"
import { STALE_TIMES } from "@/lib/queryClient"
import { useDocumentTitle } from "@/hooks/useDocumentTitle"
import { PageHeader } from "@/components/PageHeader"
import { StatCard } from "@/components/StatCard"
import { SearchBar } from "@/components/SearchBar"
import { ConfirmDialog } from "@/components/ConfirmDialog"
import { EmptyState } from "@/components/EmptyState"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Switch } from "@/components/ui/switch"
import { Skeleton } from "@/components/ui/skeleton"
import { Progress } from "@/components/ui/progress"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  getKnowledgeSources,
  searchKnowledge,
  deleteSource,
  ingestText,
  ingestDirectory,
  fetchPage,
} from "@/lib/api"
import {
  Database,
  FileText,
  FolderOpen,
  Globe,
  Plus,
  Trash2,
  ChevronDown,
  ChevronUp,
  Search,
} from "lucide-react"
import { formatDistanceToNow } from "date-fns"
import { toast } from "sonner"

interface Source {
  source: string
  doc_count: number
  latest_update: string | null
}

interface SearchResult {
  content: string
  source: string
  score: number
  metadata: Record<string, unknown>
  id: number | null
}

export default function Knowledge() {
  useDocumentTitle("Knowledge")
  const queryClient = useQueryClient()

  const { data: sources = [], isLoading: loading } = useQuery({
    queryKey: queryKeys.knowledge.sources(),
    queryFn: () => getKnowledgeSources().then((r) => (Array.isArray(r.data) ? r.data : []) as Source[]),
    staleTime: STALE_TIMES.knowledge,
    refetchInterval: 300_000,
  })

  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [expandedResult, setExpandedResult] = useState<number | null>(null)

  // Modals
  const [dirModal, setDirModal] = useState(false)
  const [textModal, setTextModal] = useState(false)
  const [urlModal, setUrlModal] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)

  // Form state
  const [dirForm, setDirForm] = useState({ path: "", source: "", recursive: true, patterns: "*.md, *.txt" })
  const [textForm, setTextForm] = useState({ title: "", source: "manual", text: "" })
  const [urlForm, setUrlForm] = useState({ url: "", source: "web" })
  const [submitting, setSubmitting] = useState(false)

  const handleSearch = useCallback(async (query: string) => {
    setSearchQuery(query)
    if (!query) {
      setSearchResults([])
      return
    }
    setSearching(true)
    try {
      const res = await searchKnowledge(query, 10)
      setSearchResults(res.data.results || [])
    } catch (err) {
      console.error("Search failed:", err)
      toast.error("Search failed")
    } finally {
      setSearching(false)
    }
  }, [])

  const handleDelete = async () => {
    if (!deleteConfirm) return
    try {
      await deleteSource(deleteConfirm)
      toast.success(`Deleted source "${deleteConfirm}"`)
      setDeleteConfirm(null)
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.all })
    } catch {
      toast.error("Failed to delete source")
    }
  }

  const handleIngestDir = async () => {
    if (!dirForm.path || !dirForm.source) return
    setSubmitting(true)
    try {
      const patterns = dirForm.patterns.split(",").map((p) => p.trim()).filter(Boolean)
      const res = await ingestDirectory({
        path: dirForm.path,
        source: dirForm.source,
        recursive: dirForm.recursive,
        patterns,
      })
      toast.success(`Ingested ${res.data.ingested} files from ${dirForm.source}`)
      setDirModal(false)
      setDirForm({ path: "", source: "", recursive: true, patterns: "*.md, *.txt" })
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.all })
    } catch {
      toast.error("Directory ingestion failed")
    } finally {
      setSubmitting(false)
    }
  }

  const handleIngestText = async () => {
    if (!textForm.title || !textForm.text) return
    setSubmitting(true)
    try {
      const res = await ingestText({
        text: textForm.text,
        title: textForm.title,
        source: textForm.source || "manual",
      })
      toast.success(`Ingested "${textForm.title}" (${res.data.chunks_stored} chunks)`)
      setTextModal(false)
      setTextForm({ title: "", source: "manual", text: "" })
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.all })
    } catch {
      toast.error("Text ingestion failed")
    } finally {
      setSubmitting(false)
    }
  }

  const handleIngestUrl = async () => {
    if (!urlForm.url) return
    setSubmitting(true)
    try {
      const fetchRes = await fetchPage(urlForm.url)
      const pageText = fetchRes.data.text
      if (!pageText) {
        toast.error("No text extracted from URL")
        setSubmitting(false)
        return
      }
      await ingestText({
        text: pageText,
        title: urlForm.url,
        source: urlForm.source || "web",
        metadata: { url: urlForm.url },
      })
      toast.success(`Ingested content from URL`)
      setUrlModal(false)
      setUrlForm({ url: "", source: "web" })
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.all })
    } catch {
      toast.error("URL ingestion failed")
    } finally {
      setSubmitting(false)
    }
  }

  const totalDocs = sources.reduce((sum, s) => sum + s.doc_count, 0)
  const lastUpdated = sources
    .filter((s) => s.latest_update)
    .sort((a, b) => new Date(b.latest_update!).getTime() - new Date(a.latest_update!).getTime())[0]

  return (
    <div className="space-y-6">
      <PageHeader
        title="Knowledge Base"
        description="Manage documents, search knowledge, and ingest content"
        actions={
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="sm">
                <Plus className="mr-2 h-4 w-4" /> Ingest
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => setDirModal(true)}>
                <FolderOpen className="mr-2 h-4 w-4" /> Directory
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setTextModal(true)}>
                <FileText className="mr-2 h-4 w-4" /> Text
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setUrlModal(true)}>
                <Globe className="mr-2 h-4 w-4" /> URL
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        }
      />

      {/* Summary Cards */}
      {loading ? (
        <div className="grid gap-4 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-3">
          <StatCard label="Sources" value={sources.length} icon={Database} />
          <StatCard label="Total Documents" value={totalDocs} icon={FileText} />
          <StatCard
            label="Last Ingestion"
            value={lastUpdated?.latest_update
              ? formatDistanceToNow(new Date(lastUpdated.latest_update), { addSuffix: true })
              : "Never"}
            icon={Search}
            subtitle={lastUpdated?.source}
          />
        </div>
      )}

      {/* Search */}
      <div className="mx-auto max-w-2xl">
        <SearchBar
          placeholder="Semantic search across all knowledge..."
          onSearch={handleSearch}
          loading={searching}
          className="text-lg"
        />
      </div>

      {/* Search Results */}
      {searchQuery && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">
            Results {searchResults.length > 0 && `(${searchResults.length})`}
          </h2>
          {searching ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-28" />
              ))}
            </div>
          ) : searchResults.length === 0 ? (
            <EmptyState icon={Search} title="No results" description={`No matches for "${searchQuery}"`} />
          ) : (
            searchResults.map((result, i) => (
              <Card key={result.id ?? i}>
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="mb-2 flex items-center gap-2">
                        <Badge variant="outline">{result.source}</Badge>
                        <span className="text-xs text-muted-foreground">
                          {(result.score * 100).toFixed(0)}% match
                        </span>
                      </div>
                      <Progress value={result.score * 100} className="mb-2 h-1.5" />
                      <p className="text-sm text-foreground/90">
                        {expandedResult === i
                          ? result.content
                          : result.content.slice(0, 200) + (result.content.length > 200 ? "..." : "")}
                      </p>
                      {"source_path" in (result.metadata || {}) && (
                        <p className="mt-1 text-xs text-muted-foreground">
                          {String(result.metadata.source_path)}
                        </p>
                      )}
                    </div>
                    {result.content.length > 200 && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="shrink-0"
                        onClick={() => setExpandedResult(expandedResult === i ? null : i)}
                      >
                        {expandedResult === i ? (
                          <ChevronUp className="h-4 w-4" />
                        ) : (
                          <ChevronDown className="h-4 w-4" />
                        )}
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      )}

      {/* Sources Table */}
      {!searchQuery && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Sources</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-10" />
                ))}
              </div>
            ) : sources.length === 0 ? (
              <EmptyState icon={Database} title="No sources" description="Ingest content to get started" />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Source</TableHead>
                    <TableHead className="text-right">Documents</TableHead>
                    <TableHead>Last Updated</TableHead>
                    <TableHead className="w-12" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sources.map((src) => (
                    <TableRow key={src.source}>
                      <TableCell className="font-medium">{src.source}</TableCell>
                      <TableCell className="text-right">{src.doc_count}</TableCell>
                      <TableCell className="text-muted-foreground">
                        {src.latest_update
                          ? formatDistanceToNow(new Date(src.latest_update), { addSuffix: true })
                          : "\u2014"}
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-destructive hover:text-destructive"
                          onClick={() => setDeleteConfirm(src.source)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}

      {/* Delete Confirm */}
      <ConfirmDialog
        open={!!deleteConfirm}
        onConfirm={handleDelete}
        onCancel={() => setDeleteConfirm(null)}
        title="Delete Source"
        description={`Delete all documents from "${deleteConfirm}"? This cannot be undone.`}
        confirmLabel="Delete"
        destructive
      />

      {/* Ingest Directory Modal */}
      <Dialog open={dirModal} onOpenChange={setDirModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Ingest Directory</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Directory Path</Label>
              <Input
                placeholder="/path/to/documents"
                value={dirForm.path}
                onChange={(e) => setDirForm({ ...dirForm, path: e.target.value })}
              />
            </div>
            <div>
              <Label>Source Name</Label>
              <Input
                placeholder="my-docs"
                value={dirForm.source}
                onChange={(e) => setDirForm({ ...dirForm, source: e.target.value })}
              />
            </div>
            <div>
              <Label>File Patterns</Label>
              <Input
                placeholder="*.md, *.txt"
                value={dirForm.patterns}
                onChange={(e) => setDirForm({ ...dirForm, patterns: e.target.value })}
              />
            </div>
            <div className="flex items-center gap-2">
              <Switch
                checked={dirForm.recursive}
                onCheckedChange={(v) => setDirForm({ ...dirForm, recursive: v })}
              />
              <Label>Recursive</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDirModal(false)}>Cancel</Button>
            <Button onClick={handleIngestDir} disabled={submitting || !dirForm.path || !dirForm.source}>
              {submitting ? "Ingesting..." : "Ingest"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Ingest Text Modal */}
      <Dialog open={textModal} onOpenChange={setTextModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Ingest Text</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Title</Label>
              <Input
                placeholder="Document title"
                value={textForm.title}
                onChange={(e) => setTextForm({ ...textForm, title: e.target.value })}
              />
            </div>
            <div>
              <Label>Source</Label>
              <Input
                placeholder="manual"
                value={textForm.source}
                onChange={(e) => setTextForm({ ...textForm, source: e.target.value })}
              />
            </div>
            <div>
              <Label>Content</Label>
              <Textarea
                placeholder="Paste or type content..."
                value={textForm.text}
                onChange={(e) => setTextForm({ ...textForm, text: e.target.value })}
                rows={8}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTextModal(false)}>Cancel</Button>
            <Button onClick={handleIngestText} disabled={submitting || !textForm.title || !textForm.text}>
              {submitting ? "Ingesting..." : "Ingest"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Ingest URL Modal */}
      <Dialog open={urlModal} onOpenChange={setUrlModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Ingest URL</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>URL</Label>
              <Input
                placeholder="https://example.com/article"
                value={urlForm.url}
                onChange={(e) => setUrlForm({ ...urlForm, url: e.target.value })}
              />
            </div>
            <div>
              <Label>Source Name</Label>
              <Input
                placeholder="web"
                value={urlForm.source}
                onChange={(e) => setUrlForm({ ...urlForm, source: e.target.value })}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setUrlModal(false)}>Cancel</Button>
            <Button onClick={handleIngestUrl} disabled={submitting || !urlForm.url}>
              {submitting ? "Fetching & Ingesting..." : "Ingest"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
