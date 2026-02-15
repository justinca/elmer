import { useState, useEffect, useCallback, useRef } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { queryKeys } from "@/lib/queryKeys"
import { STALE_TIMES } from "@/lib/queryClient"
import { useDocumentTitle } from "@/hooks/useDocumentTitle"
import { toast } from "sonner"
import { cn } from "@/lib/utils"
import { sendChat, getConversations, getConversation, deleteConversation, getModels } from "@/lib/api"
import { ConversationList, type ConversationSummary } from "@/components/chat/ConversationList"
import { MessageBubble, type ChatMessage, type SourceUsed, type WebSource } from "@/components/chat/MessageBubble"
import { ChatInput, focusChatInput } from "@/components/chat/ChatInput"
import { TypingIndicator } from "@/components/chat/TypingIndicator"
import { SourcesPanel } from "@/components/chat/SourcesPanel"
import { WebSearchToggle } from "@/components/chat/WebSearchToggle"
import { ModelSelector } from "@/components/chat/ModelSelector"
import { ConfirmDialog } from "@/components/ConfirmDialog"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Bot, MessageSquare, PanelRightClose, PanelRightOpen, PanelLeftClose, PanelLeftOpen, Sparkles } from "lucide-react"

type WebSearchMode = "auto" | "force" | "off"

interface Model {
  name: string
  size: number | null
}

const SUGGESTIONS = [
  "What propagation conditions are expected this weekend?",
  "Summarize my recent QSOs",
  "What POTA parks are near me?",
  "Search my notes for antenna projects",
]

