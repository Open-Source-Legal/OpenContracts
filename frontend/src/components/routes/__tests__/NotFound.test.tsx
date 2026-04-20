import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { NotFound } from "../NotFound";

/**
 * Tests for NotFound route component.
 *
 * NotFound is the fallback rendered by App.tsx when no other route matches.
 * It exposes a "Go to Corpuses" button that should navigate the user back
 * to /corpuses.
 */
describe("NotFound", () => {
  const LocationReporter: React.FC = () => {
    const location = useLocation();
    return <div data-testid="location">{location.pathname}</div>;
  };

  const renderNotFound = (initialPath = "/some/bogus/route") =>
    render(
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="*" element={<NotFound />} />
          <Route path="/corpuses" element={<LocationReporter />} />
        </Routes>
      </MemoryRouter>
    );

  it("renders the 404 heading and description", () => {
    renderNotFound();

    expect(
      screen.getByRole("heading", { name: /404 .*Not Found/i })
    ).toBeInTheDocument();
    expect(
      screen.getByText(/The page you requested does not exist/i)
    ).toBeInTheDocument();
  });

  it("renders a 'Go to Corpuses' button that routes to /corpuses", async () => {
    renderNotFound();

    const btn = screen.getByRole("button", { name: /Go to Corpuses/i });
    await userEvent.click(btn);

    const locationNode = await screen.findByTestId("location");
    expect(locationNode.textContent).toBe("/corpuses");
  });
});
