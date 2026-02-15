import { BrowserRouter, Routes, Route } from "react-router-dom"
import { TooltipProvider } from "@/components/ui/tooltip"
import { Toaster } from "@/components/ui/sonner"
import { ThemeProvider } from "@/lib/theme"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { AppLayout } from "@/components/AppLayout"
import { lazy } from "react"

const SystemStatus = lazy(() => import("@/pages/SystemStatus"))
const Placeholder = lazy(() => import("@/pages/Placeholder"))

function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <TooltipProvider>
          <BrowserRouter>
            <Routes>
              <Route element={<AppLayout />}>
                <Route index element={<SystemStatus />} />
                <Route path="events" element={<Placeholder />} />
                <Route path="documents" element={<Placeholder />} />
                <Route path="search" element={<Placeholder />} />
                <Route path="chat" element={<Placeholder />} />
                <Route path="agents" element={<Placeholder />} />
                <Route path="propagation" element={<Placeholder />} />
                <Route path="dx-spots" element={<Placeholder />} />
                <Route path="log" element={<Placeholder />} />
                <Route path="contests" element={<Placeholder />} />
                <Route path="pota" element={<Placeholder />} />
                <Route path="band-map" element={<Placeholder />} />
                <Route path="*" element={<Placeholder />} />
              </Route>
            </Routes>
          </BrowserRouter>
          <Toaster />
        </TooltipProvider>
      </ThemeProvider>
    </ErrorBoundary>
  )
}

export default App