function Chat() {
  useDocumentTitle("Chat")
  const queryClient = useQueryClient()

  // Conversations via useQuery
  const { data: conversations = [], isLoading: convoLoading } = useQuery({
    queryKey: queryKeys.chat.conversations(),
    queryFn: () => getConversations().then(({ data }) => (data.conversations || data || []) as ConversationSummary[]),
    staleTime: STALE_TIMES.notes, // 60s is fine for conversation list
  })

  // Models via useQuery
  const { data: models = [] } = useQuery({
    queryKey: queryKeys.chat.models(),
    queryFn: () =>
      getModels().then(({ data }) =>
        ((data.models || []) as Array<{ name: string; size?: number }>).map((m) => ({
          name: m.name,
          size: m.size ?? null,
        })) as Model[],
      ),
    staleTime: STALE_TIMES.models,
  })

  const [activeConvoId, setActiveConvoId] = useState<number | null>(null)

  // Messages
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)

  // Model selection — persist to localStorage
  const [selectedModel, setSelectedModel] = useState(() => {
    return localStorage.getItem("elmer-chat-model") || ""
  })

  // Settings
  const [webSearch, setWebSearch] = useState<WebSearchMode>("auto")

  // UI
  const [showLeftPanel, setShowLeftPanel] = useState(true)
  const [showRightPanel, setShowRightPanel] = useState(false)
  const [panelSources, setPanelSources] = useState<SourceUsed[]>([])
  const [panelWebSources, setPanelWebSources] = useState<WebSource[]>([])
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const scrollAreaRef = useRef<HTMLDivElement>(null)

  // Set default model when models load, persist selection
  useEffect(() => {
    if (models.length > 0 && !selectedModel) {
      setSelectedModel(models[0].name)
    }
  }, [models, selectedModel])

  useEffect(() => {
    if (selectedModel) {
      localStorage.setItem("elmer-chat-model", selectedModel)
    }
  }, [selectedModel])

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, sending])

  // Load a conversation's messages
  const loadConversation = useCallback(async (id: number) => {
    setActiveConvoId(id)
    setMessages([])
    try {
      const { data } = await getConversation(id)
      const msgs: ChatMessage[] = (data.messages || []).map(
        (m: { role: string; content: string; created_at?: string; sources_used?: SourceUsed[]; web_sources?: WebSource[]; web_search_performed?: boolean; web_search_query?: string }, i: number) => ({
          id: `${id}-${i}`,
          role: m.role as "user" | "assistant",
          content: m.content,
          timestamp: m.created_at ? new Date(m.created_at) : new Date(),
          conversationId: id,
          sourcesUsed: m.sources_used,
          webSources: m.web_sources,
          webSearchPerformed: m.web_search_performed,
          webSearchQuery: m.web_search_query,
        }),
      )
      setMessages(msgs)
    } catch {
      toast.error("Failed to load conversation")
    }
  }, [])

  // New conversation
  const handleNewConversation = useCallback(() => {
    setActiveConvoId(null)
    setMessages([])
    setInput("")
    setPanelSources([])
    setPanelWebSources([])
    setShowRightPanel(false)
    setTimeout(focusChatInput, 50)
  }, [])

  // Delete conversation
  const handleDelete = useCallback(async () => {
    if (deleteId === null) return
    try {
      await deleteConversation(deleteId)
      if (activeConvoId === deleteId) {
        handleNewConversation()
      }
      queryClient.invalidateQueries({ queryKey: queryKeys.chat.conversations() })
      toast.success("Conversation deleted")
    } catch {
      toast.error("Failed to delete conversation")
    } finally {
      setDeleteId(null)
    }
  }, [deleteId, activeConvoId, handleNewConversation, queryClient])

  // Send message
  const handleSend = useCallback(async () => {
    const text = input.trim()
    if (!text || sending) return

    const userMsg: ChatMessage = {
      id: `tmp-${Date.now()}`,
      role: "user",
      content: text,
      timestamp: new Date(),
    }

    setMessages((prev) => [...prev, userMsg])
    setInput("")
    setSending(true)

    try {
      const { data } = await sendChat({
        message: text,
        conversation_id: activeConvoId,
        model: selectedModel || undefined,
        web_search: webSearch,
      })

      const assistantMsg: ChatMessage = {
        id: `resp-${Date.now()}`,
        role: "assistant",
        content: data.response,
        timestamp: new Date(),
        conversationId: data.conversation_id,
        sourcesUsed: data.sources_used,
        webSearchPerformed: data.web_search_performed,
        webSearchQuery: data.web_search_query,
        webSources: data.web_sources,
      }

      setMessages((prev) => [...prev, assistantMsg])

      // Update active conversation ID if this was the first message
      if (!activeConvoId && data.conversation_id) {
        setActiveConvoId(data.conversation_id)
      }

      // Refresh conversation list
      queryClient.invalidateQueries({ queryKey: queryKeys.chat.conversations() })
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Failed to send message"
      const errChat: ChatMessage = {
        id: `err-${Date.now()}`,
        role: "assistant",
        content: "",
        timestamp: new Date(),
        error: errorMsg,
      }
      setMessages((prev) => [...prev, errChat])
    } finally {
      setSending(false)
      setTimeout(focusChatInput, 50)
    }
  }, [input, sending, activeConvoId, selectedModel, webSearch, queryClient])

  // Retry last failed message
  const handleRetry = useCallback(() => {
    setMessages((prev) => {
      const last = prev[prev.length - 1]
      if (last?.error) {
        // Find the last user message
        const userMsgs = prev.filter((m) => m.role === "user")
        const lastUserMsg = userMsgs[userMsgs.length - 1]
        if (lastUserMsg) {
          setInput(lastUserMsg.content)
        }
        return prev.slice(0, -1) // Remove error message
      }
      return prev
    })
    setTimeout(() => {
      // Send will be triggered by user pressing Enter again
      focusChatInput()
    }, 50)
  }, [])

  // Show sources panel
  const handleShowSources = useCallback((sources: SourceUsed[], webSources: WebSource[]) => {
    setPanelSources(sources)
    setPanelWebSources(webSources)
    setShowRightPanel(true)
  }, [])

  // Send suggestion
  const handleSuggestion = useCallback(
    (text: string) => {
      setInput(text)
      setTimeout(focusChatInput, 50)
    },
    [],
  )

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Ctrl+N: new conversation
      if ((e.ctrlKey || e.metaKey) && e.key === "n") {
        e.preventDefault()
        handleNewConversation()
      }
      // Escape: close source panel
      if (e.key === "Escape" && showRightPanel) {
        setShowRightPanel(false)
      }
      // / to focus chat input (only when not typing)
      if (e.key === "/" && !(e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement)) {
        e.preventDefault()
        focusChatInput()
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [handleNewConversation, showRightPanel])

  const isWelcome = messages.length === 0 && !activeConvoId

  return (
    <div className="flex flex-1 min-h-0 overflow-hidden">
      {/* Left panel -- Conversation list */}
      <div
        className={cn(
          "border-r bg-background transition-all duration-200",
          showLeftPanel ? "w-64 min-w-[16rem]" : "w-0 min-w-0 overflow-hidden border-r-0",
        )}
      >
        {showLeftPanel && (
          <ConversationList
            conversations={conversations}
            activeId={activeConvoId}
            loading={convoLoading}
            onSelect={loadConversation}
            onNew={handleNewConversation}
            onDelete={(id) => setDeleteId(id)}
          />
        )}
      </div>

      {/* Center -- Chat area */}
      <div className="flex min-w-0 min-h-0 flex-1 flex-col">
        {/* Toolbar */}
        <div className="flex items-center gap-2 border-b px-4 py-2">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            onClick={() => setShowLeftPanel(!showLeftPanel)}
          >
            {showLeftPanel ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
          </Button>

          <div className="flex flex-1 items-center gap-3 overflow-x-auto">
            <ModelSelector models={models} value={selectedModel} onChange={setSelectedModel} />
            <WebSearchToggle value={webSearch} onChange={setWebSearch} />
          </div>

          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            onClick={() => setShowRightPanel(!showRightPanel)}
          >
            {showRightPanel ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}
          </Button>
        </div>

        {/* Messages */}
        <ScrollArea className="flex-1 min-h-0" ref={scrollAreaRef}>
          <div className="mx-auto max-w-3xl space-y-6 p-4">
            {isWelcome ? (
              <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
                <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
                  <Bot className="h-8 w-8 text-primary" />
                </div>
                <h2 className="mb-2 text-xl font-semibold">Elmer Chat</h2>
                <p className="mb-8 max-w-md text-sm text-muted-foreground">
                  Ask questions about your knowledge base, notes, radio logs, and more.
                  Elmer uses RAG to search your data and can browse the web.
                </p>
                <div className="grid gap-3 sm:grid-cols-2">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => handleSuggestion(s)}
                      className="flex items-start gap-2 rounded-lg border p-3 text-left text-sm transition-colors hover:bg-accent"
                    >
                      <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <>
                {messages.map((msg) => (
                  <MessageBubble
                    key={msg.id}
                    message={msg}
                    onShowSources={handleShowSources}
                    onRetry={msg.error ? handleRetry : undefined}
                  />
                ))}
                {sending && <TypingIndicator />}
              </>
            )}
            <div ref={messagesEndRef} />
          </div>
        </ScrollArea>

        {/* Input area */}
        <div className="border-t bg-background p-4">
          <div className="mx-auto max-w-3xl">
            <ChatInput
              value={input}
              onChange={setInput}
              onSend={handleSend}
              disabled={sending}
              placeholder={activeConvoId ? "Continue the conversation..." : "Ask Elmer anything..."}
            />
            <div className="mt-1.5 flex items-center justify-between text-[10px] text-muted-foreground/60">
              <span>
                {activeConvoId ? (
                  <span className="inline-flex items-center gap-1">
                    <MessageSquare className="h-3 w-3" /> Conversation #{activeConvoId}
                  </span>
                ) : (
                  "New conversation"
                )}
              </span>
              <span>Enter to send, Shift+Enter for newline</span>
            </div>
          </div>
        </div>
      </div>

      {/* Right panel -- Sources */}
      <div
        className={cn(
          "border-l bg-background transition-all duration-200",
          showRightPanel ? "w-72 min-w-[18rem]" : "w-0 min-w-0 overflow-hidden border-l-0",
        )}
      >
        {showRightPanel && (
          <SourcesPanel
            sources={panelSources}
            webSources={panelWebSources}
            onClose={() => setShowRightPanel(false)}
          />
        )}
      </div>

      {/* Delete confirmation */}
      <ConfirmDialog
        open={deleteId !== null}
        title="Delete conversation?"
        description="This will permanently delete this conversation and all its messages."
        onConfirm={handleDelete}
        onCancel={() => setDeleteId(null)}
        destructive
      />
    </div>
  )
}

export default Chat
