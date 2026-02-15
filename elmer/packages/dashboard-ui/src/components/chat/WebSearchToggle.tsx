import { cn } from "@/lib/utils"

type WebSearchMode = "auto" | "force" | "off"

interface WebSearchToggleProps {
  value: WebSearchMode
  onChange: (value: WebSearchMode) => void
}

const modes: { value: WebSearchMode; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "force", label: "On" },
  { value: "off", label: "Off" },
]

export function WebSearchToggle({ value, onChange }: WebSearchToggleProps) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-muted-foreground">Web Search</label>
      <div className="flex rounded-md border">
        {modes.map((mode) => (
          <button
            key={mode.value}
            onClick={() => onChange(mode.value)}
            className={cn(
              "flex-1 px-3 py-1.5 text-xs font-medium transition-colors",
              "first:rounded-l-md last:rounded-r-md",
              value === mode.value
                ? "bg-primary text-primary-foreground"
                : "hover:bg-accent",
            )}
          >
            {mode.label}
          </button>
        ))}
      </div>
    </div>
  )
}
