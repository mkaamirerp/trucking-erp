import { Component, ReactNode } from "react";

type Props = { children: ReactNode };
type State = { hasError: boolean; error: Error | null };

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info.componentStack);
  }

  render() {
    if (this.state.hasError && this.state.error) {
      return (
        <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-6">
          <div className="max-w-lg w-full rounded-xl border border-rose-500/50 bg-slate-900/80 p-6">
            <h1 className="text-lg font-semibold text-rose-300">Something went wrong</h1>
            <p className="mt-2 text-sm text-slate-300 font-mono break-all">
              {this.state.error.message}
            </p>
            <pre className="mt-3 text-xs text-slate-500 overflow-auto max-h-40">
              {this.state.error.stack}
            </pre>
            <button
              type="button"
              className="mt-4 px-4 py-2 rounded-lg bg-slate-700 text-slate-200 hover:bg-slate-600 text-sm"
              onClick={() => this.setState({ hasError: false, error: null })}
            >
              Dismiss
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
