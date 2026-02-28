import { NavBar } from "@os-legal/ui";
import type { NavItem, UserMenuItem } from "@os-legal/ui";
import { useNavigate } from "react-router-dom";
import styled from "styled-components";
import { Download, User, Settings, LogOut } from "lucide-react";
import { showExportModal, showUserSettingsModal } from "../../graphql/cache";
import UserSettingsModal from "../modals/UserSettingsModal";
import { VERSION_TAG } from "../../assets/configurations/constants";
import { useNavMenu } from "./useNavMenu";
import useWindowDimensions from "../hooks/WindowDimensionHook";
import logo from "../../assets/images/os_legal_128.png";

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

// Custom styles for navbar - overrides for @os-legal/ui NavBar
// Note: These use !important due to specificity requirements with external component
const navbarCustomStyles = `
  /* Version badge - filled background */
  .oc-navbar .oc-chip {
    background: rgba(255, 255, 255, 0.15) !important;
    color: rgba(255, 255, 255, 0.9) !important;
  }
  /* Keep brand name visible on mobile */
  .oc-navbar__brand-name {
    display: block !important;
  }
`;

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

  // On mobile (< 1100px where NavBar collapses), hide version badge but keep brand name
  const isMobile = width < 1100;
  const versionDisplay = isMobile ? undefined : VERSION_TAG;

  // Extract typed user properties for display (name/username)
  const userProps = getUserProps(user);

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

  return (
    <>
      <style>{navbarCustomStyles}</style>
      <UserSettingsModal />
      <NavBar
        logo={
          <img
            src={logo}
            alt="Open Contracts Logo"
            style={{ width: 32, height: 32, objectFit: "contain" }}
          />
        }
        brandName="Open Contracts"
        version={versionDisplay}
        items={navItems}
        activeId={activeId}
        onNavigate={handleNavigate}
        userName={user ? userProps.name || userProps.username : undefined}
        userMenuItems={userMenuItems}
        hideUserMenu={isLoading || !user}
        actions={
          !user && !isLoading ? (
            <LoginButton onClick={handleLogin}>Login</LoginButton>
          ) : undefined
        }
      />
    </>
  );
};
