import React from "react";

import {
  APP_CONTAINER_STYLE,
  APP_SHELL_FLEX_SHELL_STYLE,
  APP_SHELL_FOOTER_WRAPPER_STYLE,
  APP_SHELL_OUTER_STYLE,
} from "../../styles/appShellLayout";

export interface AppShellProps {
  /** Top-level overlays / portals (modals, toasts) rendered above the shell. */
  overlays?: React.ReactNode;
  /** Wrapper for the in-shell tree, e.g. ``<ThemeProvider>``. Optional so unit
   *  tests can mount the shell without bringing the full provider tree along.
   */
  themeProvider?: React.ComponentType<{ children: React.ReactNode }>;
  /** The persistent navigation bar. */
  navMenu: React.ReactNode;
  /** Per-route content rendered inside ``#AppContainer``. */
  children: React.ReactNode;
  /** Footer content — only rendered when ``showFooter`` is true. */
  footer?: React.ReactNode;
  /** ``false`` hides the footer (e.g. while a corpus is opened). Defaults to true. */
  showFooter?: boolean;
}

/** Sticky-footer SPA shell (issue #1558). */
export const AppShell: React.FC<AppShellProps> = ({
  overlays,
  themeProvider: ThemeWrapper,
  navMenu,
  children,
  footer,
  showFooter = true,
}) => {
  const innerTree = (
    <div style={APP_SHELL_FLEX_SHELL_STYLE}>
      {navMenu}
      <div id="AppContainer" style={APP_CONTAINER_STYLE}>
        {children}
      </div>
      {showFooter && footer ? (
        <div style={APP_SHELL_FOOTER_WRAPPER_STYLE}>{footer}</div>
      ) : null}
    </div>
  );

  // overlays render outside the optional ThemeProvider so toasts/modals that
  // consume the theme context will fall back to defaults (matches App.tsx).
  return (
    <div style={APP_SHELL_OUTER_STYLE}>
      {overlays}
      {ThemeWrapper ? <ThemeWrapper>{innerTree}</ThemeWrapper> : innerTree}
    </div>
  );
};
