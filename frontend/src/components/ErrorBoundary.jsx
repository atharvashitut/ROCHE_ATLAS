import { Component } from 'react'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error) {
    // Keep diagnostics available to developers without exposing payload
    // details to users or allowing one widget to blank the application.
    console.error(`ATLAS ${this.props.label || 'component'} render failure`, error)
  }

  componentDidUpdate(previousProps) {
    if (previousProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false })
    }
  }

  render() {
    if (this.state.hasError) {
      return <section className="m-6 rounded-xl border border-rose-500/40 bg-rose-950/25 p-5 text-slate-100" role="alert">
        <h2 className="font-semibold">Failed to render component</h2>
        <p className="mt-1 text-sm text-slate-300">This view received an unexpected response. Switch tabs or refresh to try again; the rest of ATLAS remains available.</p>
      </section>
    }
    return this.props.children
  }
}
