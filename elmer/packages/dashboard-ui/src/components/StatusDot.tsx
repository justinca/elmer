import { cn } from "@/lib/utils"

interface StatusDotProps {
  status: "healthy" | "degraded" | "down" | "unknown"
  size?: "sm" | "md" | "lg"
  pulse?: boolean
  className?: string
}

const statusColors = {
  healthy: "bg-emerald-500",
  degraded: "bg-amber-500",
  down: "bg-red-500",
  unknown: "bg-gray-500",
}

const sizes = {
  sm: "h-2 w-2",
  md: "h-3 w-3",
  lg: "h-4 w-4",
}

export function StatusDot({ status, size = "md", pulse = true, className }: StatusDotProps) {
  return (
    <span className={cn("relative inline-flex", className)}>
      {pulse && status === "healthy" && (
        <span
          className={cn(
            "absolute inline-flex h-full w-full animate-ping rounded-full opacity-75",
            statusColors[status],
          )}
        />
      )}
      <span
        className={cn("relative inline-flex rounded-full", sizes[size], statusColors[status])}
      />
    </span>
  )
}
