import { cn } from "@/lib/utils"
import { Loader2 } from "lucide-react"

interface LoadingSpinnerProps {
  className?: string
  size?: number
  label?: string
}

export function LoadingSpinner({ className, size = 24, label }: LoadingSpinnerProps) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-2 py-12", className)}>
      <Loader2 className="animate-spin text-muted-foreground" size={size} />
      {label && <p className="text-sm text-muted-foreground">{label}</p>}
    </div>
  )
}
