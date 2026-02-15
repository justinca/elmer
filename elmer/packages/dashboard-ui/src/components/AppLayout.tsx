import { Outlet } from "react-router-dom"
import { useState } from "react"
import { Sidebar } from "./Sidebar"
import { MobileSidebar } from "./MobileSidebar"
import { cn } from "@/lib/utils"

export function AppLayout() {
  const [collapsed, setCollapsed] = useState(() => {
    return localStorage.getItem("elmer-sidebar-collapsed") === "true"
  })

  const handleToggle = () => {
    setCollapsed((prev) => {
      localStorage.setItem("elmer-sidebar-collapsed", String(!prev))
      return !prev
    })
  }

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Desktop sidebar */}
      <div className="hidden md:flex">
        <Sidebar collapsed={collapsed} onToggle={handleToggle} />
      </div>

      {/* Main content */}
      <main className="flex flex-1 flex-col overflow-hidden">
        {/* Mobile header */}
        <div className="flex h-14 items-center border-b px-4 md:hidden">
          <MobileSidebar />
          <span className="ml-2 text-lg font-bold text-primary">Elmer</span>
        </div>

        {/* Page content */}
        <div
          className={cn(
            "flex-1 overflow-y-auto p-4 md:p-6",
          )}
        >
          <Outlet />
        </div>
      </main>
    </div>
  )
}
