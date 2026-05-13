import { describe, expect, it } from "vitest";

import {
  APP_CONTAINER_STYLE,
  APP_SHELL_FLEX_SHELL_STYLE,
  APP_SHELL_FOOTER_WRAPPER_STYLE,
  APP_SHELL_OUTER_STYLE,
} from "../appShellLayout";

describe("APP_SHELL_OUTER_STYLE", () => {
  it("uses the visible viewport as a floor, not a ceiling, so longer pages can scroll", () => {
    expect(APP_SHELL_OUTER_STYLE.minHeight).toBe(
      "var(--oc-visible-viewport-height, 100vh)"
    );
    expect(APP_SHELL_OUTER_STYLE.height).toBeUndefined();
    expect(APP_SHELL_OUTER_STYLE.maxHeight).toBeUndefined();
  });

  it("does not clip overflow", () => {
    expect(APP_SHELL_OUTER_STYLE.overflow).toBeUndefined();
  });

  it("does not center vertically (issue #1558)", () => {
    expect(APP_SHELL_OUTER_STYLE.justifyContent).toBeUndefined();
  });

  it("is a flex column", () => {
    expect(APP_SHELL_OUTER_STYLE.display).toBe("flex");
    expect(APP_SHELL_OUTER_STYLE.flexDirection).toBe("column");
  });
});

describe("APP_SHELL_FLEX_SHELL_STYLE", () => {
  it("grows to fill the outer wrapper while allowing shrink (flex: 1, minHeight: 0)", () => {
    expect(APP_SHELL_FLEX_SHELL_STYLE.flex).toBe(1);
    expect(APP_SHELL_FLEX_SHELL_STYLE.minHeight).toBe(0);
  });

  it("does not impose a 100vh ceiling or clip overflow", () => {
    expect(APP_SHELL_FLEX_SHELL_STYLE.height).toBeUndefined();
    expect(APP_SHELL_FLEX_SHELL_STYLE.maxHeight).toBeUndefined();
    expect(APP_SHELL_FLEX_SHELL_STYLE.overflow).toBeUndefined();
  });

  it("is a positioned flex column", () => {
    expect(APP_SHELL_FLEX_SHELL_STYLE.display).toBe("flex");
    expect(APP_SHELL_FLEX_SHELL_STYLE.flexDirection).toBe("column");
    expect(APP_SHELL_FLEX_SHELL_STYLE.position).toBe("relative");
  });
});

describe("APP_CONTAINER_STYLE", () => {
  it("grows to push the footer down (flex: 1)", () => {
    expect(APP_CONTAINER_STYLE.flex).toBe(1);
  });

  it("does not clip routed content (no overflow: hidden)", () => {
    expect(APP_CONTAINER_STYLE.overflow).toBeUndefined();
  });

  it("aligns content to the top (justifyContent: flex-start)", () => {
    expect(APP_CONTAINER_STYLE.justifyContent).toBe("flex-start");
  });

  it("zeroes margin and padding so routes own their gutters", () => {
    expect(APP_CONTAINER_STYLE.margin).toBe("0px");
    expect(APP_CONTAINER_STYLE.padding).toBe("0px");
  });

  it("uses minHeight: 0 so flex children can shrink correctly", () => {
    expect(APP_CONTAINER_STYLE.minHeight).toBe(0);
  });

  it("does not pin minWidth to 100vw (scrollbar overflow regression)", () => {
    // 100vw includes the scrollbar width but the parent flex container does
    // not. Pinning minWidth to 100vw forces a horizontal scrollbar whenever
    // vertical scroll is active on systems with non-overlay scrollbars.
    expect(APP_CONTAINER_STYLE.minWidth).toBeUndefined();
  });
});

describe("APP_SHELL_FOOTER_WRAPPER_STYLE", () => {
  it("never shrinks (flexShrink: 0)", () => {
    expect(APP_SHELL_FOOTER_WRAPPER_STYLE.flexShrink).toBe(0);
  });

  it("does not use a negative margin to hide a gradient strip (issue #1558)", () => {
    expect(APP_SHELL_FOOTER_WRAPPER_STYLE.marginTop).toBeUndefined();
    expect(APP_SHELL_FOOTER_WRAPPER_STYLE.margin).toBeUndefined();
  });

  it("is positioned relatively for stacked content", () => {
    expect(APP_SHELL_FOOTER_WRAPPER_STYLE.position).toBe("relative");
  });
});
