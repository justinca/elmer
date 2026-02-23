import { NavLink } from "react-router-dom"
import { cn } from "@/lib/utils"
import { navigation } from "@/lib/nav"
import { StatusDot } from "./StatusDot"
import { ChevronLeft, Moon, Sun } from "lucide-react"
import { useTheme } from "@/lib/theme"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useConnectionStatus } from "@/hooks/useConnectionStatus"
import { NotificationBell } from "./NotificationBell"
import { ElmerIcon } from "./ElmerIcon"

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const { theme, toggleTheme } = useTheme()
  const connected = useConnectionStatus()

  return (
    <aside
      className={cn(
        "flex h-screen flex-col bg-sidebar sidebar-border-glow sidebar-gradient transition-all duration-200",
        collapsed ? "w-16" : "w-56",
      )}
    >
      {/* Header */}
      <div
        className={cn(
          "flex h-14 items-center",
          collapsed ? "justify-center" : "justify-between px-3",
        )}
      >
        {collapsed ? (
          <Tooltip delayDuration={0}>
            <TooltipTrigger asChild>
              <button
                onClick={onToggle}
                className="relative h-8 w-8 flex items-center justify-center rounded-md hover:bg-sidebar-accent transition-colors"
              >
                <ElmerIcon size={20} />
                <StatusDot
                  status={connected ? "healthy" : "down"}
                  size="sm"
                  className="absolute -top-0.5 -right-0.5"
                />
              </button>
            </TooltipTrigger>
            <TooltipContent side="right">Expand sidebar</TooltipContent>
          </Tooltip>
        ) : (
          <>
            <div className="flex items-center gap-2">
              <ElmerIcon size={22} />
              <span className="text-lg font-bold text-primary">Elmer</span>
              <StatusDot status={connected ? "healthy" : "down"} size="sm" />
              <div className="ml-auto">
                <NotificationBell />
              </div>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={onToggle}
              className="h-8 w-8 shrink-0"
            >
              <ChevronLeft className="h-4 w-4 transition-transform" />
            </Button>
          </>
        )}
      </div>

      <Separator />

      {/* Navigation */}
      <ScrollArea className="min-h-0 flex-1 overflow-hidden py-2">
        <nav className="space-y-4 px-2">
          {navigation.map((group) => (
            <div key={group.label}>
              {!collapsed && (
                <p className="mb-1 px-2 text-xs font-semibold uppercase tracking-wider text-blue-500/80">
                  {group.label}
                </p>
              )}
              <div className="space-y-0.5">
                {group.items.map((item) => {
                  const link = (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      className={({ isActive }) =>
                        cn(
                          "flex items-center gap-3 rounded-md px-2 py-2 text-sm font-medium transition-all duration-150",
                          "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                          isActive
                            ? "bg-primary/10 text-primary nav-active-indicator"
                            : "text-sidebar-foreground/70 hover:translate-x-0.5",
                          collapsed && "justify-center px-0",
                        )
                      }
                    >
                      <item.icon className="h-4 w-4 shrink-0" />
                      {!collapsed && <span>{item.label}</span>}
                    </NavLink>
                  )

                  if (collapsed) {
                    return (
                      <Tooltip key={item.path} delayDuration={0}>
                        <TooltipTrigger asChild>{link}</TooltipTrigger>
                        <TooltipContent side="right">{item.label}</TooltipContent>
                      </Tooltip>
                    )
                  }
                  return link
                })}
              </div>
            </div>
          ))}
        </nav>
      </ScrollArea>

      <Separator />

      {/* Footer */}
      <div className="flex items-center justify-center p-2">
        <Tooltip delayDuration={0}>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon" onClick={toggleTheme} className="h-8 w-8">
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right">
            {theme === "dark" ? "Light mode" : "Dark mode"}
          </TooltipContent>
        </Tooltip>
      </div>
    </aside>
  )
}
