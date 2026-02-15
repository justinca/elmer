import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import cronstrue from "cronstrue"
import { cn } from "@/lib/utils"

interface CronInputProps {
  value: string
  onChange: (value: string) => void
  className?: string
}

const presets = [
  { label: "Every hour", cron: "0 * * * *" },
  { label: "Daily 8am", cron: "0 8 * * *" },
  { label: "Every 15 min", cron: "*/15 * * * *" },
  { label: "Weekdays 7am", cron: "0 7 * * 1-5" },
]

function describeCron(expr: string): string {
  if (!expr.trim()) return ""
  try {
    return cronstrue.toString(expr, { use24HourTimeFormat: true })
  } catch {
    return "Invalid cron expression"
  }
}

export function CronInput({ value, onChange, className }: CronInputProps) {
  const description = describeCron(value)
  const isValid = value.trim() && description !== "Invalid cron expression"

  return (
    <div className={cn("space-y-1.5", className)}>
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="0 8 * * *"
        className="font-mono text-sm"
      />
      {description && (
        <p className={cn("text-xs", isValid ? "text-muted-foreground" : "text-destructive")}>
          {description}
        </p>
      )}
      <div className="flex flex-wrap gap-1">
        {presets.map((p) => (
          <Button
            key={p.cron}
            type="button"
            variant="outline"
            size="sm"
            className="h-6 text-xs"
            onClick={() => onChange(p.cron)}
          >
            {p.label}
          </Button>
        ))}
      </div>
    </div>
  )
}
