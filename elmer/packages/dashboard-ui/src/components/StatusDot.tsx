import { cn } from "@/lib/utils"

interface StatusDotProps {
  status: "healthy" | "degraded" | "down" | "unknown"
  size?: "sm" | "md" | "lg"
  pulse?: boolean
  className?: string
}

const statusColors = {
  healthy: "bg-[#10B981]",
  degraded: "bg-[#EAB308]",
  down: "bg-[#EF4444]",
  unknown: "bg-[#94A3B8]",
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
