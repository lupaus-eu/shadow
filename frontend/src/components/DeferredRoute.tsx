import { Component, type ReactNode } from "react";

export function RouteLoadingFallback(props: { message: string }) {
  return (
    <section className="route-loading-state" role="status" aria-live="polite" aria-busy="true">
      <p className="eyebrow">Schatten</p>
      <p className="route-loading-state__message">{props.message}</p>
    </section>
  );
}

type RouteErrorBoundaryProps = {
  children: ReactNode;
  title: string;
  onReload?: () => void;
  resetKey?: string;
};

type RouteErrorBoundaryState = {
  hasError: boolean;
};

export class RouteErrorBoundary extends Component<
  RouteErrorBoundaryProps,
  RouteErrorBoundaryState
> {
  state: RouteErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): RouteErrorBoundaryState {
    return { hasError: true };
  }

  componentDidUpdate(previousProps: RouteErrorBoundaryProps) {
    if (this.state.hasError && previousProps.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false });
    }
  }

  private reload = () => {
    if (this.props.onReload) {
      this.props.onReload();
      return;
    }

    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <section className="route-load-error" role="alert">
          <p className="eyebrow">Loading error</p>
          <h1 className="page-title">{this.props.title}</h1>
          <p className="muted">
            The requested page could not be loaded. Reload the application to try again.
          </p>
          <button className="btn btn--primary" type="button" onClick={this.reload}>
            Reload page
          </button>
        </section>
      );
    }

    return this.props.children;
  }
}
