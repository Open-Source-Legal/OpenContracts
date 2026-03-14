import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import styled from "styled-components";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
} from "../../../assets/configurations/osLegalStyles";
import {
  CONTEXT_MENU_VIEWPORT_PADDING as VIEWPORT_PADDING,
  Z_INDEX,
} from "../../../assets/configurations/constants";

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface ContextMenuItem {
  /** Unique key for the menu item */
  key: string;
  /** Lucide or other React icon element */
  icon?: React.ReactNode;
  /** Display label */
  label: string;
  /** Click handler — accepts both mouse and keyboard events */
  onClick: (e: React.MouseEvent | React.KeyboardEvent) => void;
  /** Visual variant — "danger" shows red text/hover */
  variant?: "default" | "primary" | "danger";
  /** Whether to show this item */
  visible?: boolean;
}

export interface ContextMenuProps {
  /** Menu items to render */
  items: ContextMenuItem[];
  /** Pixel position for the menu */
  position: { x: number; y: number };
  /** Called when the menu should close (click-outside, Escape) */
  onClose: () => void;
  /** Optional header text shown at the top of the menu */
  header?: string;
  /** ARIA label for the menu */
  "aria-label"?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// STYLED COMPONENTS
// ═══════════════════════════════════════════════════════════════════════════════

const MenuOverlay = styled.div`
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: ${Z_INDEX.CONTEXT_MENU_OVERLAY};
`;

const MenuContainer = styled.div`
  position: fixed;
  z-index: ${Z_INDEX.CONTEXT_MENU};
  min-width: 200px;
  background: ${OS_LEGAL_COLORS.surface};
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  border-radius: 8px;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  padding: 4px 0;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
`;

const MenuHeader = styled.div`
  padding: 8px 14px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: ${OS_LEGAL_COLORS.textMuted};
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 260px;
`;

const MenuItemStyled = styled.button<{
  $variant?: "default" | "primary" | "danger";
}>`
  padding: 10px 14px;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  transition: background 0.1s;
  width: 100%;
  border: none;
  background: none;
  text-align: left;
  font-family: inherit;
  color: ${(props) =>
    props.$variant === "danger"
      ? OS_LEGAL_COLORS.danger
      : props.$variant === "primary"
      ? OS_LEGAL_COLORS.accent
      : "inherit"};
  font-weight: ${(props) => (props.$variant === "primary" ? 500 : "inherit")};

  &:hover,
  &:focus-visible {
    background: ${(props) =>
      props.$variant === "danger"
        ? OS_LEGAL_COLORS.dangerSurface
        : OS_LEGAL_COLORS.surfaceLight};
    outline: none;
  }

  svg {
    flex-shrink: 0;
    opacity: 0.7;
  }
`;

// ═══════════════════════════════════════════════════════════════════════════════
// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export const ContextMenu: React.FC<ContextMenuProps> = ({
  items,
  position,
  onClose,
  header,
  "aria-label": ariaLabel = "Context menu",
}) => {
  const menuRef = useRef<HTMLDivElement>(null);
  const visibleItems = items.filter((item) => item.visible !== false);
  const [focusedIndex, setFocusedIndex] = useState(
    visibleItems.length > 0 ? 0 : -1
  );
  const [boundedPosition, setBoundedPosition] = useState({
    left: position.x,
    top: position.y,
  });

  // Reset focused index if visible items change while the menu is open
  useEffect(() => {
    setFocusedIndex(visibleItems.length > 0 ? 0 : -1);
  }, [visibleItems.length]);

  // Measure actual menu dimensions after mount and adjust position
  useLayoutEffect(() => {
    const menu = menuRef.current;
    if (!menu) return;

    let x = position.x;
    let y = position.y;
    const menuWidth = menu.offsetWidth;
    const menuHeight = menu.offsetHeight;

    if (x + menuWidth > window.innerWidth - VIEWPORT_PADDING) {
      x = window.innerWidth - menuWidth - VIEWPORT_PADDING;
    }
    if (y + menuHeight > window.innerHeight - VIEWPORT_PADDING) {
      y = window.innerHeight - menuHeight - VIEWPORT_PADDING;
    }
    if (x < VIEWPORT_PADDING) x = VIEWPORT_PADDING;
    if (y < VIEWPORT_PADDING) y = VIEWPORT_PADDING;

    setBoundedPosition({ left: x, top: y });
  }, [position.x, position.y]);

  // Focus first item on mount
  useEffect(() => {
    const timer = setTimeout(() => {
      const firstItem = menuRef.current?.querySelector(
        '[role="menuitem"]'
      ) as HTMLElement;
      firstItem?.focus();
    }, 0);
    return () => clearTimeout(timer);
  }, []);

  // Keyboard navigation with roving tabindex
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape" || e.key === "Tab") {
      e.preventDefault();
      onClose();
      return;
    }

    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const menuItems = menuRef.current?.querySelectorAll('[role="menuitem"]');
      if (!menuItems?.length) return;

      let nextIndex: number;
      if (e.key === "ArrowDown") {
        nextIndex = focusedIndex < menuItems.length - 1 ? focusedIndex + 1 : 0;
      } else {
        nextIndex = focusedIndex > 0 ? focusedIndex - 1 : menuItems.length - 1;
      }
      setFocusedIndex(nextIndex);
      (menuItems[nextIndex] as HTMLElement).focus();
    }
  };

  return (
    <>
      <MenuOverlay onClick={onClose} aria-hidden="true" />
      <MenuContainer
        ref={menuRef}
        role="menu"
        aria-label={ariaLabel}
        style={{ left: boundedPosition.left, top: boundedPosition.top }}
        onKeyDown={handleKeyDown}
      >
        {header && <MenuHeader title={header}>{header}</MenuHeader>}
        {visibleItems.map((item, index) => (
          <MenuItemStyled
            key={item.key}
            type="button"
            role="menuitem"
            tabIndex={index === focusedIndex ? 0 : -1}
            $variant={item.variant}
            onClick={(e) => {
              item.onClick(e);
            }}
            onFocus={() => setFocusedIndex(index)}
          >
            {item.icon}
            {item.label}
          </MenuItemStyled>
        ))}
      </MenuContainer>
    </>
  );
};

export default ContextMenu;
