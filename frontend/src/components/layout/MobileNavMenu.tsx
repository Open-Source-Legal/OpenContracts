import { useCallback, useEffect, useRef, useState } from "react";
import type { FC, ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link, useLocation } from "react-router-dom";
import styled, { css } from "styled-components";
import { motion, AnimatePresence } from "framer-motion";
import { Menu, X, LogIn } from "lucide-react";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
  accentAlpha,
  whiteSurfaceAlpha,
} from "../../assets/configurations/osLegalStyles";
import { initialsFor } from "../../utils/initials";
import type { OverflowMenuLink } from "./overflowMenuItems";

/**
 * Lightweight nav-item shape used by the mobile menu. Mirrors the subset of
 * @os-legal/ui's NavItem that we need here so we don't depend on its internals.
 */
export interface MobileNavItem {
  id: string;
  label: string;
  onClick: () => void;
}

export interface MobileUserAction {
  id: string;
  label: string;
  icon?: ReactNode;
  onClick: () => void;
  danger?: boolean;
}

export interface MobileNavMenuProps {
  logo: ReactNode;
  brandName: string;
  items: MobileNavItem[];
  activeId?: string;
  /** Display name for the authenticated user; absent when signed out. */
  userName?: string;
  /** Auth actions shown inside the sheet when signed in. */
  userActions?: MobileUserAction[];
  /**
   * Footer-essential links rendered in the sheet's "More" section so they
   * remain reachable on long-scroll surfaces where the in-flow Footer is
   * effectively out of reach. See issue #1609.
   */
  overflowLinks?: OverflowMenuLink[];
  /** Version tag rendered at the bottom of the sheet alongside the overflow. */
  version?: string;
  /** Triggered when the visitor taps the "Sign in" CTA (signed-out only). */
  onLogin?: () => void;
  /** Disable the auth section entirely (e.g., while Auth0 is still loading). */
  hideAuth?: boolean;
}

/* ------------------------------------------------------------------ */
/*  Layout constants                                                   */
/* ------------------------------------------------------------------ */

const HEADER_HEIGHT = 60;
const SHEET_TOP_OFFSET = HEADER_HEIGHT + 8;
const SHEET_SIDE_GUTTER = 12;

// Hoisted so the three RGBA sites below stay in lockstep.
const DARK_BASE_RGB = "15, 23, 42";

const FOCUSABLE_SELECTOR =
  'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

// Section labels in the sheet — pulled out so translations / theming
// can swap them without hunting through JSX.
const SECTION_LABEL_BROWSE = "Browse";
const SECTION_LABEL_ACCOUNT = "Account";
const SECTION_LABEL_MORE = "More";

/* ------------------------------------------------------------------ */
/*  Styled components — header                                         */
/* ------------------------------------------------------------------ */

const Header = styled.header`
  position: sticky;
  top: 0;
  z-index: 1100;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: ${HEADER_HEIGHT}px;
  padding: 0 16px;
  background: ${OS_LEGAL_COLORS.darkSurface};
  color: ${OS_LEGAL_COLORS.surface};
  border-bottom: 1px solid ${whiteSurfaceAlpha(0.06)};
`;

const Brand = styled.div`
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
`;

const BrandName = styled.span`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 16px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: ${OS_LEGAL_COLORS.surface};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const ToggleButton = styled.button<{ $open: boolean }>`
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  border: 1px solid
    ${(props) =>
      props.$open ? whiteSurfaceAlpha(0.18) : whiteSurfaceAlpha(0.08)};
  background: ${(props) =>
    props.$open ? whiteSurfaceAlpha(0.08) : "transparent"};
  color: ${OS_LEGAL_COLORS.surface};
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;

  &:hover {
    background: ${whiteSurfaceAlpha(0.1)};
    border-color: ${whiteSurfaceAlpha(0.18)};
  }

  &:focus-visible {
    outline: 2px solid ${OS_LEGAL_COLORS.accent};
    outline-offset: 2px;
  }
`;

/* ------------------------------------------------------------------ */
/*  Styled components — backdrop & sheet                               */
/* ------------------------------------------------------------------ */

const Backdrop = styled(motion.div)`
  position: fixed;
  inset: 0;
  z-index: 1090;
  background: rgba(${DARK_BASE_RGB}, 0.42);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
