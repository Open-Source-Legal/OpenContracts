/**
 * Unit-level coverage for ``CreateUrlAnnotationModal``.
 *
 * The Playwright component tests in ``frontend/tests/`` cover the modal
 * end-to-end, but unit coverage drives the modal-body interaction
 * handlers (``onMouseDown`` stopPropagation, error-clearing on input)
 * which Playwright's snapshot tests don't reliably wire into the
 * Istanbul lcov bundle picked up by codecov's ``frontend-unit`` flag.
 */
import React from "react";
import { render, fireEvent, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

import { CreateUrlAnnotationModal } from "../CreateUrlAnnotationModal";

describe("CreateUrlAnnotationModal", () => {
  it("stopPropagation on body mousedown does not bubble to wrapping handler", () => {
    // The modal body wraps its children in a div that swallows mousedown
    // so a click inside the modal cannot start a selection-drag on the
    // underlying SelectionLayer / TxtAnnotator.
    const parentHandler = vi.fn();
    render(
      <div onMouseDown={parentHandler} data-testid="outer">
        <CreateUrlAnnotationModal
          visible
          selectedText=""
          onConfirm={vi.fn()}
          onCancel={vi.fn()}
        />
      </div>
    );
    const input = screen.getByPlaceholderText(/https:\/\//);
    fireEvent.mouseDown(input);
    // The body wrapper's stopPropagation must prevent the bubble.
    expect(parentHandler).not.toHaveBeenCalled();
  });

  it("clears an existing error as soon as the user edits the input", () => {
    // The change handler is ``setUrl + if (error) setError(null)``. The
    // ``if (error)`` partial branch (covered when error is non-null) is
    // exercised by first triggering a validation failure, then typing.
    const onConfirm = vi.fn();
    render(
      <CreateUrlAnnotationModal
        visible
        selectedText=""
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />
    );

    const input = screen.getByPlaceholderText(/https:\/\//) as HTMLInputElement;

    // 1. Type an unsafe URL and submit so ``setError`` fires.
    fireEvent.change(input, { target: { value: "javascript:alert(1)" } });
    const createBtn = screen.getByRole("button", { name: /create link/i });
    fireEvent.click(createBtn);
    // The component renders an inline error message when validation fails.
    expect(screen.getByText(/must start with/i)).toBeInTheDocument();

    // 2. Edit the input; the partial-branch (error truthy → clear) must
    //    fire and the error message must disappear from the DOM.
    fireEvent.change(input, { target: { value: "https://safe.example.com" } });
    expect(screen.queryByText(/must start with/i)).not.toBeInTheDocument();
  });

  it("trims leading/trailing whitespace before passing the URL upstream", () => {
    // Mirror of the model layer's whitespace-stripping contract — the
    // modal must hand the parent component a canonical URL string.
    const onConfirm = vi.fn();
    render(
      <CreateUrlAnnotationModal
        visible
        selectedText=""
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />
    );
    const input = screen.getByPlaceholderText(/https:\/\//) as HTMLInputElement;
    fireEvent.change(input, {
      target: { value: "   https://example.com/with-spaces   " },
    });
    fireEvent.click(screen.getByRole("button", { name: /create link/i }));
    expect(onConfirm).toHaveBeenCalledWith("https://example.com/with-spaces");
  });
});
