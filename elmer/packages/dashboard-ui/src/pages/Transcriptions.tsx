import { useState, useCallback } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { queryKeys } from "@/lib/queryKeys"
import { STALE_TIMES } from "@/lib/queryClient"
import { useDocumentTitle } from "@/hooks/useDocumentTitle"
import { PageHeader } from "@/components/PageHeader"
import { SearchBar } from "@/components/SearchBar"
import { FileUpload } from "@/components/FileUpload"
import { ConfirmDialog } from "@/components/ConfirmDialog"
import { EmptyState } from "@/components/EmptyState"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import {
  getTranscriptions,
  getTranscription,
  searchTranscriptions,
  uploadTranscription,
  deleteTranscription,
} from "@/lib/api"
import {
  AudioLines,
  ChevronDown,
  ChevronUp,
  Clock,
  Languages,
  Trash2,
  Upload,
} from "lucide-react"
import { formatDistanceToNow, format } from "date-fns"
import { toast } from "sonner"

interface TranscriptionItem {
  id: number
  audio_file: string
  transcript: string
  language: string | null
  duration_seconds: number | null
  model: string | null
  created_at: string | null
}

interface TranscriptionDetail {
  id: number
  audio_file: string
  transcript: string
  segments: Array<{ start: number; end: number; text: string; speaker?: string }>
  language: string | null
  duration_seconds: number | null
  model: string | null
  metadata: Record<string, unknown>
  created_at: string | null
  diarized: boolean
  speakers: string[]
}

