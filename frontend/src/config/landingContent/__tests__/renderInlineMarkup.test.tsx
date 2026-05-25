import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import React from "react";

import { renderInlineMarkup } from "../renderInlineMarkup";

/**
 * Helper to mount the array of nodes returned by renderInlineMarkup so we
 * can assert against the rendered DOM rather than React internals.
 */
const renderMarkup = (input: string) => {
  return render(<div data-testid="root">{renderInlineMarkup(input)}</div>);
};

describe("renderInlineMarkup", () => {
  it("returns an empty array for an empty string (no nodes to render)", () => {
    expect(renderInlineMarkup("")).toEqual([]);
  });

  it("renders plain text as a single fragment with no <em>", () => {
    const { container, getByTestId } = renderMarkup("just plain words");
    expect(getByTestId("root").textContent).toBe("just plain words");
    expect(container.querySelector("em")).toBeNull();
  });

  it("wraps a single *segment* in an italic <em> with serif font", () => {
    const { container, getByTestId } = renderMarkup("*cite* is the layer");
    const em = container.querySelector("em");
    expect(em).not.toBeNull();
    expect(em?.textContent).toBe("cite");
    expect(em).toHaveStyle({ fontStyle: "italic", fontWeight: "400" });
    // Trailing plain segment is preserved verbatim, sans asterisks.
    expect(getByTestId("root").textContent).toBe("cite is the layer");
  });

  it("renders multiple italic spans interleaved with plain text", () => {
    const { container, getByTestId } = renderMarkup(
      "*cite* sits under *OpenStreetMap*."
    );
    const ems = container.querySelectorAll("em");
    expect(ems).toHaveLength(2);
    expect(ems[0].textContent).toBe("cite");
    expect(ems[1].textContent).toBe("OpenStreetMap");
    expect(getByTestId("root").textContent).toBe(
      "cite sits under OpenStreetMap."
    );
  });
});
