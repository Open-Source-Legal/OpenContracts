import React from "react";
import { render, screen } from "@testing-library/react";
import { Badge } from "../Badge";

describe("Badge Component", () => {
  const mockBadge = {
    id: "1",
    name: "Test Badge",
    description: "A test badge description",
    icon: "Trophy",
    color: "#FFD700",
    badgeType: "GLOBAL" as const,
  };

  it("renders badge with name", () => {
    render(<Badge badge={mockBadge} showTooltip={false} />);
    expect(screen.getByText("Test Badge")).toBeInTheDocument();
  });

  it("renders with default icon when icon not found", () => {
    const badgeWithInvalidIcon = {
      ...mockBadge,
      icon: "NonExistentIcon",
    };
    render(<Badge badge={badgeWithInvalidIcon} showTooltip={false} />);
    expect(screen.getByText("Test Badge")).toBeInTheDocument();
  });

  it("renders with different sizes", () => {
    const { rerender } = render(
      <Badge badge={mockBadge} size="mini" showTooltip={false} />
    );
    expect(screen.getByText("Test Badge")).toBeInTheDocument();

    rerender(<Badge badge={mockBadge} size="large" showTooltip={false} />);
    expect(screen.getByText("Test Badge")).toBeInTheDocument();
  });

  it("renders badge with corpus type", () => {
    const corpusBadge = {
      ...mockBadge,
      badgeType: "CORPUS" as const,
      corpus: {
        title: "Test Corpus",
      },
    };
    render(<Badge badge={corpusBadge} showTooltip={false} />);
    expect(screen.getByText("Test Badge")).toBeInTheDocument();
  });

  it("renders badge with awarded information", () => {
    const awardedBadge = {
      ...mockBadge,
      awardedAt: "2024-01-01T00:00:00Z",
      awardedBy: {
        username: "admin",
      },
    };
    render(<Badge badge={awardedBadge} showTooltip={false} />);
    expect(screen.getByText("Test Badge")).toBeInTheDocument();
  });
});
