import type { CSSProperties } from "react";

/** Sticky-footer SPA shell layout (issue #1558). */
export const APP_SHELL_OUTER_STYLE: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  minHeight: "100vh",
};

export const APP_SHELL_FLEX_SHELL_STYLE: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  position: "relative",
  flex: 1,
  minHeight: 0,
};

// minWidth intentionally omitted: 100vw includes scrollbar width but the
// parent flex container does not, which forces a horizontal scrollbar on
// systems with non-overlay scrollbars whenever vertical scroll is active.
// width: 100% already fills the parent.
export const APP_CONTAINER_STYLE: CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  justifyContent: "flex-start",
  width: "100%",
  margin: "0px",
  padding: "0px",
  minHeight: 0,
};

export const APP_SHELL_FOOTER_WRAPPER_STYLE: CSSProperties = {
  flexShrink: 0,
  position: "relative",
};
