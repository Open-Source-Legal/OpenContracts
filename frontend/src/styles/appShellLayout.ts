import type { CSSProperties } from "react";

/**
 * Sticky-footer SPA shell layout.
 *
 * The shell stacks: outer wrapper → flex shell → AppContainer (main routes) →
 * footer wrapper. Each layer's responsibility:
 *
 * - **outer**: floor of 100vh so short pages fill the viewport, but no
 *   ``height: 100vh`` ceiling so longer pages can grow naturally and the
 *   body scrolls. ``justifyContent: center`` is intentionally absent — it
 *   would have negatively offset overflow content if a page exceeded 100vh.
 * - **flexShell**: ``flex: 1`` so it consumes the outer wrapper's free space,
 *   ``minHeight: 0`` so its children can shrink correctly inside flex.
 * - **appContainer**: ``flex: 1`` so the main routes area grows to push the
 *   footer down. ``minHeight: 0`` for the same flex shrink reason.
 * - **footerWrapper**: ``flexShrink: 0`` so the footer never gets squished
 *   away. Previously had ``marginTop: -1.5rem`` to mask the gradient strip
 *   exposed by the ``overflow: hidden`` clamps; that hack is no longer needed
 *   now that the inner wrappers don't clip overflow.
 */
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

export const APP_CONTAINER_STYLE: CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  justifyContent: "flex-start",
  width: "100%",
  margin: "0px",
  padding: "0px",
  minWidth: "100vw",
  minHeight: 0,
};

export const APP_SHELL_FOOTER_WRAPPER_STYLE: CSSProperties = {
  flexShrink: 0,
  position: "relative",
};
