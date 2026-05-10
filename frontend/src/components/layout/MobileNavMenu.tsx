import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation } from "react-router-dom";
import styled, { css } from "styled-components";
import { motion, AnimatePresence } from "framer-motion";
import { Menu, X, LogIn } from "lucide-react";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
  accentAlpha,
} from "../../assets/configurations/osLegalStyles";
import { initialsFor } from "../../utils/initials";

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
  icon: React.ReactNode;
  onClick: () => void;
  danger?: boolean;
}

export interface MobileNavMenuProps {
  logo: React.ReactNode;
  brandName: string;
  items: MobileNavItem[];
  activeId?: string;
  /** Display name for the authenticated user; absent when signed out. */
  userName?: string;
  /** Auth actions shown inside the sheet when signed in. */
  userActions?: MobileUserAction[];
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

// ``slate-950``-ish base used for the backdrop wash and sheet-shadow
// stops. Hoisted so the three RGBA sites below stay in lockstep — and
// so a future palette move only needs one edit. There's no
// ``OS_LEGAL_COLORS`` token for this exact stop today; if one is added
// later, swap the constant out.
const DARK_BASE_RGB = "15, 23, 42";

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
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
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
      props.$open ? "rgba(255, 255, 255, 0.18)" : "rgba(255, 255, 255, 0.08)"};
  background: ${(props) =>
    props.$open ? "rgba(255, 255, 255, 0.08)" : "transparent"};
  color: ${OS_LEGAL_COLORS.surface};
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;

  &:hover {
    background: rgba(255, 255, 255, 0.1);
    border-color: rgba(255, 255, 255, 0.18);
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

const Sheet = styled(motion.nav)`
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
`;

const SheetScroll = styled.div`
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
export const MobileNavMenu: React.FC<MobileNavMenuProps> = ({
  logo,
  brandName,
  items,
  activeId,
  userName,
  userActions = [],
  onLogin,
  hideAuth = false,
}) => {
  const [open, setOpen] = useState(false);
  const { pathname, search } = useLocation();
  const sheetRef = useRef<HTMLElement | null>(null);
  // Remember the trigger so we can return focus to it on close (WCAG
  // 2.1 SC 2.4.3 — keyboard users must land back where they came from).
  const toggleRef = useRef<HTMLButtonElement | null>(null);

  // Close the sheet whenever the route changes — covers both in-sheet
  // taps and external state changes. ``search`` is in the dep list so
  // updating filter / query params (e.g. from a deep link in the sheet)
  // also dismisses the nav; mobile flows treat such transitions as full
  // navigations even when the pathname is unchanged.
  useEffect(() => {
    setOpen(false);
  }, [pathname, search]);

  // Lock body scroll, listen for ESC, and manage focus while the sheet
  // is open.
  useEffect(() => {
    if (!open) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", handleKey);

    // Focus management: move focus to the first focusable element
    // inside the sheet on open. Falls back to the sheet container so
    // ESC still works if nothing tabbable is rendered.
    const focusTimer = window.setTimeout(() => {
      const sheet = sheetRef.current;
      if (!sheet) return;
      const firstFocusable = sheet.querySelector<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      (firstFocusable ?? sheet).focus();
    }, 0);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKey);
      window.clearTimeout(focusTimer);
      // Return focus to the toggle on close. ``open`` flipping to
      // ``false`` is the trigger; this cleanup runs once per close.
      toggleRef.current?.focus();
    };
  }, [open]);

  // Single handler for nav-item / user-action clicks — both shapes
  // share "run onClick, then close the sheet".
  const runAndClose = useCallback((onClick: () => void) => {
    onClick();
    setOpen(false);
  }, []);

  const handleLogin = () => {
    setOpen(false);
    onLogin?.();
  };

  const sheetOverlay = (
    <AnimatePresence>
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
            aria-label="Site navigation"
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
            <SheetScroll>
              <SectionLabel>Browse</SectionLabel>
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
                  <SectionLabel>Account</SectionLabel>
                  {userActions.map((action) => (
                    <NavItemButton
                      key={action.id}
                      type="button"
                      $danger={action.danger}
                      onClick={() => runAndClose(action.onClick)}
                    >
                      <NavItemIcon $danger={action.danger}>
                        {action.icon}
                      </NavItemIcon>
                      {action.label}
                    </NavItemButton>
                  ))}
                </>
              )}
            </SheetScroll>

            {!hideAuth && (
              <AuthFooter>
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
