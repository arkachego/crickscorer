import { Component, type ErrorInfo, type ReactNode } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

type Props = {
  children: ReactNode;
  title?: string;
};

type State = {
  hasError: boolean;
};

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("UI error boundary", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <Alert tone="error" title={this.props.title ?? "Something went wrong"}>
          <p>
            The scoreboard failed to render. Refresh to reload authoritative
            match state.
          </p>
          <Button
            className="mt-3"
            type="button"
            variant="secondary"
            onClick={() => {
              this.setState({ hasError: false });
              window.location.reload();
            }}
          >
            Refresh
          </Button>
        </Alert>
      );
    }
    return this.props.children;
  }
}