`;

// Modal container (NOT a landmark). `role="dialog"` on a `<nav>` would
// override the implicit navigation landmark semantics and remove it from
// the a11y tree — see issue #1610. The actual navigation landmark lives
// inside this dialog as `SheetNav` below, which keeps dialog and
// landmark roles cleanly separated.
const Sheet = styled(motion.div)`
  position: fixed;
  top: ${SHEET_TOP_OFFSET}px;
  left: ${SHEET_SIDE_GUTTER}px;
  right: ${SHEET_SIDE_GUTTER}px;
  z-index: 1095;
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - ${SHEET_TOP_OFFSET + SHEET_SIDE_GUTTER}px);
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 16px;
  box-shadow: 0 20px 50px -12px rgba(${DARK_BASE_RGB}, 0.28),
    0 6px 18px -8px rgba(${DARK_BASE_RGB}, 0.12);
  overflow: hidden;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};

  /* Empty-focusables fallback receives focus programmatically; the
     default UA outline on a -1 tabindex container is jarring so we
     suppress it. Tabbable children keep their own focus rings. */
  &:focus-visible {
    outline: none;
  }
`;

// Inner navigation landmark — wraps only the nav items + Account actions
// so the AuthFooter's Sign-in CTA / user chip stays *outside* the landmark
// (it's not navigation, it's auth state).
const SheetNav = styled.nav`
  flex: 1;
  overflow-y: auto;
  padding: 8px;
`;

const SectionLabel = styled.div`
  padding: 12px 12px 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const navItemActiveStyles = css`
  color: ${OS_LEGAL_COLORS.accent};
  background: ${OS_LEGAL_COLORS.accentSurface};

  &::before {
    background: ${OS_LEGAL_COLORS.accent};
  }
`;

const NavItemButton = styled.button<{ $active?: boolean; $danger?: boolean }>`
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-height: 44px;
  padding: 0 12px 0 18px;
  border: none;
  background: transparent;
  color: ${(props) =>
    props.$danger ? OS_LEGAL_COLORS.danger : OS_LEGAL_COLORS.textPrimary};
  font: inherit;
  font-size: 15px;
  font-weight: 500;
  text-align: left;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease;

  &::before {
    content: "";
    position: absolute;
    left: 6px;
    top: 50%;
    transform: translateY(-50%);
    width: 3px;
    height: 18px;
    border-radius: 2px;
    background: transparent;
    transition: background 0.12s ease;
  }

  &:hover {
    background: ${(props) =>
      props.$danger
        ? OS_LEGAL_COLORS.dangerSurface
        : OS_LEGAL_COLORS.surfaceHover};
  }

  &:focus-visible {
    outline: 2px solid ${OS_LEGAL_COLORS.accent};
    outline-offset: 2px;
  }

  ${(props) => props.$active && navItemActiveStyles}
`;

const NavItemIcon = styled.span<{ $danger?: boolean }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: ${(props) =>
    props.$danger ? OS_LEGAL_COLORS.danger : OS_LEGAL_COLORS.textSecondary};
`;

const Divider = styled.div`
  height: 1px;
  margin: 6px 12px;
  background: ${OS_LEGAL_COLORS.border};
`;

// Shared styles for the "More" overflow link rows. They are visually
// quieter than NavItemButton (lighter weight, no active rail) because
// they are secondary destinations — privacy / terms / GitHub — not the
// primary site navigation.
const overflowLinkStyles = css`
  display: flex;
  align-items: center;
  width: 100%;
  min-height: 40px;
  padding: 0 12px;
  border: none;
  background: transparent;
  color: ${OS_LEGAL_COLORS.textPrimary};
  font: inherit;
  font-size: 14px;
  font-weight: 500;
  text-align: left;
  text-decoration: none;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    color: ${OS_LEGAL_COLORS.accent};
    text-decoration: none;
  }

  &:focus-visible {
    outline: 2px solid ${OS_LEGAL_COLORS.accent};
    outline-offset: 2px;
  }
`;

const OverflowItemLink = styled(Link)`
  ${overflowLinkStyles}
`;

const OverflowItemAnchor = styled.a`
  ${overflowLinkStyles}
`;

const VersionRow = styled.div`
  padding: 8px 12px 12px;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

/* ------------------------------------------------------------------ */
/*  Styled components — auth area                                      */
/* ------------------------------------------------------------------ */

const AuthFooter = styled.div`
  border-top: 1px solid ${OS_LEGAL_COLORS.border};
  padding: 12px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
`;

const SignInButton = styled.button`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  height: 44px;
  border-radius: 10px;
  border: none;
  background: ${OS_LEGAL_COLORS.accent};
  color: ${OS_LEGAL_COLORS.surface};
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.01em;
  cursor: pointer;
  transition: background 0.12s ease, box-shadow 0.12s ease;
  box-shadow: 0 1px 2px ${accentAlpha(0.15)};

  &:hover {
    background: ${OS_LEGAL_COLORS.accentHover};
    box-shadow: 0 4px 14px ${accentAlpha(0.25)};
  }

  &:focus-visible {
    outline: 2px solid ${OS_LEGAL_COLORS.accent};
    outline-offset: 2px;
  }
`;

