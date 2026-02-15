import { useState, useEffect, useCallback, useMemo } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { queryKeys } from "@/lib/queryKeys"
import { STALE_TIMES } from "@/lib/queryClient"
import { useDocumentTitle } from "@/hooks/useDocumentTitle"
import { toast } from "sonner"
import { cn } from "@/lib/utils"
import { getModels, getAgentTools, getAgent, createAgent, updateAgent, triggerAgent } from "@/lib/api"
import { PageHeader } from "@/components/PageHeader"
import { CronInput } from "@/components/agents/CronInput"
import { JSONEditor } from "@/components/agents/JSONEditor"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Checkbox } from "@/components/ui/checkbox"
import { Save, Play, X, Plus, Trash2, Copy } from "lucide-react"
import yaml from "js-yaml"

interface ToolDef {
  name: string
  description: string
  parameters?: Record<string, unknown>
}

interface TriggerForm {
  type: string
  topic: string
  payload_filter: string
  cron: string
  interval_seconds: string
  event_type: string
  debounce_seconds: string
}

const EVENT_TYPES = [
  "node_offline",
  "node_online",
  "node_unreachable",
  "transcription_complete",
  "obsidian_sync_complete",
  "sync_complete",
  "agent_run_complete",
  "knowledge_ingested",
  "system_error",
  "circuit_breaker_tripped",
]

const OUTPUT_CHANNELS = ["telegram", "mqtt", "dashboard", "log"]

const PROMPT_TEMPLATES: { label: string; text: string }[] = [
  {
    label: "Ham Radio Expert",
    text: "You are an expert amateur radio operator assistant for W0ABE. You have deep knowledge of HF propagation, antenna design, contesting, and FCC regulations. Provide concise, actionable advice.",
  },
  {
    label: "System Monitor",
    text: "You are a system monitoring assistant. Analyze system metrics, node health, and service status. Alert on anomalies and suggest remediation steps. Be concise and technical.",
  },
  {
    label: "Knowledge Assistant",
    text: "You are a knowledge base assistant. Search through documents, notes, and transcriptions to answer questions. Always cite your sources and provide relevant context.",
  },
  {
    label: "Web Researcher",
    text: "You are a web research assistant. Search the web for current information and summarize findings. Provide links and cite sources. Focus on accuracy over speed.",
  },
]

const defaultTrigger = (): TriggerForm => ({
  type: "api",
  topic: "",
  payload_filter: "{}",
  cron: "",
  interval_seconds: "",
  event_type: "",
  debounce_seconds: "30",
})

function slugify(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
}

