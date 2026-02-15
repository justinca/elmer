import {
  Activity,
  AudioLines,
  Bot,
  BookOpen,
  Radio,
  LayoutDashboard,
  MessageSquare,
  FileText,
  Search,
  StickyNote,
  Antenna,
  Globe,
  Trophy,
  BarChart3,
  Wrench,
  PlayCircle,
  Cpu,
  Server,
  type LucideIcon,
} from "lucide-react"

export interface NavItem {
  label: string
  path: string
  icon: LucideIcon
}

export interface NavGroup {
  label: string
  items: NavItem[]
}

export const navigation: NavGroup[] = [
  {
    label: "System",
    items: [
      { label: "Status", path: "/", icon: LayoutDashboard },
      { label: "Events", path: "/events", icon: Activity },
      { label: "Services", path: "/services", icon: Server },
    ],
  },
  {
    label: "Knowledge",
    items: [
      { label: "Documents", path: "/documents", icon: FileText },
      { label: "Notes", path: "/notes", icon: StickyNote },
      { label: "Transcriptions", path: "/transcriptions", icon: AudioLines },
      { label: "Search", path: "/search", icon: Search },
      { label: "Chat", path: "/chat", icon: MessageSquare },
    ],
  },
  {
    label: "Agents",
    items: [
      { label: "Agents", path: "/agents", icon: Bot },
      { label: "Builder", path: "/agents/builder", icon: Wrench },
      { label: "Runs", path: "/agents/runs", icon: PlayCircle },
      { label: "Orchestrator", path: "/agents/orchestrator", icon: Cpu },
    ],
  },
  {
    label: "Radio",
    items: [
      { label: "Propagation", path: "/propagation", icon: Antenna },
      { label: "DX Spots", path: "/dx-spots", icon: Globe },
      { label: "Log", path: "/log", icon: BookOpen },
      { label: "Contests", path: "/contests", icon: Trophy },
      { label: "POTA", path: "/pota", icon: BarChart3 },
      { label: "Band Map", path: "/band-map", icon: Radio },
    ],
  },
]