const UserChip = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px 10px;
`;

const Avatar = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: ${OS_LEGAL_COLORS.accent};
  color: ${OS_LEGAL_COLORS.surface};
  font-weight: 600;
  font-size: 14px;
  flex-shrink: 0;
`;

const UserMeta = styled.div`
  display: flex;
  flex-direction: column;
  min-width: 0;
`;

const UserNameLabel = styled.span`
  font-size: 14px;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const UserStatusLabel = styled.span`
  font-size: 12px;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

/**
 * Mobile-only nav header + floating sheet. Replaces the heavier built-in
 * drawer from @os-legal/ui with a lighter, content-overlaying sheet that
 * matches the os-legal design language (white surface, teal accent, soft
 * shadow, backdrop blur).
 */
export const MobileNavMenu: FC<MobileNavMenuProps> = ({
  logo,
  brandName,
  items,
  activeId,
  userName,
  userActions = [],
  overflowLinks = [],
  version,
  onLogin,
  hideAuth = false,
}) => {
  const [open, setOpen] = useState(false);
  const { pathname, search } = useLocation();
  const sheetRef = useRef<HTMLDivElement | null>(null);
  // Restore focus to the trigger on close (WCAG 2.1 SC 2.4.3).
  const toggleRef = useRef<HTMLButtonElement | null>(null);
  // Captured overflow values; restored in onExitComplete so scroll
  // doesn't re-enable while the exit animation is still playing.
  // We lock both <body> and <html> because iOS Safari ignores
  // ``body { overflow: hidden }`` for its rubber-band / overscroll
  // gesture — ``documentElement`` is what actually stops the bleed-through.
  const savedBodyOverflowRef = useRef<string>("");
  const savedHtmlOverflowRef = useRef<string>("");

  // Dismiss on route change — covers in-sheet taps and external nav.
  useEffect(() => {
    setOpen(false);
  }, [pathname, search]);

  // Belt-and-suspenders: if the component unmounts mid-animation
  // (hard navigation while open), AnimatePresence#onExitComplete
  // never fires — restore overflow on unmount instead so the page
  // isn't left scroll-locked.
  useEffect(
    () => () => {
      document.body.style.overflow = savedBodyOverflowRef.current;
      document.documentElement.style.overflow = savedHtmlOverflowRef.current;
    },
    []
  );

  // Lock body scroll, listen for ESC + Tab focus trap, and manage
  // focus while the sheet is open.
  useEffect(() => {
    if (!open) return;

    savedBodyOverflowRef.current = document.body.style.overflow;
    savedHtmlOverflowRef.current = document.documentElement.style.overflow;
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";

    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        return;
      }

      if (event.key !== "Tab") return;

      // Manual Tab trap — ARIA APG dialog pattern.
      const sheet = sheetRef.current;
      if (!sheet) return;

      const focusables = Array.from(
        sheet.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
      ).filter((el) => !el.hasAttribute("disabled"));

      if (focusables.length === 0) {
        // Nothing tabbable — pin focus to the container.
        event.preventDefault();
        sheet.focus();
        return;
      }

      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement as HTMLElement | null;

      if (!sheet.contains(active)) {
        // Focus leaked outside the sheet — pull it back in.
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
        return;
      }

      if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handleKey);

    // Seed focus on the first focusable inside the sheet; fall back
    // to the container so ESC still works when nothing is tabbable.
    const focusTimer = window.setTimeout(() => {
      const sheet = sheetRef.current;
      if (!sheet) return;
      const firstFocusable =
        sheet.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
      (firstFocusable ?? sheet).focus();
    }, 0);

    return () => {
      // Scroll restoration runs in onExitComplete — see savedOverflowRef.
      window.removeEventListener("keydown", handleKey);
      window.clearTimeout(focusTimer);
      toggleRef.current?.focus();
    };
  }, [open]);

  // Run the action then close. try/finally so a throwing handler
  // still dismisses the sheet (no stranded UI).
  const runAndClose = useCallback((onClick: () => void) => {
    try {
      onClick();
    } finally {
      setOpen(false);
    }
  }, []);

  const handleLogin = useCallback(() => {
    setOpen(false);
    onLogin?.();
  }, [onLogin]);

  const sheetOverlay = (
    <AnimatePresence
      onExitComplete={() => {
        // Restore body + html scroll only after the exit animation finishes.
        // See ``savedBodyOverflowRef`` declaration for the rationale.
        document.body.style.overflow = savedBodyOverflowRef.current;
        document.documentElement.style.overflow = savedHtmlOverflowRef.current;
      }}
    >
      {open && (
        <>
          <Backdrop
            key="mobile-nav-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />
          <Sheet
            key="mobile-nav-sheet"
            ref={sheetRef}
            id="mobile-nav-sheet"
            role="dialog"
            aria-modal="true"
            aria-label="Navigation menu"
            // ``tabIndex={-1}`` lets the sheet itself receive
            // programmatic focus from the focus-management effect when
            // no nav item is tabbable yet (auth still loading, items
            // empty), without making it appear in the natural tab order.
            tabIndex={-1}
            initial={{ opacity: 0, y: -10, scale: 0.985 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.99 }}
            transition={{
              type: "spring",
              stiffness: 320,
              damping: 32,
              mass: 0.7,
            }}
          >
            <SheetNav aria-label="Site navigation">
              <SectionLabel>{SECTION_LABEL_BROWSE}</SectionLabel>
              {items.map((item) => (
                <NavItemButton
                  key={item.id}
                  id={item.id}
                  type="button"
                  $active={item.id === activeId}
                  onClick={() => runAndClose(item.onClick)}
                >
                  {item.label}
                </NavItemButton>
              ))}

              {userName && userActions.length > 0 && (
                <>
                  <Divider />
                  <SectionLabel>{SECTION_LABEL_ACCOUNT}</SectionLabel>
                  {userActions.map((action) => (
                    <NavItemButton
                      key={action.id}
                      type="button"
                      $danger={action.danger}
                      onClick={() => runAndClose(action.onClick)}
                    >
                      {action.icon && (
                        <NavItemIcon $danger={action.danger}>
                          {action.icon}
                        </NavItemIcon>
                      )}
                      {action.label}
                    </NavItemButton>
                  ))}
                </>
              )}

              {overflowLinks.length > 0 && (
                <>
                  <Divider />
                  <SectionLabel>{SECTION_LABEL_MORE}</SectionLabel>
                  {overflowLinks.map((link) =>
                    link.to ? (
                      <OverflowItemLink
                        key={link.id}
                        to={link.to}
                        onClick={() => setOpen(false)}
                      >
                        {link.label}
                      </OverflowItemLink>
                    ) : (
                      <OverflowItemAnchor
                        key={link.id}
                        href={link.href}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={() => setOpen(false)}
                      >
                        {link.label}
                      </OverflowItemAnchor>
                    )
                  )}
                  {version && (
                    <VersionRow aria-label={`Version ${version}`}>
                      {version}
                    </VersionRow>
                  )}
                </>
              )}
            </SheetNav>

            {!hideAuth && (
              <AuthFooter data-testqa="mobile-nav-auth-footer">
                {userName ? (
                  <UserChip>
                    <Avatar>{initialsFor(userName)}</Avatar>
                    <UserMeta>
                      <UserNameLabel>{userName}</UserNameLabel>
                      <UserStatusLabel>Signed in</UserStatusLabel>
                    </UserMeta>
                  </UserChip>
                ) : (
                  <SignInButton type="button" onClick={handleLogin}>
                    <LogIn size={16} aria-hidden="true" />
                    Sign in
                  </SignInButton>
                )}
              </AuthFooter>
            )}
          </Sheet>
        </>
      )}
    </AnimatePresence>
  );

  return (
    <>
      <Header>
        <Brand>
          {logo}
          <BrandName>{brandName}</BrandName>
        </Brand>
        {/*
          Toggle is intentionally OUTSIDE ``sheetRef`` (the focus-trap
          container). The Header sits above the Sheet at z-index 1100 so
          the toggle stays tap-targetable while the dialog is open;
          tapping it closes the sheet via ``setOpen`` rather than via
          the trap. The trap's "focus leaked outside" branch still pulls
          focus back if the user tabs onto the toggle.

          ``aria-controls`` references an element that lives in a portal
          at ``document.body`` and only exists in the DOM while ``open``
          is true. Screen readers tolerate the dangling reference when
          closed and resolve it correctly once portalled; we keep the
          attribute static (rather than toggling with ``open``) so
          assistive tech sees a stable relationship from the toggle to
          its controlled element.
        */}
        <ToggleButton
          ref={toggleRef}
          type="button"
          $open={open}
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-controls="mobile-nav-sheet"
          aria-label={open ? "Close navigation" : "Open navigation"}
          onClick={() => setOpen((prev) => !prev)}
        >
          {open ? <X size={20} /> : <Menu size={20} />}
        </ToggleButton>
      </Header>
      {typeof document !== "undefined"
        ? createPortal(sheetOverlay, document.body)
        : sheetOverlay}
    </>
  );
};
