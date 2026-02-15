import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

interface Model {
  name: string
  size: number | null
}

interface ModelSelectorProps {
  models: Model[]
  value: string
  onChange: (value: string) => void
}

function formatSize(bytes: number | null): string {
  if (!bytes) return ""
  const gb = bytes / 1e9
  return gb >= 1 ? `${gb.toFixed(1)}GB` : `${(bytes / 1e6).toFixed(0)}MB`
}

export function ModelSelector({ models, value, onChange }: ModelSelectorProps) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-muted-foreground">Model</label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="h-8 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {models.map((m) => (
            <SelectItem key={m.name} value={m.name} className="text-xs">
              {m.name} {m.size ? `(${formatSize(m.size)})` : ""}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
