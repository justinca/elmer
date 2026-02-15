import { useState } from "react"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import { CheckCircle2, XCircle } from "lucide-react"

interface JSONEditorProps {
  value: string
  onChange: (value: string) => void
  label?: string
  rows?: number
  className?: string
}

export function JSONEditor({ value, onChange, label, rows = 4, className }: JSONEditorProps) {
  const [error, setError] = useState<string | null>(null)
  const [touched, setTouched] = useState(false)

  const validate = (v: string) => {
    if (!v.trim() || v.trim() === "{}") {
      setError(null)
      return
    }
    try {
      JSON.parse(v)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Invalid JSON")
    }
  }

  return (
    <div className={cn("space-y-1", className)}>
      {label && <label className="text-sm font-medium">{label}</label>}
      <Textarea
        value={value}
        onChange={(e) => {
          onChange(e.target.value)
          if (touched) validate(e.target.value)
        }}
        onBlur={() => {
          setTouched(true)
          validate(value)
        }}
        rows={rows}
        className="font-mono text-sm"
        placeholder="{}"
      />
      {touched && (
        <div className="flex items-center gap-1">
          {error ? (
            <>
              <XCircle className="h-3 w-3 text-destructive" />
              <span className="text-xs text-destructive">{error}</span>
            </>
          ) : (
            <>
              <CheckCircle2 className="h-3 w-3 text-emerald-500" />
              <span className="text-xs text-emerald-500">Valid JSON</span>
            </>
          )}
        </div>
      )}
    </div>
  )
}
