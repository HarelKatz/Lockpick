import { Component, ErrorInfo, ReactNode } from 'react'

interface Props { children: ReactNode; label?: string }
interface State { hasError: boolean; error: Error | null }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[ErrorBoundary:${this.props.label ?? 'unknown'}] crash:`, error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 16, color: 'var(--danger)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>
          <strong>Render error in {this.props.label}</strong><br />
          {this.state.error?.message}<br />
          <button onClick={() => this.setState({ hasError: false, error: null })} style={{ marginTop: 8, cursor: 'pointer' }}>
            Retry
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
