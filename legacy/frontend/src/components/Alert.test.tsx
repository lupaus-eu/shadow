import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Alert from "./Alert";

describe("Alert", () => {
  it("renders the title, message and a close button named after the title", () => {
    const onDismiss = vi.fn();
    render(
      <Alert
        variant="danger"
        role="alert"
        title="Save error"
        message="Could not save."
        onDismiss={onDismiss}
      />
    );

    const alert = screen.getByRole("alert");
    expect(alert).toHaveClass("alert", "alert--danger", "alert--dismissible");
    expect(alert).toHaveTextContent("Save error");
    expect(alert).toHaveTextContent("Could not save.");

    fireEvent.click(screen.getByRole("button", { name: "Dismiss Save error notice" }));

    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("uses a generic close label without a title and accepts a custom label", () => {
    const { rerender } = render(<Alert variant="info" role="status" message="Done." />);
    expect(screen.getByRole("button", { name: "Dismiss notice" })).toBeInTheDocument();

    rerender(
      <Alert variant="info" role="status" message="Done." dismissLabel="Dismiss request notice" />
    );
    expect(screen.getByRole("button", { name: "Dismiss request notice" })).toBeInTheDocument();
  });

  it("hides itself without an owner and shows again for a new key", () => {
    const { rerender } = render(
      <Alert key="first" variant="danger" role="alert" message="First failure." />
    );

    fireEvent.click(screen.getByRole("button", { name: "Dismiss notice" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    rerender(<Alert key="first" variant="danger" role="alert" message="First failure." />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    rerender(<Alert key="second" variant="danger" role="alert" message="Second failure." />);
    expect(screen.getByRole("alert")).toHaveTextContent("Second failure.");
  });

  it("keeps a compact Retry button after hiding itself", () => {
    const onRetry = vi.fn();
    const { rerender } = render(
      <Alert
        key="first"
        variant="danger"
        role="alert"
        className="context-dropdown__alert"
        message="Load failed."
        onRetry={onRetry}
        retryLabel="Try again"
      />
    );

    fireEvent.click(within(screen.getByRole("alert")).getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Dismiss notice" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    const retry = screen.getByRole("button", { name: "Try again" });
    expect(retry).toHaveClass("btn--compact");
    expect(retry.parentElement).toHaveClass("alert-retry", "context-dropdown__alert");
    fireEvent.click(retry);
    expect(onRetry).toHaveBeenCalledTimes(2);

    rerender(
      <Alert
        key="first"
        variant="danger"
        role="alert"
        message="Load failed."
        onRetry={onRetry}
        retryLabel="Try again"
        retryDisabled
      />
    );
    expect(screen.getByRole("button", { name: "Try again" })).toBeDisabled();
  });

  it("leaves no Retry button when the owner clears the alert", () => {
    const onDismiss = vi.fn();
    render(<Alert variant="danger" role="alert" message="Load failed." onDismiss={onDismiss} />);

    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Dismiss notice" }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("uses a caller's own box classes instead of the alert box", () => {
    render(
      <Alert
        variant="danger"
        role="alert"
        boxClassName="summary-state summary-state--error"
        message="Could not load summary."
        onDismiss={() => undefined}
        dismissLabel="Dismiss summary error notice"
      />
    );

    const alert = screen.getByRole("alert");
    expect(alert).toHaveClass("summary-state", "summary-state--error", "alert--dismissible");
    expect(alert).not.toHaveClass("alert");
    expect(alert).not.toHaveClass("alert--danger");
    expect(screen.getByRole("button", { name: "Dismiss summary error notice" })).toHaveClass(
      "alert__dismiss"
    );
  });

  it("renders extra content and keeps the id and accessible name", () => {
    render(
      <Alert id="field-error" variant="danger" ariaLabel="Validation errors" title="Errors">
        <ul>
          <li>First error</li>
        </ul>
      </Alert>
    );

    const alert = screen.getByLabelText("Validation errors");
    expect(alert).toHaveAttribute("id", "field-error");
    expect(alert).toHaveTextContent("First error");
  });
});
