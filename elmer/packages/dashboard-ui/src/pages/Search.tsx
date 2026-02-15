import { useState, useCallback } from "react"
import { useNavigate } from "react-router-dom"
import { searchKnowledge, searchNotes, searchLog } from "@/lib/api"
import { useDocumentTitle } from "@/hooks/useDocumentTitle"
import { PageHeader } from "@/components/PageHeader"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Search as SearchIcon, FileText, StickyNote, Radio, Loader2 } from "lucide-react"

interface SearchResult {
  type: "knowledge" | "note" | "qso"
  title: string
  snippet: string
  score?: number
  id?: number
  source?: string
}

export default function SearchPage() {
  useDocumentTitle("Search")
  const navigate = useNavigate()

  const [query, setQuery] = useState("")
  const [results, setResults] = useState<SearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [searched, setSearched] = useState(false)

  const handleSearch = useCallback(async () => {
    const q = query.trim()
    if (!q) return
    setSearching(true)
    setSearched(true)
    try {
      const [knowRes, notesRes, logRes] = await Promise.allSettled([
        searchKnowledge(q, 10),
        searchNotes(q, 10),
        searchLog(q, 10),
      ])

      const merged: SearchResult[] = []

      if (knowRes.status === "fulfilled") {
        const items = knowRes.value.data?.results || knowRes.value.data || []
        for (const item of items) {
          merged.push({
            type: "knowledge",
            title: item.title || item.source || "Document",
            snippet: (item.content || item.text || "").slice(0, 200),
            score: item.score || item.similarity,
            source: item.source,
          })
        }
      }

      if (notesRes.status === "fulfilled") {
        const items = notesRes.value.data || []
        for (const item of items) {
          merged.push({
            type: "note",
            title: item.title || item.filename || "Note",
            snippet: (item.content || item.preview || "").slice(0, 200),
            score: item.score || item.similarity,
            id: item.id,
          })
        }
      }

      if (logRes.status === "fulfilled") {
        const items = logRes.value.data || []
        for (const item of items) {
          merged.push({
            type: "qso",
            title: item.call || "QSO",
            snippet: [item.date, item.band, item.mode, item.country].filter(Boolean).join(" · "),
            id: item.id,
          })
        }
      }

      // Sort by score descending when available
      merged.sort((a, b) => (b.score || 0) - (a.score || 0))
      setResults(merged)
    } catch {
      setResults([])
    } finally {
      setSearching(false)
    }
  }, [query])

  const typeIcon = {
    knowledge: FileText,
    note: StickyNote,
    qso: Radio,
  }

  const typeLabel = {
    knowledge: "Knowledge",
    note: "Note",
    qso: "QSO",
  }

  const handleClick = (result: SearchResult) => {
    if (result.type === "knowledge") navigate("/documents")
    else if (result.type === "note") navigate("/notes")
    else if (result.type === "qso") navigate("/log")
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Search" description="Search across knowledge, notes, and QSO log" />

      {/* Search bar */}
      <div className="flex gap-2 max-w-2xl">
        <div className="relative flex-1">
          <SearchIcon className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search knowledge, notes, QSOs..."
            className="pl-9 h-11 text-base"
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          />
        </div>
        <Button onClick={handleSearch} disabled={searching || !query.trim()} className="h-11">
          {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : "Search"}
        </Button>
      </div>

      {/* Results */}
      {searching && (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      )}

      {!searching && searched && results.length === 0 && (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            No results found for &ldquo;{query}&rdquo;
          </CardContent>
        </Card>
      )}

      {!searching && results.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">
              {results.length} result{results.length !== 1 ? "s" : ""}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <ScrollArea className="max-h-[600px]">
              <div className="divide-y">
                {results.map((result, i) => {
                  const Icon = typeIcon[result.type]
                  return (
                    <div
                      key={i}
                      className="flex items-start gap-3 p-4 hover:bg-accent/50 cursor-pointer"
                      onClick={() => handleClick(result)}
                    >
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10">
                        <Icon className="h-4 w-4 text-primary" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium truncate">{result.title}</p>
                          <Badge variant="secondary" className="text-xs shrink-0">
                            {typeLabel[result.type]}
                          </Badge>
                          {result.score != null && (
                            <span className="text-xs text-muted-foreground tabular-nums">
                              {(result.score * 100).toFixed(0)}%
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground line-clamp-2 mt-0.5">
                          {result.snippet}
                        </p>
                      </div>
                    </div>
                  )
                })}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
