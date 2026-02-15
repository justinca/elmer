import { useEffect, useRef, useState } from "react"
import { Input } from "@/components/ui/input"
import { Search, X, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

interface SearchBarProps {
  placeholder?: string
  onSearch: (query: string) => void
  loading?: boolean
  debounceMs?: number
  className?: string
}

export function SearchBar({
  placeholder = "Search...",
  onSearch,
  loading = false,
  debounceMs = 300,
  className,
}: SearchBarProps) {
  const [value, setValue] = useState("")
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      onSearch(value.trim())
    }, debounceMs)
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [value, debounceMs, onSearch])

  const clear = () => {
    setValue("")
    onSearch("")
  }

  return (
    <div className={cn("relative", className)}>
      <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder}
        className="pl-9 pr-9"
      />
      {loading && (
        <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-muted-foreground" />
      )}
      {!loading && value && (
        <button
          onClick={clear}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  )
}
