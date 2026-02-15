import ReactMarkdown from "react-markdown"
import rehypeHighlight from "rehype-highlight"
import { cn } from "@/lib/utils"

interface MarkdownRendererProps {
  content: string
  className?: string
}

export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  return (
    <div
      className={cn(
        "prose prose-sm dark:prose-invert max-w-none",
        "prose-headings:font-semibold prose-headings:tracking-tight",
        "prose-p:leading-relaxed prose-p:text-foreground/90",
        "prose-a:text-primary prose-a:no-underline hover:prose-a:underline",
        "prose-code:rounded prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:text-sm",
        "prose-pre:bg-muted prose-pre:border prose-pre:border-border",
        "prose-blockquote:border-l-primary",
        "prose-li:text-foreground/90",
        className,
      )}
    >
      <ReactMarkdown rehypePlugins={[rehypeHighlight]}>{content}</ReactMarkdown>
    </div>
  )
}
