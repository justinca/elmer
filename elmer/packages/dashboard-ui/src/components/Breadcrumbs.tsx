import { useLocation, Link } from "react-router-dom"
import { ChevronRight, Home } from "lucide-react"
import { navigation } from "@/lib/nav"

export function Breadcrumbs() {
  const location = useLocation()
  const segments = location.pathname.split("/").filter(Boolean)

  if (segments.length === 0) return null

  const crumbs = segments.map((seg, i) => {
    const path = "/" + segments.slice(0, i + 1).join("/")
    for (const group of navigation) {
      for (const item of group.items) {
        if (item.path === path) return { label: item.label, path }
      }
    }
    return {
      label: seg.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      path,
    }
  })

  return (
    <nav className="flex items-center gap-1 text-sm text-muted-foreground mb-4">
      <Link to="/" className="hover:text-foreground transition-colors">
        <Home className="h-3.5 w-3.5" />
      </Link>
      {crumbs.map((crumb, i) => (
        <span key={crumb.path} className="flex items-center gap-1">
          <ChevronRight className="h-3 w-3" />
          {i === crumbs.length - 1 ? (
            <span className="text-foreground font-medium">{crumb.label}</span>
          ) : (
            <Link to={crumb.path} className="hover:text-foreground transition-colors">
              {crumb.label}
            </Link>
          )}
        </span>
      ))}
    </nav>
  )
}
