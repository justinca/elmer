import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function mapStatus(s: string): "healthy" | "degraded" | "down" | "unknown" {
  if (s === "healthy" || s === "online" || s === "ok") return "healthy"
  if (s === "degraded" || s === "warning") return "degraded"
  if (s === "down" || s === "offline" || s === "error") return "down"
  return "unknown"
}
