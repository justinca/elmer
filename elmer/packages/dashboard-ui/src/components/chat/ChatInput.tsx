import { useRef, useEffect, type KeyboardEvent } from "react"
import { Button } from "@/components/ui/button"
import { SendHorizontal } from "lucide-react"
import { cn } from "@/lib/utils"

interface ChatInputProps {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  disabled?: boolean
  placeholder?: string
  className?: string
}

export function ChatInput({
  value,
  onChange,
  onSend,
  disabled = false,
  placeholder = "Type a message...",
  className,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-resize
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = Math.min(el.scrollHeight, 128) + "px"
  }, [value])

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      if (value.trim() && !disabled) onSend()
    }
  }

  return (
    <div className={cn("flex items-end gap-2", className)}>
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        rows={1}
        className={cn(
          "flex-1 resize-none rounded-lg border bg-background px-3 py-2.5 text-sm",
          "placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring",
          "disabled:opacity-50",
          "max-h-32 hide-scrollbar",
        )}
      />
      <Button
        size="icon"
        onClick={onSend}
        disabled={!value.trim() || disabled}
        className="h-10 w-10 shrink-0"
      >
        <SendHorizontal className="h-4 w-4" />
      </Button>
    </div>
  )
}

export function focusChatInput() {
  const el = document.querySelector<HTMLTextAreaElement>("textarea")
  el?.focus()
}
