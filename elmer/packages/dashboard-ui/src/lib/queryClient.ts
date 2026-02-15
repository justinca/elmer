import { QueryClient } from "@tanstack/react-query"

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      refetchOnWindowFocus: true,
      staleTime: 30_000,
    },
  },
})

export const STALE_TIMES = {
  health: 30_000,
  propagation: 300_000,
  dxSpots: 30_000,
  agents: 60_000,
  knowledge: 300_000,
  notes: 60_000,
  transcriptions: 60_000,
  orchestrator: 10_000,
  contests: 60_000,
  pota: 60_000,
  log: 60_000,
  bandScanner: 30_000,
  models: 300_000,
} as const
