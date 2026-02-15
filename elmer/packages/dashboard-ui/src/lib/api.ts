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

// Knowledge
export const getKnowledgeSources = () => api.get("/knowledge/sources")
export const searchKnowledge = (query: string, limit = 10) =>
  api.post("/knowledge/search", { query, limit })
export const ingestFile = (data: FormData) =>
  api.post("/knowledge/ingest/file", data, {
    headers: { "Content-Type": "multipart/form-data" },
  })
export const deleteSource = (source: string) =>
  api.delete(`/knowledge/source/${encodeURIComponent(source)}`)

// Notes
export const getNotes = (params?: Record<string, string | number>) =>
  api.get("/notes", { params })
export const searchNotes = (query: string, limit = 5) =>
  api.get("/notes/search", { params: { q: query, limit } })

// Transcriptions
export const getTranscriptions = (params?: Record<string, string | number>) =>
  api.get("/transcription", { params })
export const searchTranscriptions = (query: string, limit = 5) =>
  api.get("/transcription/search", { params: { q: query, limit } })

// Chat
export const sendChat = (message: string, webSearch?: string) =>
  api.post("/chat", { message, web_search: webSearch })
export const getConversations = () => api.get("/chat/conversations")

// Radio - Propagation
export const getPropagation = () => api.get("/propagation")
export const getBands = () => api.get("/propagation/bands")
export const getSolar = () => api.get("/propagation/solar")

// Radio - DX
export const getDxSpots = (params?: Record<string, string>) =>
  api.get("/dx/spots", { params })
export const getDxSummary = () => api.get("/dx/spots/summary")
export const getNeeds = () => api.get("/dx/needs")

// Radio - Log
export const getLogStatus = () => api.get("/log/status")
export const getQsos = (params?: Record<string, string | number>) =>
  api.get("/log/qsos", { params })
export const getLogStats = () => api.get("/log/stats")
export const getRecentQsos = (limit = 20) =>
  api.get("/log/recent", { params: { limit } })

// Radio - POTA
export const searchParks = (params: Record<string, string>) =>
  api.get("/pota/parks/search", { params })
export const getPotaSpots = () => api.get("/pota/spots")

// Radio - Contests
export const getUpcomingContests = (days = 30) =>
  api.get("/contest/upcoming", { params: { days } })

// LLM
export const getModels = () => api.get("/llm/models")

export default api
