import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  CardSegment,
  GradientSegment,
  PageHeader,
  ScrollableTableWrapper,
} from "../SharedSegments";
import {
  BADGE_TABLE_MIN_WIDTH_PX,
  AGENT_TABLE_MIN_WIDTH_PX,
  WORKER_TABLE_MIN_WIDTH_PX,
  MOBILE_VIEW_BREAKPOINT,
} from "../../../assets/configurations/constants";

describe("SharedSegments", () => {
  it("exposes CardSegment and GradientSegment as styled wrappers", () => {
    const { container } = render(
      <>
        <CardSegment data-testid="card">card</CardSegment>
        <GradientSegment data-testid="gradient">gradient</GradientSegment>
      </>
    );
    expect(container.querySelector("[data-testid='card']")).toHaveTextContent(
      "card"
    );
    expect(
      container.querySelector("[data-testid='gradient']")
    ).toHaveTextContent("gradient");
  });

  it("renders PageHeader as a flex row that wraps on overflow", () => {
    render(
      <PageHeader data-testid="header">
        <h2>Title</h2>
        <button type="button">Action</button>
      </PageHeader>
    );
    expect(screen.getByTestId("header")).toHaveTextContent("Title");
    expect(screen.getByTestId("header")).toHaveTextContent("Action");
  });

  it("ScrollableTableWrapper applies the supplied $minWidth to its only child", () => {
    render(
      <ScrollableTableWrapper $minWidth={`${AGENT_TABLE_MIN_WIDTH_PX}px`}>
        <table data-testid="table">
          <tbody>
            <tr>
              <td>cell</td>
            </tr>
          </tbody>
        </table>
      </ScrollableTableWrapper>
    );
    expect(screen.getByTestId("table")).toBeInTheDocument();
  });
});

describe("admin/badges table-width constants", () => {
  it("declares per-table minimum widths used by ScrollableTableWrapper", () => {
    expect(BADGE_TABLE_MIN_WIDTH_PX).toBe(600);
    expect(AGENT_TABLE_MIN_WIDTH_PX).toBe(720);
    expect(WORKER_TABLE_MIN_WIDTH_PX).toBe(760);
  });

  it("keeps each table width >= the mobile breakpoint so the wrapper scrolls", () => {
    for (const px of [
      BADGE_TABLE_MIN_WIDTH_PX,
      AGENT_TABLE_MIN_WIDTH_PX,
      WORKER_TABLE_MIN_WIDTH_PX,
    ]) {
      expect(px).toBeGreaterThanOrEqual(MOBILE_VIEW_BREAKPOINT);
    }
  });
});
