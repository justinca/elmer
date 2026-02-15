import { useNavigate } from "react-router-dom"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/EmptyState"
import { Button } from "@/components/ui/button"
import { FileQuestion } from "lucide-react"
import { useDocumentTitle } from "@/hooks/useDocumentTitle"

export default function NotFound() {
  useDocumentTitle("Page Not Found")
  const navigate = useNavigate()

  return (
    <div className="space-y-6">
      <PageHeader title="Page Not Found" description="The page you're looking for doesn't exist" />
      <EmptyState
        icon={FileQuestion}
        title="404"
        description="This page could not be found. Check the URL or navigate back to the dashboard."
      />
      <div className="flex justify-center">
        <Button onClick={() => navigate("/")}>Back to Dashboard</Button>
      </div>
    </div>
  )
}
