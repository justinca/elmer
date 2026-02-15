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
        "flex h-screen flex-col border-r border-sidebar-border bg-sidebar transition-all duration-200",
        collapsed ? "w-16" : "w-56",
      )}
    >
      {/* Header */}
      <div className="flex h-14 items-center justify-between px-3">
        {!collapsed && (
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold text-primary">Elmer</span>
            <StatusDot status={connected ? "healthy" : "down"} size="sm" />
            <div className="ml-auto">
              <NotificationBell />
            </div>
          </div>
        )}
        {collapsed && (
          <div className="flex w-full justify-center">
            <StatusDot status={connected ? "healthy" : "down"} size="sm" />
          </div>
        )}
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggle}
          className={cn("h-8 w-8 shrink-0", collapsed && "mx-auto")}
        >
          <ChevronLeft
            className={cn(
              "h-4 w-4 transition-transform",
              collapsed && "rotate-180",
            )}
          />
        </Button>
      </div>

      <Separator />

      {/* Navigation */}
      <ScrollArea className="flex-1 py-2">
        <nav className="space-y-4 px-2">
          {navigation.map((group) => (
            <div key={group.label}>
              {!collapsed && (
                <p className="mb-1 px-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
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
                          "flex items-center gap-3 rounded-md px-2 py-2 text-sm font-medium transition-colors",
                          "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                          isActive
                            ? "bg-sidebar-accent text-sidebar-accent-foreground"
                            : "text-sidebar-foreground/70",
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
