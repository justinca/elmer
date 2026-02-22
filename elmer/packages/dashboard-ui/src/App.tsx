import { BrowserRouter, Routes, Route } from "react-router-dom"
import { QueryClientProvider } from "@tanstack/react-query"
import { queryClient } from "@/lib/queryClient"
import { TooltipProvider } from "@/components/ui/tooltip"
import { Toaster } from "@/components/ui/sonner"
import { ThemeProvider } from "@/lib/theme"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { AppLayout } from "@/components/AppLayout"
import { lazy } from "react"

const SystemStatus = lazy(() => import("@/pages/SystemStatus"))
const Services = lazy(() => import("@/pages/Services"))
const Events = lazy(() => import("@/pages/Events"))
const Knowledge = lazy(() => import("@/pages/Knowledge"))
const Notes = lazy(() => import("@/pages/Notes"))
const Transcriptions = lazy(() => import("@/pages/Transcriptions"))
const SearchPage = lazy(() => import("@/pages/Search"))
const Chat = lazy(() => import("@/pages/Chat"))
const Agents = lazy(() => import("@/pages/Agents"))
const AgentBuilder = lazy(() => import("@/pages/AgentBuilder"))
const AgentRuns = lazy(() => import("@/pages/AgentRuns"))
const OrchestratorPage = lazy(() => import("@/pages/Orchestrator"))
const Propagation = lazy(() => import("@/pages/Propagation"))
const DXSpots = lazy(() => import("@/pages/DXSpots"))
const LogAnalysis = lazy(() => import("@/pages/LogAnalysis"))
const Contests = lazy(() => import("@/pages/Contests"))
const POTA = lazy(() => import("@/pages/POTA"))
const BandScanner = lazy(() => import("@/pages/BandScanner"))
const AllStar = lazy(() => import("@/pages/AllStar"))
const NotFound = lazy(() => import("@/pages/NotFound"))

function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <TooltipProvider>
            <BrowserRouter>
              <Routes>
                <Route element={<AppLayout />}>
                  <Route index element={<SystemStatus />} />
                  <Route path="events" element={<Events />} />
                  <Route path="services" element={<Services />} />
                  <Route path="documents" element={<Knowledge />} />
                  <Route path="notes" element={<Notes />} />
                  <Route path="transcriptions" element={<Transcriptions />} />
                  <Route path="search" element={<SearchPage />} />
                  <Route path="chat" element={<Chat />} />
                  <Route path="agents" element={<Agents />} />
                  <Route path="agents/builder" element={<AgentBuilder />} />
                  <Route path="agents/runs" element={<AgentRuns />} />
                  <Route path="agents/orchestrator" element={<OrchestratorPage />} />
                  <Route path="propagation" element={<Propagation />} />
                  <Route path="dx-spots" element={<DXSpots />} />
                  <Route path="log" element={<LogAnalysis />} />
                  <Route path="contests" element={<Contests />} />
                  <Route path="pota" element={<POTA />} />
                  <Route path="band-map" element={<BandScanner />} />
                  <Route path="allstar" element={<AllStar />} />
                  <Route path="*" element={<NotFound />} />
                </Route>
              </Routes>
            </BrowserRouter>
            <Toaster />
          </TooltipProvider>
        </ThemeProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}

export default App
