import React, { useEffect, useRef } from "react";
import styled, { keyframes } from "styled-components";
import {
  BookOpen,
  Eye,
  Loader2,
  Download,
  Pencil,
  Link,
  GitBranch,
  Trash2,
  CheckSquare,
  Square,
  LucideIcon,
} from "lucide-react";

// Mapping from semantic-ui icon names to lucide-react components
const iconMap: Record<string, LucideIcon> = {
  book: BookOpen,
  eye: Eye,
  spinner: Loader2,
  download: Download,
  edit: Pencil,
  linkify: Link,
  "code branch": GitBranch,
  trash: Trash2,
  "check square outline": CheckSquare,
  "square outline": Square,
};

const slideIn = keyframes`
  from {
    opacity: 0;
    transform: scale(0.95) translateY(-8px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
`;

const MenuContainer = styled.div<{ x: number; y: number }>`
  position: fixed;
  left: ${(props) => props.x}px;
  top: ${(props) => props.y}px;
  z-index: 10000;
  min-width: 200px;
  max-width: calc(100vw - 16px);
  background: white;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15), 0 0 0 1px rgba(0, 0, 0, 0.05);
  padding: 4px;
  animation: ${slideIn} 0.15s ease-out;
  overflow: hidden;

  @media (max-width: 768px) {
    min-width: 180px;
    max-width: calc(100vw - 16px);
  }
`;

const MenuItem = styled.button<{ variant?: "danger" | "primary" }>`
  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s ease;
  font-size: 0.875rem;
  color: ${(props) =>
    props.variant === "danger"
      ? "#ef4444"
      : props.variant === "primary"
      ? "#3b82f6"
      : "#0f172a"};
  font-weight: 500;
  text-align: left;

  &:hover {
    background: ${(props) =>
      props.variant === "danger"
        ? "#fee2e2"
        : props.variant === "primary"
        ? "#eff6ff"
        : "#f8fafc"};
  }

  &:active {
    transform: scale(0.98);
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .icon {
    width: 16px;
    height: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0 !important;
    flex-shrink: 0;
    opacity: 0.8;
  }
`;

const MenuDivider = styled.div`
  height: 1px;
  background: #e2e8f0;
  margin: 4px 8px;
`;

const MenuLabel = styled.div`
  padding: 6px 12px;
  font-size: 0.75rem;
  font-weight: 600;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

export interface ContextMenuItem {
  label: string;
  icon: string;
  onClick: (e: React.MouseEvent) => void;
  variant?: "danger" | "primary";
  disabled?: boolean;
  dividerAfter?: boolean;
}

interface ModernContextMenuProps {
  x: number;
  y: number;
  items: ContextMenuItem[];
  onClose: () => void;
  title?: string;
}

export const ModernContextMenu: React.FC<ModernContextMenuProps> = ({
  x,
  y,
  items,
  onClose,
  title,
}) => {
  const menuRef = useRef<HTMLDivElement>(null);

  // Adjust position if menu would go off screen
  useEffect(() => {
    if (menuRef.current) {
      const rect = menuRef.current.getBoundingClientRect();
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;
      const margin = 8;

      let adjustedX = x;
      let adjustedY = y;

      // Adjust horizontal position - check both left and right edges
      if (rect.right > viewportWidth - margin) {
        adjustedX = viewportWidth - rect.width - margin;
      }
      if (adjustedX < margin) {
        adjustedX = margin;
      }

      // Adjust vertical position - check both top and bottom edges
      if (rect.bottom > viewportHeight - margin) {
        adjustedY = viewportHeight - rect.height - margin;
      }
      if (adjustedY < margin) {
        adjustedY = margin;
      }

      if (adjustedX !== x || adjustedY !== y) {
        menuRef.current.style.left = `${adjustedX}px`;
        menuRef.current.style.top = `${adjustedY}px`;
      }
    }
  }, [x, y]);

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };

    // Small delay to prevent immediate close from the same click that opened it
    setTimeout(() => {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("keydown", handleEscape);
    }, 100);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [onClose]);

  return (
    <MenuContainer ref={menuRef} x={x} y={y}>
      {title && <MenuLabel>{title}</MenuLabel>}
      {items.map((item, index) => (
        <React.Fragment key={index}>
          <MenuItem
            variant={item.variant}
            onClick={(e) => {
              if (!item.disabled) {
                item.onClick(e);
                onClose();
              }
            }}
            disabled={item.disabled}
          >
            {(() => {
              const IconComponent = iconMap[item.icon];
              return IconComponent ? (
                <IconComponent size={16} className="icon" />
              ) : null;
            })()}
            {item.label}
          </MenuItem>
          {item.dividerAfter && <MenuDivider />}
        </React.Fragment>
      ))}
    </MenuContainer>
  );
};
