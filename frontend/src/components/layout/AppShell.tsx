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

/**
 * Sticky-footer SPA shell.
 *
 * Owns the four nested wrappers that compose the top-level layout so the
 * ``appShellLayout`` style constants are applied in a single small component
 * that can be unit-tested without standing up the whole ``App`` provider tree.
 */
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

  return (
    <div style={APP_SHELL_OUTER_STYLE}>
      {overlays}
      {ThemeWrapper ? <ThemeWrapper>{innerTree}</ThemeWrapper> : innerTree}
    </div>
  );
};
