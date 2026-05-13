import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CardLayout } from "../CardLayout";

const getCardContainer = (container: HTMLElement): HTMLElement => {
  const cardContainer = container.querySelector(".CardLayoutContainer");
  expect(cardContainer).not.toBeNull();
  return cardContainer as HTMLElement;
};

describe("CardLayout", () => {
  it("does not reserve search-bar spacing for an empty fragment", () => {
    const { container } = render(
      <CardLayout SearchBar={<></>}>
        <div data-testid="content">content</div>
      </CardLayout>
    );

    const cardContainer = getCardContainer(container);

    expect(cardContainer.children).toHaveLength(1);
    expect(cardContainer.firstElementChild).toHaveAttribute(
      "id",
      "ScrollableSegment"
    );
  });

  it("wraps a real search bar above the scrollable content", () => {
    const { container } = render(
      <CardLayout SearchBar={<div data-testid="search-bar">search</div>}>
        <div data-testid="content">content</div>
      </CardLayout>
    );

    const cardContainer = getCardContainer(container);

    expect(cardContainer.children).toHaveLength(2);
    expect(cardContainer.firstElementChild).toContainElement(
      screen.getByTestId("search-bar")
    );
    expect(cardContainer.lastElementChild).toHaveAttribute(
      "id",
      "ScrollableSegment"
    );
  });
});