interface SearchResult {
  id: number
  audio_file: string
  transcript: string
  score: number
  metadata: Record<string, unknown>
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return "\u2014"
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}:${s.toString().padStart(2, "0")}`
}

function formatTimestamp(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  const ms = Math.round((seconds % 1) * 100)
  return `${m}:${s.toString().padStart(2, "0")}.${ms.toString().padStart(2, "0")}`
}

export default function Transcriptions() {
  useDocumentTitle("Transcriptions")
  const queryClient = useQueryClient()

  const { data: transcriptions = [], isLoading: loading } = useQuery({
    queryKey: queryKeys.transcriptions.list({ limit: 100 }),
    queryFn: () => getTranscriptions({ limit: 100 }).then((r) => (Array.isArray(r.data) ? r.data : []) as TranscriptionItem[]),
    staleTime: STALE_TIMES.transcriptions,
    refetchInterval: 60_000,
  })

  const [searching, setSearching] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null)

  const [showUpload, setShowUpload] = useState(false)
  const [diarize, setDiarize] = useState(false)

  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [expandedDetail, setExpandedDetail] = useState<TranscriptionDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  const [deleteId, setDeleteId] = useState<number | null>(null)

  const handleSearch = useCallback(async (query: string) => {
    setSearchQuery(query)
    if (!query) {
      setSearchResults(null)
      return
    }
    setSearching(true)
    try {
      const res = await searchTranscriptions(query, 10)
      setSearchResults(Array.isArray(res.data) ? res.data : [])
    } catch {
      toast.error("Search failed")
    } finally {
      setSearching(false)
    }
  }, [])

  const handleUpload = async (file: File) => {
    await uploadTranscription(file, diarize)
    toast.success(`Uploaded "${file.name}" for transcription`)
    queryClient.invalidateQueries({ queryKey: queryKeys.transcriptions.all })
  }

  const handleExpand = async (id: number) => {
    if (expandedId === id) {
      setExpandedId(null)
      setExpandedDetail(null)
      return
    }
    setExpandedId(id)
    setLoadingDetail(true)
    try {
      const res = await getTranscription(id)
      setExpandedDetail(res.data)
    } catch {
      toast.error("Failed to load transcription details")
      setExpandedId(null)
    } finally {
      setLoadingDetail(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteId) return
    try {
      await deleteTranscription(deleteId)
      toast.success("Transcription deleted")
      setDeleteId(null)
      if (expandedId === deleteId) {
        setExpandedId(null)
        setExpandedDetail(null)
      }
      queryClient.invalidateQueries({ queryKey: queryKeys.transcriptions.all })
    } catch {
      toast.error("Delete failed")
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Transcriptions"
        description="Audio transcription with Whisper"
        actions={
          <Button
            size="sm"
            variant={showUpload ? "secondary" : "default"}
            onClick={() => setShowUpload(!showUpload)}
          >
            <Upload className="mr-2 h-4 w-4" />
            {showUpload ? "Hide Upload" : "Upload"}
          </Button>
        }
      />

      {/* Upload Section */}
      {showUpload && (
        <Card>
          <CardContent className="p-4 space-y-3">
            <FileUpload
              accept={{
                "audio/*": [".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm"],
              }}
              onUpload={handleUpload}
              label="Drop audio files here or click to browse"
              formats="Supported: .wav, .mp3, .m4a, .flac, .ogg, .webm"
            />
            <div className="flex items-center gap-2">
              <Switch checked={diarize} onCheckedChange={setDiarize} />
              <Label>Enable speaker diarization</Label>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Search */}
      <SearchBar
        placeholder="Search transcriptions..."
        onSearch={handleSearch}
        loading={searching}
      />

      {/* Search Results */}
      {searchResults !== null && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">
            Search Results ({searchResults.length})
          </h2>
          {searchResults.length === 0 ? (
            <EmptyState
              icon={AudioLines}
              title="No results"
              description={`No matches for "${searchQuery}"`}
            />
          ) : (
            searchResults.map((result) => (
              <Card key={result.id}>
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="mb-1 flex items-center gap-2">
                        <span className="font-medium">{result.audio_file}</span>
                        <Badge variant="outline">{(result.score * 100).toFixed(0)}%</Badge>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {result.transcript.slice(0, 300)}
                        {result.transcript.length > 300 ? "..." : ""}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      )}

      {/* Transcription List */}
      {searchResults === null && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Transcriptions ({transcriptions.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {loading ? (
              <div className="space-y-2 p-4">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-12" />
                ))}
              </div>
            ) : transcriptions.length === 0 ? (
              <div className="p-4">
                <EmptyState
                  icon={AudioLines}
                  title="No transcriptions"
                  description="Upload audio files to get started"
                />
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8" />
                    <TableHead>File</TableHead>
                    <TableHead>Duration</TableHead>
                    <TableHead>Language</TableHead>
                    <TableHead>Date</TableHead>
                    <TableHead className="w-12" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {transcriptions.map((t) => (
                    <Collapsible
                      key={t.id}
                      open={expandedId === t.id}
                      onOpenChange={() => handleExpand(t.id)}
                      asChild
                    >
                      <>
                        <CollapsibleTrigger asChild>
                          <TableRow className="cursor-pointer">
                            <TableCell>
                              {expandedId === t.id ? (
                                <ChevronUp className="h-4 w-4" />
                              ) : (
                                <ChevronDown className="h-4 w-4" />
                              )}
                            </TableCell>
                            <TableCell className="font-medium">
                              <div className="flex items-center gap-2">
                                <AudioLines className="h-4 w-4 shrink-0 text-muted-foreground" />
                                <span className="truncate">{t.audio_file}</span>
                              </div>
                            </TableCell>
                            <TableCell>
                              <div className="flex items-center gap-1 text-muted-foreground">
                                <Clock className="h-3 w-3" />
                                {formatDuration(t.duration_seconds)}
                              </div>
                            </TableCell>
                            <TableCell>
                              {t.language ? (
                                <div className="flex items-center gap-1">
                                  <Languages className="h-3 w-3 text-muted-foreground" />
                                  {t.language}
                                </div>
                              ) : (
                                "\u2014"
                              )}
                            </TableCell>
                            <TableCell className="text-muted-foreground">
                              {t.created_at
                                ? formatDistanceToNow(new Date(t.created_at), { addSuffix: true })
                                : "\u2014"}
                            </TableCell>
                            <TableCell>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8 text-destructive hover:text-destructive"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  setDeleteId(t.id)
                                }}
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </TableCell>
                          </TableRow>
                        </CollapsibleTrigger>
                        <CollapsibleContent asChild>
                          <TableRow>
                            <TableCell colSpan={6} className="bg-muted/30 p-4">
                              {loadingDetail && expandedId === t.id ? (
                                <div className="space-y-2">
                                  <Skeleton className="h-4 w-full" />
                                  <Skeleton className="h-4 w-full" />
                                  <Skeleton className="h-4 w-3/4" />
                                </div>
                              ) : expandedDetail && expandedId === t.id ? (
                                <div className="space-y-4">
                                  {/* Metadata */}
                                  <div className="flex flex-wrap gap-2 text-xs">
                                    {expandedDetail.model && (
                                      <Badge variant="outline">Model: {expandedDetail.model}</Badge>
                                    )}
                                    {expandedDetail.diarized && (
                                      <Badge variant="outline">Diarized</Badge>
                                    )}
                                    {expandedDetail.speakers.length > 0 && (
                                      <Badge variant="outline">
                                        Speakers: {expandedDetail.speakers.join(", ")}
                                      </Badge>
                                    )}
                                    {expandedDetail.created_at && (
                                      <Badge variant="outline">
                                        {format(new Date(expandedDetail.created_at), "PPpp")}
                                      </Badge>
                                    )}
                                  </div>

                                  {/* Full transcript */}
                                  <div>
                                    <h4 className="mb-1 text-sm font-medium">Transcript</h4>
                                    <p className="whitespace-pre-wrap text-sm text-foreground/90">
                                      {expandedDetail.transcript}
                                    </p>
                                  </div>

                                  {/* Segments */}
                                  {expandedDetail.segments.length > 0 && (
                                    <div>
                                      <h4 className="mb-1 text-sm font-medium">Segments</h4>
                                      <div className="max-h-64 overflow-y-auto rounded border">
                                        <table className="w-full text-sm">
                                          <thead className="sticky top-0 bg-muted">
                                            <tr>
                                              <th className="px-2 py-1 text-left">Time</th>
                                              {expandedDetail.diarized && (
                                                <th className="px-2 py-1 text-left">Speaker</th>
                                              )}
                                              <th className="px-2 py-1 text-left">Text</th>
                                            </tr>
                                          </thead>
                                          <tbody>
                                            {expandedDetail.segments.map((seg, i) => (
                                              <tr key={i} className="border-t border-border/50">
                                                <td className="whitespace-nowrap px-2 py-1 text-xs text-muted-foreground">
                                                  {formatTimestamp(seg.start)} \u2192 {formatTimestamp(seg.end)}
                                                </td>
                                                {expandedDetail.diarized && (
                                                  <td className="px-2 py-1 text-xs">
                                                    <Badge variant="secondary" className="text-xs">
                                                      {seg.speaker || "?"}
                                                    </Badge>
                                                  </td>
                                                )}
                                                <td className="px-2 py-1">{seg.text}</td>
                                              </tr>
                                            ))}
                                          </tbody>
                                        </table>
                                      </div>
                                    </div>
                                  )}
                                </div>
                              ) : null}
                            </TableCell>
                          </TableRow>
                        </CollapsibleContent>
                      </>
                    </Collapsible>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}

      {/* Delete Confirm */}
      <ConfirmDialog
        open={!!deleteId}
        onConfirm={handleDelete}
        onCancel={() => setDeleteId(null)}
        title="Delete Transcription"
        description="This will permanently delete this transcription. This cannot be undone."
        confirmLabel="Delete"
        destructive
      />
    </div>
  )
}
