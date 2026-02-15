import { Outlet, useLocation } from "react-router-dom"
import { Suspense, useState, useEffect } from "react"
import { Sidebar } from "./Sidebar"
import { MobileSidebar } from "./MobileSidebar"
import { LoadingSpinner } from "./LoadingSpinner"
import { Breadcrumbs } from "./Breadcrumbs"
import { NotificationBell } from "./NotificationBell"
import { CommandPalette } from "./CommandPalette"
import { cn } from "@/lib/utils"

export function AppLayout() {
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(() => {
    return localStorage.getItem("elmer-sidebar-collapsed") === "true"
  })
  const [paletteOpen, setPaletteOpen] = useState(false)

  const handleToggle = () => {
    setCollapsed((prev) => {
      localStorage.setItem("elmer-sidebar-collapsed", String(!prev))
      return !prev
    })
  }

  // Global Cmd/Ctrl+K shortcut
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault()
        setPaletteOpen((prev) => !prev)
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [])

  const isFullBleed = location.pathname === "/chat"

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Desktop sidebar */}
      <div className="hidden md:flex">
        <Sidebar collapsed={collapsed} onToggle={handleToggle} />
      </div>

      {/* Main content */}
      <main className="flex flex-1 flex-col overflow-hidden">
        {/* Mobile header */}
        <div className="flex h-14 items-center justify-between border-b px-4 md:hidden">
          <div className="flex items-center">
            <MobileSidebar />
            <span className="ml-2 text-lg font-bold text-primary">Elmer</span>
          </div>
          <NotificationBell />
        </div>

        {/* Page content */}
        <div
          className={cn(
            "flex-1",
            isFullBleed
              ? "flex flex-col overflow-hidden"
              : "overflow-y-auto p-4 md:p-6",
          )}
        >
          <Suspense fallback={<LoadingSpinner label="Loading..." />}>
            <div key={location.pathname} className={cn("animate-in fade-in duration-150", isFullBleed && "flex flex-1 flex-col overflow-hidden")}>
              {!isFullBleed && <Breadcrumbs />}
              <Outlet />
            </div>
          </Suspense>
        </div>
      </main>

      {/* Command palette */}
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  )
}
