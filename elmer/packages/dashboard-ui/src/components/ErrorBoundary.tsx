import { Component, type ReactNode } from "react"

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-screen items-center justify-center bg-background p-8">
          <div className="max-w-lg space-y-4 text-center">
            <h1 className="text-2xl font-bold text-destructive">Something went wrong</h1>
            <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 text-left text-sm text-muted-foreground">
              {this.state.error?.message}
              {"\n\n"}
              {this.state.error?.stack}
            </pre>
            <button
              onClick={() => window.location.reload()}
              className="rounded-md bg-primary px-4 py-2 text-primary-foreground"
            >
              Reload
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
