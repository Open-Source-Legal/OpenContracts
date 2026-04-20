import { render, screen } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing";
import { describe, it, expect, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { GlobalDiscussionsRoute } from "../GlobalDiscussionsRoute";

vi.mock("../../../views/GlobalDiscussions", () => ({
  GlobalDiscussions: () => <div>GlobalDiscussions Component</div>,
}));

vi.mock("../../seo/MetaTags", () => ({
  MetaTags: () => null,
}));

vi.mock("../../widgets/ErrorBoundary", () => ({
  ErrorBoundary: ({ children }: any) => <div>{children}</div>,
}));

/**
 * Tests for GlobalDiscussionsRoute.
 *
 * Thin wrapper that composes ErrorBoundary + MetaTags + GlobalDiscussions.
 * The test locks the render contract so accidental removals show up.
 */
describe("GlobalDiscussionsRoute", () => {
  it("renders the GlobalDiscussions view", () => {
    render(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter>
          <GlobalDiscussionsRoute />
        </MemoryRouter>
      </MockedProvider>
    );

    expect(screen.getByText("GlobalDiscussions Component")).toBeInTheDocument();
  });
});
