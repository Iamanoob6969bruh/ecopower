import React from "react";

interface State {
  hasError: boolean;
  message?: string;
}

/**
 * Top-level error boundary so a render-time throw in any component (e.g. an
 * unexpected null shape or NaN math) shows a recoverable message instead of a
 * blank white screen.
 */
export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, State> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error?.message };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("Unhandled UI error:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex flex-col items-center justify-center gap-3 bg-background text-foreground p-8 text-center">
          <h1 className="font-serif text-2xl">Something went wrong</h1>
          <p className="text-sm text-muted-foreground max-w-md">
            The dashboard hit an unexpected error while rendering. Reloading usually fixes it.
          </p>
          {this.state.message && (
            <code className="text-[11px] text-muted-foreground/70 break-all max-w-md">{this.state.message}</code>
          )}
          <button
            onClick={() => window.location.reload()}
            className="mt-2 px-4 py-2 border border-border rounded font-mono text-xs uppercase tracking-widest hover:bg-accent/10"
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
