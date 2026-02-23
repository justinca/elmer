import { cn } from "@/lib/utils"
import { Bot } from "lucide-react"

interface ElmerIconProps {
  className?: string
  size?: number
}

export function ElmerIcon({ className, size = 24 }: ElmerIconProps) {
  return (
    <Bot
      width={size}
      height={size}
      className={cn("shrink-0 text-blue-500", className)}
    />
  )
}
