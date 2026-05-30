import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { NavBar } from "@os-legal/ui";
import type { NavItem, UserMenuItem } from "@os-legal/ui";
import { useNavigate } from "react-router-dom";
import styled from "styled-components";
import { Download, User, Settings, LogOut, Cog } from "lucide-react";
import { showExportModal, showUserSettingsModal } from "../../graphql/cache";
import UserSettingsModal from "../modals/UserSettingsModal";
import { VERSION_TAG } from "../../assets/configurations/constants";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
} from "../../assets/configurations/osLegalStyles";
import { useNavMenu } from "./useNavMenu";
import useWindowDimensions from "../hooks/WindowDimensionHook";
import { CiteMark } from "../brand/CiteMark";
import {
  MobileNavMenu,
  type MobileNavItem,
  type MobileUserAction,
} from "./MobileNavMenu";
import { NavOverflowMenu } from "./NavOverflowMenu";
import { OVERFLOW_MENU_LINKS } from "./overflowMenuItems";

/**
 * User display properties accessed by NavMenu.
 * Covers both Auth0 User (name) and local UserType (username).
 */
interface NavMenuUserProps {
  name?: string;
  username?: string;
}

/** Type guard to safely access display properties from Auth0 User or local UserType */
const getUserProps = (user: unknown): NavMenuUserProps => {
  if (!user || typeof user !== "object") return {};
  const u = user as Record<string, unknown>;
  return {
    name: typeof u.name === "string" ? u.name : undefined,
    username: typeof u.username === "string" ? u.username : undefined,
  };
};

// Styled login button for navbar - matches dark navbar theme
const LoginButton = styled.button`
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.9);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  padding: 8px 12px;
  border-radius: 6px;
  transition: background 0.15s ease;

  &:hover {
    background: rgba(255, 255, 255, 0.1);
  }
`;

// Custom styles for the desktop @os-legal/ui NavBar.
// Note: the !important is needed to win the specificity battle with the
// library's own CSS. Mobile uses a custom component (MobileNavMenu) and
// is not affected by these rules.
const navbarCustomStyles = `
  /* Version badge - filled background */
  .oc-navbar .oc-chip {
    background: rgba(255, 255, 255, 0.15) !important;
    color: rgba(255, 255, 255, 0.9) !important;
  }
  /* cite wordmark — Source Serif 4 with the brackets preserved.
     Overrides the @os-legal/ui default of 600-weight Inter so the
     wordmark reads as a typographic mark, not a UI label. */
  .oc-navbar__brand-name {
    font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif} !important;
    font-weight: 400 !important;
    font-size: 22px !important;
    letter-spacing: -0.5px !important;
  }
`;

// Width threshold below which we render the custom mobile nav. Matches
// the prior @os-legal/ui NavBar collapse breakpoint so tablet behaviour
// stays consistent.
const MOBILE_BREAKPOINT_PX = 1100;

