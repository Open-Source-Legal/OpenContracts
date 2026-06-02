/**
 * ErrorBoundary Component Tests
 *
 * Verifies the React error boundary behavior:
 * - Renders children when no error thrown
 * - Catches render errors and displays fallback UI
 * - Invokes optional onError callback with error + errorInfo
 * - Supports custom fallback render prop
 * - Reset path clears error state and re-renders children
 * - Logs errors to console (observability)
 *
 * Covers catch path in componentDidCatch (line 66 of ErrorBoundary.tsx).
 */

import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ErrorBoundary } from "../ErrorBoundary";

/**
 * Helper component that throws on render when `shouldThrow` prop is true.
 * Used to force the error boundary into its error state.
 */
const Thrower: React.FC<{ shouldThrow: boolean; message?: string }> = ({
  shouldThrow,
  message = "boom",
}) => {
  if (shouldThrow) {
    throw new Error(message);
  }
  return <div>child content</div>;
};

describe("ErrorBoundary", () => {
  // Silence React's console.error spam for caught render errors so
  // test output stays readable. Asserted on separately below.
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleErrorSpy = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it("renders children when no error is thrown", () => {
    render(
      <ErrorBoundary>
        <Thrower shouldThrow={false} />
      </ErrorBoundary>
    );

    expect(screen.getByText("child content")).toBeInTheDocument();
  });

  it("renders default fallback UI when a child throws", () => {
    render(
      <ErrorBoundary>
        <Thrower shouldThrow message="kaboom" />
      </ErrorBoundary>
    );

    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByText("kaboom")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /try again/i })
    ).toBeInTheDocument();
  });

  it("invokes onError callback with error and errorInfo", () => {
    const onError = vi.fn();

    render(
      <ErrorBoundary onError={onError}>
        <Thrower shouldThrow message="callback test" />
      </ErrorBoundary>
    );

    expect(onError).toHaveBeenCalledTimes(1);
    const [error, errorInfo] = onError.mock.calls[0];
    expect(error).toBeInstanceOf(Error);
    expect(error.message).toBe("callback test");
    // React's ErrorInfo carries a componentStack string
    expect(errorInfo).toHaveProperty("componentStack");
  });

  it("logs the caught error via console.error (observability)", () => {
    render(
      <ErrorBoundary>
        <Thrower shouldThrow message="log me" />
      </ErrorBoundary>
    );

    // componentDidCatch logs with the marker "ErrorBoundary caught an error:"
    const markerCall = consoleErrorSpy.mock.calls.find(
      (call: unknown[]) =>
        typeof call[0] === "string" &&
        (call[0] as string).includes("ErrorBoundary caught an error:")
    );
    expect(markerCall).toBeDefined();
  });

  it("renders a custom fallback when fallback prop is provided", () => {
    const fallback = (error: Error, resetError: () => void) => (
      <div>
        <span data-testid="custom-message">Custom: {error.message}</span>
        <button onClick={resetError}>Custom Reset</button>
      </div>
    );

    render(
      <ErrorBoundary fallback={fallback}>
        <Thrower shouldThrow message="custom fallback" />
      </ErrorBoundary>
    );

    expect(screen.getByTestId("custom-message")).toHaveTextContent(
      "Custom: custom fallback"
    );
    expect(
      screen.getByRole("button", { name: /custom reset/i })
    ).toBeInTheDocument();
  });

  it("recovers to children when reset is clicked and child no longer throws", () => {
    /**
     * Parent controls whether the child throws so we can simulate a
     * recoverable error: fault first render → user clicks reset → parent
     * fixes the condition → boundary re-renders children.
     */
    const Harness: React.FC = () => {
      const [shouldThrow, setShouldThrow] = React.useState(true);
      return (
        <div>
          <button data-testid="fix-error" onClick={() => setShouldThrow(false)}>
            fix
          </button>
          <ErrorBoundary>
            <Thrower shouldThrow={shouldThrow} message="recoverable" />
          </ErrorBoundary>
        </div>
      );
    };

    render(<Harness />);

    // Fallback visible initially
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();

    // Flip the parent state so the child will no longer throw
    fireEvent.click(screen.getByTestId("fix-error"));
    // Clicking "Try Again" resets boundary state → boundary re-renders children
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    expect(screen.getByText("child content")).toBeInTheDocument();
    expect(screen.queryByText("Something went wrong")).not.toBeInTheDocument();
  });

  it("re-displays fallback when child still throws after reset", () => {
    /**
     * If the underlying condition isn't fixed, clicking reset should
     * cause the child to throw again and the fallback should re-render.
     * This ensures reset doesn't permanently swallow the error state.
     */
    render(
      <ErrorBoundary>
        <Thrower shouldThrow message="persistent" />
      </ErrorBoundary>
    );

    expect(screen.getByText("persistent")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    // Still in error state because the child keeps throwing
    expect(screen.getByText("persistent")).toBeInTheDocument();
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
  });
});
