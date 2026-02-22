import axios from "axios"

const api = axios.create({
  baseURL: "/api",
  timeout: 15000,
  headers: { "Content-Type": "application/json" },
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error("API Error:", error.response?.status, error.message)
    return Promise.reject(error)
  },
)

// Health & System
export const getHealth = () => api.get("/health")
export const getNodes = () => api.get("/health/nodes")
export const getNodeHistory = (nodeId: string, hours = 24) =>
  api.get(`/health/nodes/${nodeId}/history`, { params: { hours } })
export const pingNode = (nodeId: string) => api.post(`/nodes/${nodeId}/ping`)

// Agents
export const getAgents = () => api.get("/agents")
export const getAgent = (name: string) => api.get(`/agents/${name}`)
export const updateAgent = (name: string, data: Record<string, unknown>) =>
  api.put(`/agents/${name}`, data)
export const triggerAgent = (name: string) => api.post(`/agents/${name}/run`)
export const getAgentRuns = (name: string, limit = 20) =>
  api.get(`/agents/${name}/runs`, { params: { limit } })
export const getAllRuns = (params?: Record<string, string | number>) =>
  api.get("/agents/runs", { params })
export const enableAgent = (name: string) => api.post(`/agents/${name}/enable`)
export const disableAgent = (name: string) => api.post(`/agents/${name}/disable`)
export const getOrchestratorStatus = () => api.get("/agents/orchestrator/status")
export const createAgent = (data: Record<string, unknown>) =>
  api.post("/agents", data)
export const deleteAgent = (name: string) =>
  api.delete(`/agents/${name}`)
export const getAgentRun = (runId: number) =>
  api.get(`/agents/runs/${runId}`)
export const reloadOrchestrator = () =>
  api.post("/agents/orchestrator/reload")
export const getScheduledJobs = () =>
  api.get("/agents/schedule")
export const getAgentTools = () =>
  api.get("/agents/tools")

// Knowledge
export const getKnowledgeSources = () => api.get("/knowledge/sources")
export const searchKnowledge = (query: string, limit = 10) =>
  api.post("/knowledge/search", { query, limit })
export const ingestFile = (data: FormData) =>
  api.post("/knowledge/ingest/file", data, {
    headers: { "Content-Type": "multipart/form-data" },
  })
export const ingestText = (data: { text: string; title: string; source?: string; metadata?: Record<string, unknown> }) =>
  api.post("/knowledge/ingest/text", data)
export const ingestDirectory = (data: { path: string; source: string; recursive?: boolean; patterns?: string[] }) =>
  api.post("/knowledge/ingest/directory", data)
export const deleteSource = (source: string) =>
  api.delete(`/knowledge/source/${encodeURIComponent(source)}`)

// Notes
export const getNotes = (params?: Record<string, string | number>) =>
  api.get("/notes", { params })
export const getNote = (id: number) => api.get(`/notes/${id}`)
export const searchNotes = (query: string, limit = 10) =>
  api.get("/notes/search", { params: { q: query, limit } })
export const getNoteTags = () => api.get("/notes/tags")
export const getNotesByTag = (tag: string) => api.get(`/notes/tag/${encodeURIComponent(tag)}`)
export const syncNotes = () => api.post("/notes/sync")
export const syncNotesIncremental = () => api.post("/notes/sync/incremental")

// Transcriptions
export const getTranscriptions = (params?: Record<string, string | number>) =>
  api.get("/transcription", { params })
export const getTranscription = (id: number) => api.get(`/transcription/${id}`)
export const searchTranscriptions = (query: string, limit = 10) =>
  api.get("/transcription/search", { params: { q: query, limit } })
export const uploadTranscription = (file: File, diarize = false) => {
  const form = new FormData()
  form.append("file", file)
  return api.post(`/transcription/upload?diarize=${diarize}`, form, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 300000,
  })
}
export const deleteTranscription = (id: number) => api.delete(`/transcription/${id}`)

// Web search
export const fetchPage = (url: string, maxChars = 8000) =>
  api.post("/search/fetch", { url, max_chars: maxChars })

