import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/EmptyState"
import { Construction } from "lucide-react"
import { useLocation } from "react-router-dom"

export default function Placeholder() {
  const location = useLocation()
  const name = location.pathname.slice(1).replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) || "Page"

  return (
    <div className="space-y-6">
      <PageHeader title={name} />
      <EmptyState
        icon={Construction}
        title="Coming Soon"
        description={`The ${name} page is under development.`}
      />
    </div>
  )
}
