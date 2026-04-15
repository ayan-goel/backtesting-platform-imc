"use client";

import { Component, type ReactNode } from "react";

interface State {
  error: Error | null;
}

/**
 * Catch render-time errors from any chart or panel inside the replay view
 * so a recharts crash doesn't white-screen the whole route. Async fetch
 * errors are still handled via the existing try/catch in replay-view.
 */
export class ReplayErrorBoundary extends Component<
  { children: ReactNode },
  State
> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: unknown): void {
    // Surface in the browser console for debugging.
    console.error("ReplayErrorBoundary caught", error, info);
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="rounded-card border border-sell/40 bg-sell/5 p-4 text-sm text-sell">
          <div className="font-semibold">replay view crashed</div>
          <div className="mt-1 font-mono text-xs opacity-80">
            {this.state.error.message}
          </div>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-3 rounded border border-sell/60 bg-sell/10 px-3 py-1 text-xs font-semibold hover:bg-sell/20"
          >
            reload page
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