// Chat
export const sendChat = (data: {
  message: string
  conversation_id?: number | null
  model?: string
  web_search?: string
}) => api.post("/chat", data, { timeout: 120000 })
export const getConversations = (limit = 30) =>
  api.get("/chat/conversations", { params: { limit } })
export const getConversation = (id: number) =>
  api.get(`/chat/conversation/${id}`)
export const deleteConversation = (id: number) =>
  api.delete(`/chat/conversation/${id}`)

// Radio - Propagation
export const getPropagation = () => api.get("/propagation")
export const getBands = () => api.get("/propagation/bands")
export const getSolar = () => api.get("/propagation/solar")
export const getPropForecast = () => api.get("/propagation/forecast")
export const getPropHistory = (hours = 24) =>
  api.get("/propagation/history", { params: { hours } })

// Radio - DX
export const getDxSpots = (params?: Record<string, string | number>) =>
  api.get("/dx/spots", { params })
export const getDxSummary = () => api.get("/dx/spots/summary")
export const getNeeds = () => api.get("/dx/needs")
export const addNeed = (data: { entity: string; band?: string; mode?: string; priority?: number }) =>
  api.post("/dx/needs", data)
export const deleteNeed = (id: number) => api.delete(`/dx/needs/${id}`)
export const getClusterStatus = () => api.get("/dx/cluster/status")
export const lookupCallsign = (call: string) => api.get(`/dx/entities/${encodeURIComponent(call)}`)

// Radio - Log
export const getLogStatus = () => api.get("/log/status")
export const getQsos = (params?: Record<string, string | number>) =>
  api.get("/log/qsos", { params })
export const getQsoCount = (params?: Record<string, string | number>) =>
  api.get("/log/qsos/count", { params })
export const getLogStats = () => api.get("/log/stats")
export const getRecentQsos = (limit = 20) =>
  api.get("/log/recent", { params: { limit } })
export const getDxcc = () => api.get("/log/dxcc")
export const searchLog = (q: string, limit = 50) =>
  api.get("/log/search", { params: { q, limit } })
export const getLogContests = () => api.get("/log/contests")
export const analyzeLog = (days = 30, focus?: string) =>
  api.post("/log/analyze", null, { params: { days, ...(focus && { focus }) }, timeout: 120000 })

// Radio - POTA
export const searchParks = (params: Record<string, string>) =>
  api.get("/pota/parks/search", { params })
export const getPotaSpots = () => api.get("/pota/spots")
export const getNearbyParks = (grid = "DN70", radius = 50) =>
  api.get("/pota/parks/nearby", { params: { grid, radius } })
export const getParkDetail = (ref: string) => api.get(`/pota/park/${encodeURIComponent(ref)}`)
export const getParkPlan = (ref: string) => api.get(`/pota/plan/${encodeURIComponent(ref)}`)

// Radio - Contests
export const getUpcomingContests = (days = 30) =>
  api.get("/contest/upcoming", { params: { days } })
export const getContestDetail = (name: string) => api.get(`/contest/${encodeURIComponent(name)}`)
export const getContestDashboard = (name: string) =>
  api.get(`/contest/${encodeURIComponent(name)}/dashboard`)
export const getContestHistory = () => api.get("/contest/history")
export const getContestBandRec = (currentBand: string, contest?: string) =>
  api.get("/contest/recommend-band", { params: { current_band: currentBand, ...(contest && { contest }) } })

// Radio - AllStar
export const getAllstarStatus = (params?: { refresh?: boolean }) =>
  api.get("/allstar", { params })
export const getAllstarStats = () => api.get("/allstar/stats")
export const getAllstarConnections = (params?: { refresh?: boolean }) =>
  api.get("/allstar/connections", { params })
export const getAllstarNodeInfo = (node: number) => api.get(`/allstar/node/${node}`)
export const postAllstarConnect = (data: { node: number }) =>
  api.post("/allstar/connect", data)
export const postAllstarDisconnect = (data: { node: number }) =>
  api.post("/allstar/disconnect", data)
export const postAllstarMonitor = (data: { node: number }) =>
  api.post("/allstar/monitor", data)

// Services / Docs
export const getDeviceInventory = () => api.get("/docs/inventory")
export const getServiceCatalog = () => api.get("/docs/services")

// LLM
export const getModels = () => api.get("/llm/models")

export default api
