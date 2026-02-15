import { Outlet, useLocation } from "react-router-dom"
import { Suspense, useState, useEffect, useRef } from "react"
import { Sidebar } from "./Sidebar"
import { MobileSidebar } from "./MobileSidebar"
import { LoadingSpinner } from "./LoadingSpinner"
import { Breadcrumbs } from "./Breadcrumbs"
import { NotificationBell } from "./NotificationBell"
import { CommandPalette } from "./CommandPalette"

export function AppLayout() {
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(() => {
    return localStorage.getItem("elmer-sidebar-collapsed") === "true"
  })
  const [paletteOpen, setPaletteOpen] = useState(false)
  const contentRef = useRef<HTMLDivElement>(null)

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

  // Reset scroll position on route change
  useEffect(() => {
    if (contentRef.current) {
      contentRef.current.scrollTop = 0
    }
  }, [location.pathname])

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
        {isFullBleed ? (
          <div className="relative flex-1">
            <div className="absolute inset-0 flex">
              <Suspense fallback={<LoadingSpinner label="Loading..." />}>
                <Outlet />
              </Suspense>
            </div>
          </div>
        ) : (
          <div ref={contentRef} className="flex-1 min-h-0 overflow-y-auto p-4 md:p-6">
            <Suspense fallback={<LoadingSpinner label="Loading..." />}>
              <div key={location.pathname} className="animate-in fade-in duration-150">
                <Breadcrumbs />
                <Outlet />
              </div>
            </Suspense>
          </div>
        )}
      </main>

      {/* Command palette */}
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  )
}
