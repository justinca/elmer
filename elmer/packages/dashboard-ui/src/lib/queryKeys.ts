export const queryKeys = {
  health: {
    all: ["health"] as const,
    core: () => [...queryKeys.health.all, "core"] as const,
    nodes: () => [...queryKeys.health.all, "nodes"] as const,
    nodeHistory: (nodeId: string, hours: number) =>
      [...queryKeys.health.all, "history", nodeId, hours] as const,
    allHistory: (hours: number) =>
      [...queryKeys.health.all, "allHistory", hours] as const,
  },
  agents: {
    all: ["agents"] as const,
    list: () => [...queryKeys.agents.all, "list"] as const,
    detail: (name: string) => [...queryKeys.agents.all, name] as const,
    runs: (name: string) => [...queryKeys.agents.all, name, "runs"] as const,
    allRuns: (params?: Record<string, string | number>) =>
      [...queryKeys.agents.all, "runs", params] as const,
    orchestrator: () => [...queryKeys.agents.all, "orchestrator"] as const,
    schedule: () => [...queryKeys.agents.all, "schedule"] as const,
    tools: () => [...queryKeys.agents.all, "tools"] as const,
  },
  knowledge: {
    all: ["knowledge"] as const,
    sources: () => [...queryKeys.knowledge.all, "sources"] as const,
  },
  notes: {
    all: ["notes"] as const,
    list: (params?: Record<string, string | number>) =>
      [...queryKeys.notes.all, "list", params] as const,
    tags: () => [...queryKeys.notes.all, "tags"] as const,
    detail: (id: number) => [...queryKeys.notes.all, id] as const,
  },
  transcriptions: {
    all: ["transcriptions"] as const,
    list: (params?: Record<string, string | number>) =>
      [...queryKeys.transcriptions.all, "list", params] as const,
    detail: (id: number) => [...queryKeys.transcriptions.all, id] as const,
  },
  chat: {
    conversations: () => ["chat", "conversations"] as const,
    conversation: (id: number) => ["chat", "conversation", id] as const,
    models: () => ["chat", "models"] as const,
  },
  propagation: {
    all: ["propagation"] as const,
    current: () => [...queryKeys.propagation.all, "current"] as const,
    forecast: () => [...queryKeys.propagation.all, "forecast"] as const,
    history: (hours: number) =>
      [...queryKeys.propagation.all, "history", hours] as const,
    bands: () => [...queryKeys.propagation.all, "bands"] as const,
  },
  dx: {
    all: ["dx"] as const,
    spots: (params?: Record<string, string | number>) =>
      [...queryKeys.dx.all, "spots", params] as const,
    summary: () => [...queryKeys.dx.all, "summary"] as const,
    needs: () => [...queryKeys.dx.all, "needs"] as const,
    cluster: () => [...queryKeys.dx.all, "cluster"] as const,
  },
  log: {
    all: ["log"] as const,
    stats: () => [...queryKeys.log.all, "stats"] as const,
    recent: (limit: number) => [...queryKeys.log.all, "recent", limit] as const,
    dxcc: () => [...queryKeys.log.all, "dxcc"] as const,
  },
  pota: {
    all: ["pota"] as const,
    spots: () => [...queryKeys.pota.all, "spots"] as const,
    nearby: (grid: string, radius: number) =>
      [...queryKeys.pota.all, "nearby", grid, radius] as const,
  },
  contests: {
    all: ["contests"] as const,
    upcoming: (days: number) =>
      [...queryKeys.contests.all, "upcoming", days] as const,
    history: () => [...queryKeys.contests.all, "history"] as const,
    dashboard: (name: string) =>
      [...queryKeys.contests.all, "dashboard", name] as const,
  },
  allstar: {
    all: ["allstar"] as const,
    status: () => [...queryKeys.allstar.all, "status"] as const,
    connections: () => [...queryKeys.allstar.all, "connections"] as const,
    nodeInfo: (node: number) => [...queryKeys.allstar.all, "node", node] as const,
  },
  services: {
    all: ["services"] as const,
    inventory: () => [...queryKeys.services.all, "inventory"] as const,
    catalog: () => [...queryKeys.services.all, "catalog"] as const,
  },
}
