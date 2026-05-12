import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router-dom";
import styled from "styled-components";
import { MoreHorizontal } from "lucide-react";
import {
  overflow_menu_links,
  type OverflowMenuLink,
} from "./overflowMenuItems";
import { VERSION_TAG } from "../../assets/configurations/constants";

/**
 * Desktop NavMenu overflow trigger. Renders a kebab button in the NavBar's
 * actions slot that opens a small dropdown of footer-essential links so they
 * stay reachable from any scroll position on infinite-scroll surfaces
 * (corpus Annotations / Analyses / Extracts). See issue #1609.
 *
 * The on-screen styling intentionally tracks the dark NavBar surface — the
 * trigger glyph is a low-opacity white, the dropdown is the standard white
 * surface card with rounded corners and a soft shadow, matching the
 * @os-legal/ui user-menu visual language.
 */

const FOCUSABLE_ITEM_SELECTOR = '[role="menuitem"]';

const Container = styled.div`
  position: relative;
  display: inline-flex;
  align-items: center;
`;

const TriggerButton = styled.button<{ $open: boolean }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  border: 1px solid
    ${(props) =>
      props.$open ? "rgba(255, 255, 255, 0.18)" : "rgba(255, 255, 255, 0.08)"};
  background: ${(props) =>
    props.$open ? "rgba(255, 255, 255, 0.12)" : "transparent"};
  color: rgba(255, 255, 255, 0.9);
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;

  &:hover {
    background: rgba(255, 255, 255, 0.1);
    border-color: rgba(255, 255, 255, 0.18);
  }

  &:focus-visible {
    outline: 2px solid #0f766e;
    outline-offset: 2px;
  }
`;

const Menu = styled.ul`
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 1200;
  min-width: 200px;
  margin: 0;
  padding: 6px;
  list-style: none;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  box-shadow: 0 10px 30px -12px rgba(15, 23, 42, 0.25),
    0 4px 12px -6px rgba(15, 23, 42, 0.1);
`;

const MenuItem = styled.li`
  margin: 0;
`;

const itemStyles = `
  display: block;
  width: 100%;
  padding: 8px 12px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #1e293b;
  font: inherit;
  font-size: 14px;
  font-weight: 500;
  line-height: 1.4;
  text-align: left;
  text-decoration: none;
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease;

  &:hover {
    background: #f8fafc;
    color: #0f766e;
    text-decoration: none;
  }

  &:focus-visible {
    outline: 2px solid #0f766e;
    outline-offset: -2px;
  }
`;

const ItemLink = styled(Link)`
  ${itemStyles}
`;

const ItemAnchor = styled.a`
  ${itemStyles}
`;

const MenuSeparator = styled.li`
  height: 1px;
  margin: 6px 4px;
  padding: 0;
  background: #e2e8f0;
  list-style: none;
`;

const VersionRow = styled.li`
  margin: 0;
  padding: 6px 12px 4px;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #94a3b8;
  list-style: none;
`;

interface NavOverflowMenuProps {
  links?: OverflowMenuLink[];
}

/**
 * Render a single link as a ``role="menuitem"`` — internal links use
 * react-router's ``Link``; external links use a plain anchor with
 * ``target="_blank"``.
 */
const renderLink = (
  link: OverflowMenuLink,
  onSelect: () => void
): JSX.Element => {
  if (link.to) {
    return (
      <ItemLink role="menuitem" to={link.to} onClick={onSelect}>
        {link.label}
      </ItemLink>
    );
  }
  return (
    <ItemAnchor
      role="menuitem"
      href={link.href}
      target="_blank"
      rel="noopener noreferrer"
      onClick={onSelect}
    >
      {link.label}
    </ItemAnchor>
  );
};

export const NavOverflowMenu: React.FC<NavOverflowMenuProps> = ({
  links = overflow_menu_links,
}) => {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLUListElement | null>(null);
  const menuId = useId();

  const close = useCallback(() => setOpen(false), []);

  // Close on outside click + ESC, manage arrow-key navigation inside menu.
  useEffect(() => {
    if (!open) return;

    const handlePointer = (event: MouseEvent) => {
      const node = containerRef.current;
      if (node && !node.contains(event.target as Node)) {
        close();
      }
    };

    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
        triggerRef.current?.focus();
        return;
      }

      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;

      const menu = menuRef.current;
      if (!menu) return;

      const items = Array.from(
        menu.querySelectorAll<HTMLElement>(FOCUSABLE_ITEM_SELECTOR)
      );
      if (items.length === 0) return;

      const active = document.activeElement as HTMLElement | null;
      const currentIndex = active ? items.indexOf(active) : -1;
      event.preventDefault();

      const delta = event.key === "ArrowDown" ? 1 : -1;
      const nextIndex =
        currentIndex === -1
          ? delta === 1
            ? 0
            : items.length - 1
          : (currentIndex + delta + items.length) % items.length;
      items[nextIndex]?.focus();
    };

    // Seed focus on the first item — APG menu pattern when activated by
    // keyboard. Mouse activation leaves the trigger focused which is fine.
    const focusTimer = window.setTimeout(() => {
      const menu = menuRef.current;
      if (!menu) return;
      const firstItem = menu.querySelector<HTMLElement>(
        FOCUSABLE_ITEM_SELECTOR
      );
      firstItem?.focus();
    }, 0);

    document.addEventListener("mousedown", handlePointer);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handlePointer);
      document.removeEventListener("keydown", handleKey);
      window.clearTimeout(focusTimer);
    };
  }, [open, close]);

  return (
    <Container ref={containerRef}>
      <TriggerButton
        ref={triggerRef}
        type="button"
        $open={open}
        aria-label="More links"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((prev) => !prev)}
      >
        <MoreHorizontal size={18} aria-hidden="true" />
      </TriggerButton>
      {open && (
        <Menu
          ref={menuRef}
          id={menuId}
          role="menu"
          aria-label="More site links"
        >
          {links.map((link) => (
            <MenuItem key={link.id}>{renderLink(link, close)}</MenuItem>
          ))}
          <MenuSeparator role="separator" aria-hidden="true" />
          <VersionRow aria-label={`Version ${VERSION_TAG}`}>
            {VERSION_TAG}
          </VersionRow>
        </Menu>
      )}
    </Container>
  );
};
