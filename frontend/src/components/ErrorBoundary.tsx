import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * Catches render-time errors anywhere below it so a crash in one component shows
 * a recoverable fallback instead of unmounting the whole app to a blank screen.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled UI error:", error, info.componentStack);
  }

  private handleReload = () => {
    this.setState({ error: null });
    window.location.reload();
  };

  render() {
    const { error } = this.state;
    if (!error) {
      return this.props.children;
    }

    return (
      <div className="min-h-screen bg-background text-foreground antialiased">
        <div className="flex min-h-screen items-center justify-center px-6">
          <div className="app-startup-panel w-full max-w-[460px] rounded-[28px] px-8 py-8 text-center">
            <h1 className="text-[18px] font-semibold tracking-tight text-[hsl(var(--text-strong))]">
              Something went wrong
            </h1>
            <p className="mt-2 text-[13px] leading-6 text-muted-foreground">
              The interface hit an unexpected error. Your music files were not touched.
            </p>
            {error.message ? (
              <p className="mt-3 break-words rounded-xl bg-surface-subtle/70 px-3 py-2 text-left font-mono text-[11px] text-muted-foreground">
                {error.message}
              </p>
            ) : null}
            <button
              className="app-button-primary mt-5 rounded-2xl px-4 py-2 text-[13px]"
              type="button"
              onClick={this.handleReload}
            >
              Reload
            </button>
          </div>
        </div>
      </div>
    );
  }
}
