import { NavLink } from "react-router-dom"
import { cn } from "@/lib/utils"
import { navigation } from "@/lib/nav"
import { Menu, Moon, Sun } from "lucide-react"
import { useTheme } from "@/lib/theme"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import { StatusDot } from "./StatusDot"
import { NotificationBell } from "./NotificationBell"
import { useConnectionStatus } from "@/hooks/useConnectionStatus"
import { useState } from "react"

export function MobileSidebar() {
  const { theme, toggleTheme } = useTheme()
  const connected = useConnectionStatus()
  const [open, setOpen] = useState(false)

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="md:hidden">
          <Menu className="h-5 w-5" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-64 p-0">
        <div className="flex h-14 items-center justify-between px-4">
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold text-primary">Elmer</span>
            <StatusDot status={connected ? "healthy" : "down"} size="sm" />
          </div>
          <NotificationBell />
        </div>
        <Separator />
        <ScrollArea className="flex-1 py-2">
          <nav className="space-y-4 px-3">
            {navigation.map((group) => (
              <div key={group.label}>
                <p className="mb-1 px-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {group.label}
                </p>
                <div className="space-y-0.5">
                  {group.items.map((item) => (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      onClick={() => setOpen(false)}
                      className={({ isActive }) =>
                        cn(
                          "flex items-center gap-3 rounded-md px-2 py-2 text-sm font-medium transition-colors",
                          "hover:bg-accent hover:text-accent-foreground",
                          isActive
                            ? "bg-accent text-accent-foreground"
                            : "text-foreground/70",
                        )
                      }
                    >
                      <item.icon className="h-4 w-4" />
                      <span>{item.label}</span>
                    </NavLink>
                  ))}
                </div>
              </div>
            ))}
          </nav>
        </ScrollArea>
        <Separator />
        <div className="flex items-center justify-center p-2">
          <Button variant="ghost" size="icon" onClick={toggleTheme} className="h-8 w-8">
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  )
}
