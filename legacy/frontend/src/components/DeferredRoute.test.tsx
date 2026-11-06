import { lazy, Suspense, type ReactNode } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RouteErrorBoundary, RouteLoadingFallback } from "./DeferredRoute";

function deferredComponent() {
  let resolve!: (module: { default: () => ReactNode }) => void;
  const promise = new Promise<{ default: () => ReactNode }>((promiseResolve) => {
    resolve = promiseResolve;
  });

  return { promise, resolve };
}

describe("deferred route states", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("announces loading while keeping content outside the Suspense seam visible", async () => {
    const deferred = deferredComponent();
    const DeferredContent = lazy(() => deferred.promise);

    render(
      <>
        <header>Persistent workspace navigation</header>
        <Suspense fallback={<RouteLoadingFallback message="Loading workspace tab..." />}>
          <DeferredContent />
        </Suspense>
      </>
    );

    expect(screen.getByText("Persistent workspace navigation")).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent("Loading workspace tab...");

    deferred.resolve({ default: () => <p>Deferred content</p> });

    expect(await screen.findByText("Deferred content")).toBeVisible();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("shows a non-sensitive error and reload action for a rejected lazy import", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const reload = vi.fn();
    const RejectedContent = lazy(() => Promise.reject(new Error("private chunk failure details")));

    render(
      <RouteErrorBoundary title="Unable to load workspace tab" onReload={reload}>
        <Suspense fallback={<RouteLoadingFallback message="Loading workspace tab..." />}>
          <RejectedContent />
        </Suspense>
      </RouteErrorBoundary>
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load workspace tab");
    expect(screen.queryByText(/private chunk failure details/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Reload page" }));
    expect(reload).toHaveBeenCalledOnce();
  });
});
