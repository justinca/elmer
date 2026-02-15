import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { ReactNode } from "react"

interface SlidePanelProps {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
}

export function SlidePanel({ open, onClose, title, children }: SlidePanelProps) {
  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-xl md:max-w-2xl p-0">
        <SheetHeader className="border-b px-6 py-4">
          <SheetTitle>{title}</SheetTitle>
        </SheetHeader>
        <ScrollArea className="h-[calc(100vh-5rem)]">
          <div className="px-6 py-4">{children}</div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}
