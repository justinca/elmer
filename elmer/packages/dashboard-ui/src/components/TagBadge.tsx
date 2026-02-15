import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

interface TagBadgeProps {
  tag: string
  onClick?: (tag: string) => void
  active?: boolean
  size?: "sm" | "md"
  className?: string
}

export function TagBadge({ tag, onClick, active, size = "sm", className }: TagBadgeProps) {
  return (
    <Badge
      variant={active ? "default" : "secondary"}
      className={cn(
        "cursor-default transition-colors",
        onClick && "cursor-pointer hover:bg-primary/20",
        size === "sm" && "text-xs px-2 py-0",
        size === "md" && "text-sm px-2.5 py-0.5",
        className,
      )}
      onClick={() => onClick?.(tag)}
    >
      {tag}
    </Badge>
  )
}
