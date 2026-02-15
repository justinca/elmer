import { Badge } from "@/components/ui/badge"
import { Globe } from "lucide-react"

interface WebSearchBadgeProps {
  query: string
}

export function WebSearchBadge({ query }: WebSearchBadgeProps) {
  return (
    <Badge variant="outline" className="gap-1 text-xs font-normal">
      <Globe className="h-3 w-3" />
      Searched: {query}
    </Badge>
  )
}