export const NavMenu = () => {
  const {
    user,
    isSuperuser,
    isLoading,
    REACT_APP_USE_AUTH0,
    public_header_items,
    private_header_items,
    show_export_modal,
    isActive,
    requestLogout,
    doLogin,
  } = useNavMenu();
  const navigate = useNavigate();
  const { width } = useWindowDimensions();

  const isMobile = width < MOBILE_BREAKPOINT_PX;

  // Extract typed user properties for display (name/username)
  const userProps = getUserProps(user);
  const displayName = user
    ? userProps.name || userProps.username || undefined
    : undefined;

  // Build nav items from menu configuration
  const baseNavItems = [
    ...public_header_items,
    ...(user ? private_header_items : []),
  ];

  // Add superuser-only Badge Management item
  const allMenuItems = isSuperuser
    ? [
        ...baseNavItems,
        {
          title: "Badge Management",
          route: "/admin/badges",
          id: "admin_badges_menu_button",
          protected: true,
        },
      ]
    : baseNavItems;

  // Map to NavItem format with onClick handlers for navigation
  const navItems: NavItem[] = allMenuItems.map((item) => ({
    id: item.id,
    label: item.title,
    onClick: () => navigate(item.route),
  }));

  // Login button for unauthenticated users (rendered on right side via actions prop)
  const handleLogin = REACT_APP_USE_AUTH0 ? doLogin : () => navigate("/login");

  // Build user menu items
  const userMenuItems: UserMenuItem[] = user
    ? [
        {
          id: "exports",
          label: "Exports",
          icon: <Download size={16} />,
          onClick: () => showExportModal(!show_export_modal),
        },
        {
          id: "profile",
          label: "Profile",
          icon: <User size={16} />,
          onClick: () => showUserSettingsModal(true),
        },
        ...(isSuperuser
          ? [
              {
                id: "system-settings",
                label: "System Settings",
                icon: <Cog size={16} />,
                onClick: () => navigate("/system_settings"),
              },
              {
                id: "admin",
                label: "Admin Settings",
                icon: <Settings size={16} />,
                onClick: () => navigate("/admin/settings"),
              },
            ]
          : []),
        { id: "divider", label: "", divider: true },
        {
          id: "logout",
          label: "Logout",
          icon: <LogOut size={16} />,
          danger: true,
          onClick: requestLogout,
        },
      ]
    : [];

  // Find active nav item by checking routes
  const findActiveId = (): string | undefined => {
    for (const item of allMenuItems) {
      if (isActive(item.route)) {
        return item.id;
      }
    }
    return undefined;
  };

  const activeId = findActiveId();

  // Handle navigation from NavBar
  const handleNavigate = (id: string) => {
    const item = navItems.find((i) => i.id === id);
    item?.onClick?.();
  };

  // Mobile: dividers are stripped since the sheet renders its own
  // section header.
  const mobileNavItems: MobileNavItem[] = useMemo(
    () =>
      navItems.map((item) => ({
        id: item.id,
        label: item.label,
        onClick: () => item.onClick?.(),
      })),
    [navItems]
  );

  const mobileUserActions: MobileUserAction[] = useMemo(
    () =>
      userMenuItems
        .filter((item) => !item.divider)
        .map((item) => ({
          id: item.id,
          label: item.label,
          icon: item.icon,
          onClick: () => item.onClick?.(),
          danger: item.danger,
        })),
    [userMenuItems]
  );

  // cite icon mark — the bracketed teal node. Rendered for both nav surfaces
  // beside the wordmark; brackets are kept in the brand warm-paper colour
  // so the mark sits cleanly on the navy chrome.
  const logoNode = useMemo(
    () => (
      <CiteMark
        size={28}
        bracketColor={OS_LEGAL_COLORS.warmPaper}
        nodeColor={OS_LEGAL_COLORS.accent}
        ariaLabel="cite"
      />
    ),
    []
  );

  if (isMobile) {
    return (
      <>
        <UserSettingsModal />
        <MobileNavMenu
          logo={logoNode}
          brandName="[cite]"
          items={mobileNavItems}
          activeId={activeId}
          userName={displayName}
          userActions={mobileUserActions}
          overflowLinks={OVERFLOW_MENU_LINKS}
          version={VERSION_TAG}
          onLogin={handleLogin}
          hideAuth={isLoading}
        />
      </>
    );
  }

  return (
    <>
      <style>{navbarCustomStyles}</style>
      <UserSettingsModal />
      <NavbarHeightSync />
      <NavBar
        logo={logoNode}
        brandName="[cite]"
        version={VERSION_TAG}
        items={navItems}
        activeId={activeId}
        onNavigate={handleNavigate}
        userName={displayName}
        userMenuItems={userMenuItems}
        hideUserMenu={isLoading || !user}
        actions={
          <>
            <NavOverflowMenu />
            {!user && !isLoading && (
              <LoginButton onClick={handleLogin}>Login</LoginButton>
            )}
          </>
        }
      />
    </>
  );
};

/**
 * Keeps the global `--oc-navbar-height` CSS variable in sync with the
 * actual rendered height of the `.oc-navbar` element. The variable is
 * seeded in index.css with a static estimate (72px desktop / 60px mobile),
 * but the real navbar uses `padding: 12px 24px; flex-wrap: wrap`, so the
 * actual height shifts with content/wrapping and breakpoint.
 *
 * Consumers of viewport-bounded layouts (CorpusViewContainer min-height,
 * CorpusChat tab height, CorpusQueryView's COMPOSER_MAX_HEIGHT, etc.)
 * subtract this variable from 100vh — when it lags the real height by
 * even a few pixels, the document gains a small scrollable strip below
 * the viewport.
 */
const NavbarHeightSync: React.FC = () => {
  const observerRef = useRef<ResizeObserver | null>(null);

  useLayoutEffect(() => {
    const navbar = document.querySelector<HTMLElement>(".oc-navbar");
    if (!navbar) return;

    const sync = () => {
      // Measure the fractional rendered height and round UP. `offsetHeight` is
      // an integer — it rounds the real border-box height DOWN — so a 72.5px
      // navbar reported 72px while the element still occupied 72.5px. The
      // viewport-bounded consumers below subtract this var from 100dvh, so the
      // missing 0.5px left a permanent body-scroll strip beneath every bounded
      // tab (the "subtle reposition"). `getBoundingClientRect().height` keeps
      // the sub-pixel value and `Math.ceil` guarantees the var never
      // under-reports the navbar, so reserved space always covers space used.
      const h = Math.ceil(navbar.getBoundingClientRect().height);
      if (h > 0) {
        document.documentElement.style.setProperty(
          "--oc-navbar-height",
          `${h}px`
        );
      }
    };

    sync();
    observerRef.current = new ResizeObserver(sync);
    observerRef.current.observe(navbar);

    return () => {
      observerRef.current?.disconnect();
      observerRef.current = null;
    };
  }, []);

  // Reset the inline override on unmount so the index.css default
  // re-applies if the desktop navbar disappears (e.g. on mobile resize).
  useEffect(
    () => () => {
      document.documentElement.style.removeProperty("--oc-navbar-height");
    },
    []
  );

  return null;
};