function AgentBuilder() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const editName = searchParams.get("edit")
  const isEdit = !!editName

  useDocumentTitle("Agent Builder")

  // Form state
  const [displayName, setDisplayName] = useState("")
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [model, setModel] = useState("")
  const [temperature, setTemperature] = useState("")
  const [enabled, setEnabled] = useState(true)
  const [systemPrompt, setSystemPrompt] = useState("")
  const [selectedTools, setSelectedTools] = useState<Set<string>>(new Set())
  const [toolConfigs, setToolConfigs] = useState<Record<string, string>>({})
  const [triggers, setTriggers] = useState<TriggerForm[]>([defaultTrigger()])
  const [outputChannels, setOutputChannels] = useState<Set<string>>(new Set(["log"]))
  const [maxConcurrent, setMaxConcurrent] = useState("1")
  const [timeoutSeconds, setTimeoutSeconds] = useState("120")
  const [configJson, setConfigJson] = useState("{}")

  const [saving, setSaving] = useState(false)
  const [autoSlug, setAutoSlug] = useState(!isEdit)
  const [activeTab, setActiveTab] = useState("basic")

  // Reference data via useQuery
  const { data: models = [] } = useQuery({
    queryKey: queryKeys.chat.models(),
    queryFn: () => getModels().then((r) => (r.data.models || []) as Array<{ name: string; size?: number }>),
    staleTime: STALE_TIMES.models,
  })

  const { data: availableTools = [] } = useQuery({
    queryKey: queryKeys.agents.tools(),
    queryFn: () => getAgentTools().then((r) => (r.data || []) as ToolDef[]),
    staleTime: STALE_TIMES.agents,
  })

  // Set default model when models load
  useEffect(() => {
    if (!model && models.length > 0) {
      setModel(models[0].name)
    }
  }, [models, model])

  // Load existing agent for edit mode
  useEffect(() => {
    if (!editName) return
    getAgent(editName)
      .then(({ data }) => {
        setDisplayName(data.display_name || "")
        setName(data.name || "")
        setDescription(data.description || "")
        setModel(data.model || "")
        setTemperature(data.temperature != null ? String(data.temperature) : "")
        setEnabled(data.enabled ?? true)
        setSystemPrompt(data.system_prompt || "")
        setSelectedTools(new Set((data.tools || []).map((t: { name: string }) => t.name)))
        const cfgs: Record<string, string> = {}
        for (const t of data.tools || []) {
          if (t.config && Object.keys(t.config).length > 0) {
            cfgs[t.name] = JSON.stringify(t.config, null, 2)
          }
        }
        setToolConfigs(cfgs)
        setTriggers(
          (data.triggers || []).length > 0
            ? (data.triggers || []).map(
                (t: {
                  type: string
                  topic?: string
                  payload_filter?: Record<string, unknown>
                  cron?: string
                  interval_seconds?: number
                  event_type?: string
                  config?: Record<string, unknown>
                }) => ({
                  type: t.type || "api",
                  topic: t.topic || "",
                  payload_filter: t.payload_filter
                    ? JSON.stringify(t.payload_filter, null, 2)
                    : "{}",
                  cron: t.cron || "",
                  interval_seconds: t.interval_seconds ? String(t.interval_seconds) : "",
                  event_type: t.event_type || "",
                  debounce_seconds: t.config?.debounce_seconds
                    ? String(t.config.debounce_seconds)
                    : "30",
                }),
              )
            : [defaultTrigger()],
        )
        setOutputChannels(new Set(data.output_channels || []))
        setMaxConcurrent(String(data.max_concurrent ?? 1))
        setTimeoutSeconds(String(data.timeout_seconds ?? 120))
        setConfigJson(
          data.config && Object.keys(data.config).length > 0
            ? JSON.stringify(data.config, null, 2)
            : "{}",
        )
        setAutoSlug(false)
      })
      .catch(() => {
        toast.error(`Agent "${editName}" not found`)
        navigate("/agents")
      })
  }, [editName, navigate])

  // Auto-generate slug from display name
  useEffect(() => {
    if (autoSlug && displayName) {
      setName(slugify(displayName))
    }
  }, [displayName, autoSlug])

  const nameValid = /^[a-z0-9][a-z0-9-]*[a-z0-9]$/.test(name) || (name.length === 1 && /^[a-z0-9]$/.test(name))

  // Build request body
  const buildBody = useCallback(() => {
    const tools = [...selectedTools].map((toolName) => {
      const cfg = toolConfigs[toolName]
      let config = {}
      if (cfg) {
        try {
          config = JSON.parse(cfg)
        } catch {
          /* empty */
        }
      }
      return { name: toolName, config }
    })

    const triggerList = triggers
      .filter((t) => t.type)
      .map((t) => {
        const trigger: Record<string, unknown> = { type: t.type }
        if (t.type === "mqtt") {
          trigger.topic = t.topic
          try {
            const pf = JSON.parse(t.payload_filter)
            if (Object.keys(pf).length > 0) trigger.payload_filter = pf
          } catch {
            /* empty */
          }
          if (t.debounce_seconds) {
            trigger.config = { debounce_seconds: Number(t.debounce_seconds) }
          }
        }
        if (t.type === "schedule") {
          if (t.cron) trigger.cron = t.cron
          if (t.interval_seconds) trigger.interval_seconds = Number(t.interval_seconds)
        }
        if (t.type === "event") {
          trigger.event_type = t.event_type
        }
        return trigger
      })

    let config = {}
    try {
      config = JSON.parse(configJson)
    } catch {
      /* empty */
    }

    const body: Record<string, unknown> = {
      name,
      display_name: displayName,
      description,
      model,
      system_prompt: systemPrompt,
      tools,
      triggers: triggerList,
      output_channels: [...outputChannels],
      enabled,
      max_concurrent: Number(maxConcurrent) || 1,
      timeout_seconds: Number(timeoutSeconds) || 120,
      config,
    }
    if (temperature) body.temperature = Number(temperature)
    return body
  }, [
    name, displayName, description, model, temperature, systemPrompt,
    selectedTools, toolConfigs, triggers, outputChannels, enabled,
    maxConcurrent, timeoutSeconds, configJson,
  ])

  // YAML preview
  const previewYaml = useMemo(() => {
    try {
      const body = buildBody()
      return yaml.dump(body, { lineWidth: 60, noRefs: true })
    } catch {
      return "# Error generating preview"
    }
  }, [buildBody])

  const handleSave = async (runAfter = false) => {
    if (!name || !nameValid) {
      toast.error("Invalid agent name (lowercase alphanumeric + hyphens)")
      setActiveTab("basic")
      return
    }
    setSaving(true)
    try {
      const body = buildBody()
      if (isEdit) {
        await updateAgent(editName!, body)
        toast.success("Agent updated")
      } else {
        await createAgent(body)
        toast.success("Agent created")
      }
      if (runAfter) {
        await triggerAgent(name)
        toast.success("Agent triggered")
      }
      navigate("/agents")
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? String((err as { response?: { data?: { detail?: string } } }).response?.data?.detail || "Save failed")
          : "Save failed"
      toast.error(msg)
    } finally {
      setSaving(false)
    }
  }

  const addTrigger = () => setTriggers((prev) => [...prev, defaultTrigger()])
  const removeTrigger = (i: number) =>
    setTriggers((prev) => prev.filter((_, idx) => idx !== i))
  const updateTrigger = (i: number, field: keyof TriggerForm, value: string) =>
    setTriggers((prev) => prev.map((t, idx) => (idx === i ? { ...t, [field]: value } : t)))

  const toggleTool = (toolName: string) => {
    setSelectedTools((prev) => {
      const next = new Set(prev)
      if (next.has(toolName)) next.delete(toolName)
      else next.add(toolName)
      return next
    })
  }

  const toggleChannel = (ch: string) => {
    setOutputChannels((prev) => {
      const next = new Set(prev)
      if (next.has(ch)) next.delete(ch)
      else next.add(ch)
      return next
    })
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={isEdit ? `Edit: ${editName}` : "Create Agent"}
        description={isEdit ? "Modify agent definition" : "Define a new autonomous agent"}
        actions={
          <Button variant="outline" size="sm" onClick={() => navigate("/agents")}>
            <X className="mr-1 h-4 w-4" /> Cancel
          </Button>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        {/* Main form */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="w-full grid grid-cols-5">
            <TabsTrigger value="basic">Basic</TabsTrigger>
            <TabsTrigger value="prompt">Prompt</TabsTrigger>
            <TabsTrigger value="tools">Tools</TabsTrigger>
            <TabsTrigger value="triggers">Triggers</TabsTrigger>
            <TabsTrigger value="output">Output</TabsTrigger>
          </TabsList>

          {/* Tab 1: Basic Info */}
          <TabsContent value="basic" className="space-y-4">
            <Card>
              <CardContent className="space-y-4 pt-6">
                <div className="space-y-2">
                  <Label>Display Name</Label>
                  <Input
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    placeholder="Daily Briefing"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Name / Slug</Label>
                  <Input
                    value={name}
                    onChange={(e) => {
                      setName(e.target.value)
                      setAutoSlug(false)
                    }}
                    placeholder="daily-briefing"
                    disabled={isEdit}
                    className={cn("font-mono", !nameValid && name.length > 0 && "border-destructive")}
                  />
                  {!nameValid && name.length > 0 && (
                    <p className="text-xs text-destructive">
                      Must be lowercase alphanumeric with hyphens (e.g. "my-agent-1")
                    </p>
                  )}
                </div>
                <div className="space-y-2">
                  <Label>Description</Label>
                  <Textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="What does this agent do?"
                    rows={3}
                  />
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label>Model</Label>
                    <Select value={model} onValueChange={setModel}>
                      <SelectTrigger>
                        <SelectValue placeholder="Select model" />
                      </SelectTrigger>
                      <SelectContent>
                        {models.map((m) => (
                          <SelectItem key={m.name} value={m.name}>
                            {m.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Temperature</Label>
                    <Input
                      type="number"
                      step={0.1}
                      min={0}
                      max={2}
                      value={temperature}
                      onChange={(e) => setTemperature(e.target.value)}
                      placeholder="Default"
                    />
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Switch checked={enabled} onCheckedChange={setEnabled} />
                  <Label>Enabled</Label>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Tab 2: System Prompt */}
          <TabsContent value="prompt" className="space-y-4">
            <Card>
              <CardContent className="space-y-4 pt-6">
                <div className="flex flex-wrap gap-1">
                  {PROMPT_TEMPLATES.map((t) => (
                    <Button
                      key={t.label}
                      variant="outline"
                      size="sm"
                      className="h-7 text-xs"
                      onClick={() => setSystemPrompt(t.text)}
                    >
                      {t.label}
                    </Button>
                  ))}
                </div>
                <Textarea
                  value={systemPrompt}
                  onChange={(e) => setSystemPrompt(e.target.value)}
                  placeholder="You are a helpful assistant..."
                  rows={16}
                  className="font-mono text-sm"
                />
                <p className="text-xs text-muted-foreground text-right">
                  {systemPrompt.length} characters
                </p>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Tab 3: Tools */}
          <TabsContent value="tools" className="space-y-4">
            <Card>
              <CardContent className="space-y-3 pt-6">
                {availableTools.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Loading tools...</p>
                ) : (
                  availableTools.map((tool) => (
                    <div key={tool.name} className="space-y-2">
                      <div className="flex items-start gap-3">
                        <Checkbox
                          id={`tool-${tool.name}`}
                          checked={selectedTools.has(tool.name)}
                          onCheckedChange={() => toggleTool(tool.name)}
                          className="mt-0.5"
                        />
                        <div className="min-w-0">
                          <label
                            htmlFor={`tool-${tool.name}`}
                            className="text-sm font-medium cursor-pointer"
                          >
                            {tool.name}
                          </label>
                          <p className="text-xs text-muted-foreground">{tool.description}</p>
                        </div>
                      </div>
                      {selectedTools.has(tool.name) && (
                        <div className="ml-7">
                          <JSONEditor
                            value={toolConfigs[tool.name] || "{}"}
                            onChange={(v) =>
                              setToolConfigs((prev) => ({ ...prev, [tool.name]: v }))
                            }
                            label="Tool Config"
                            rows={3}
                          />
                        </div>
                      )}
                      <Separator />
                    </div>
                  ))
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Tab 4: Triggers */}
          <TabsContent value="triggers" className="space-y-4">
            <Card>
              <CardContent className="space-y-4 pt-6">
                {triggers.map((trigger, i) => (
                  <div key={i} className="space-y-3 rounded-md border p-3">
                    <div className="flex items-center justify-between">
                      <Select
                        value={trigger.type}
                        onValueChange={(v) => updateTrigger(i, "type", v)}
                      >
                        <SelectTrigger className="w-[160px]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="api">API</SelectItem>
                          <SelectItem value="mqtt">MQTT</SelectItem>
                          <SelectItem value="schedule">Schedule</SelectItem>
                          <SelectItem value="event">Event</SelectItem>
                        </SelectContent>
                      </Select>
                      {triggers.length > 1 && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={() => removeTrigger(i)}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </div>

                    {trigger.type === "api" && (
                      <p className="text-xs text-muted-foreground">
                        Triggered via POST /agents/{name || "<name>"}/run
                      </p>
                    )}

                    {trigger.type === "mqtt" && (
                      <div className="space-y-2">
                        <div className="space-y-1">
                          <Label className="text-xs">Topic</Label>
                          <Input
                            value={trigger.topic}
                            onChange={(e) => updateTrigger(i, "topic", e.target.value)}
                            placeholder="homeassistant/+/+/state"
                            className="font-mono text-sm"
                          />
                        </div>
                        <JSONEditor
                          value={trigger.payload_filter}
                          onChange={(v) => updateTrigger(i, "payload_filter", v)}
                          label="Payload Filter"
                          rows={3}
                        />
                        <div className="space-y-1">
                          <Label className="text-xs">Debounce (seconds)</Label>
                          <Input
                            type="number"
                            value={trigger.debounce_seconds}
                            onChange={(e) => updateTrigger(i, "debounce_seconds", e.target.value)}
                            className="w-24"
                          />
                        </div>
                      </div>
                    )}

                    {trigger.type === "schedule" && (
                      <div className="space-y-3">
                        <div className="space-y-1">
                          <Label className="text-xs">Cron Expression</Label>
                          <CronInput
                            value={trigger.cron}
                            onChange={(v) => updateTrigger(i, "cron", v)}
                          />
                        </div>
                        <p className="text-xs text-muted-foreground text-center">&mdash; or &mdash;</p>
                        <div className="space-y-1">
                          <Label className="text-xs">Interval (seconds)</Label>
                          <Input
                            type="number"
                            value={trigger.interval_seconds}
                            onChange={(e) => updateTrigger(i, "interval_seconds", e.target.value)}
                            placeholder="3600"
                            className="w-32"
                          />
                        </div>
                      </div>
                    )}

                    {trigger.type === "event" && (
                      <div className="space-y-1">
                        <Label className="text-xs">Event Type</Label>
                        <Select
                          value={trigger.event_type}
                          onValueChange={(v) => updateTrigger(i, "event_type", v)}
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Select event type" />
                          </SelectTrigger>
                          <SelectContent>
                            {EVENT_TYPES.map((e) => (
                              <SelectItem key={e} value={e}>
                                {e}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    )}
                  </div>
                ))}
                <Button variant="outline" size="sm" onClick={addTrigger}>
                  <Plus className="mr-1 h-3 w-3" /> Add Trigger
                </Button>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Tab 5: Output & Advanced */}
          <TabsContent value="output" className="space-y-4">
            <Card>
              <CardContent className="space-y-4 pt-6">
                <div className="space-y-2">
                  <Label>Output Channels</Label>
                  <div className="flex flex-wrap gap-3">
                    {OUTPUT_CHANNELS.map((ch) => (
                      <div key={ch} className="flex items-center gap-2">
                        <Checkbox
                          id={`ch-${ch}`}
                          checked={outputChannels.has(ch)}
                          onCheckedChange={() => toggleChannel(ch)}
                        />
                        <label htmlFor={`ch-${ch}`} className="text-sm capitalize cursor-pointer">
                          {ch}
                        </label>
                      </div>
                    ))}
                  </div>
                </div>
                <Separator />
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label>Max Concurrent</Label>
                    <Input
                      type="number"
                      min={1}
                      max={10}
                      value={maxConcurrent}
                      onChange={(e) => setMaxConcurrent(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Timeout (seconds)</Label>
                    <Input
                      type="number"
                      min={5}
                      max={3600}
                      value={timeoutSeconds}
                      onChange={(e) => setTimeoutSeconds(e.target.value)}
                    />
                  </div>
                </div>
                <Separator />
                <JSONEditor
                  value={configJson}
                  onChange={setConfigJson}
                  label="Agent Config JSON"
                  rows={6}
                />
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>

        {/* YAML preview (right column) */}
        <div className="hidden lg:block">
          <Card className="sticky top-4">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">YAML Preview</CardTitle>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  onClick={() => {
                    navigator.clipboard.writeText(previewYaml)
                    toast.success("Copied to clipboard")
                  }}
                >
                  <Copy className="h-3.5 w-3.5" />
                </Button>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <ScrollArea className="h-[calc(100vh-16rem)]">
                <pre className="px-4 pb-4 text-xs font-mono text-muted-foreground whitespace-pre-wrap">
                  {previewYaml}
                </pre>
              </ScrollArea>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Action bar */}
      <div className="flex items-center justify-end gap-2 border-t pt-4">
        <Button variant="outline" onClick={() => navigate("/agents")}>
          Cancel
        </Button>
        <Button onClick={() => handleSave(false)} disabled={saving}>
          <Save className="mr-2 h-4 w-4" />
          {saving ? "Saving..." : "Save"}
        </Button>
        <Button onClick={() => handleSave(true)} disabled={saving}>
          <Play className="mr-2 h-4 w-4" />
          {saving ? "Saving..." : "Save & Run"}
        </Button>
      </div>
    </div>
  )
}

export default AgentBuilder
