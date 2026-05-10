import React, { useCallback } from "react";
import styled from "styled-components";
import { useNavigate } from "react-router-dom";
import { CollectionCard } from "@os-legal/ui";
import { Eye, Trash2 } from "lucide-react";
import { ExtractType } from "../../types/graphql-api";
import { getPermissions } from "../../utils/transform";
import { PermissionTypes } from "../types";
import { getExtractStatus, formatExtractDate } from "../../utils/extractUtils";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import {
  ContextMenu,
  ContextMenuItem,
} from "../widgets/context-menu/ContextMenu";

// Styled Components

const CardWrapper = styled.div<{ $isSelected?: boolean }>`
  position: relative;
  border-radius: 12px;
  transition: all 0.15s ease;

  ${(props) =>
    props.$isSelected &&
    `
    box-shadow: 0 0 0 2px ${OS_LEGAL_COLORS.accent};
    background: #f0fdfa;
  `}
`;

const MenuButton = styled.button`
  && {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    background: transparent;
    border: none;
    border-radius: 6px;
    color: ${OS_LEGAL_COLORS.textSecondary};
    cursor: pointer;
    transition: all 0.15s;

    &:hover {
      background: ${OS_LEGAL_COLORS.surfaceLight};
      color: #334155;
    }
  }
`;

// Icons

const KebabIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16">
    <circle cx="8" cy="3" r="1.5" fill="currentColor" />
    <circle cx="8" cy="8" r="1.5" fill="currentColor" />
    <circle cx="8" cy="13" r="1.5" fill="currentColor" />
  </svg>
);

// Helper Functions

function formatStats(extract: ExtractType): string[] {
  const stats: string[] = [];

  // Document count (use fullDocumentList from GraphQL query)
  const docCount = extract.fullDocumentList?.length || 0;
  stats.push(`${docCount} ${docCount === 1 ? "document" : "documents"}`);

  // Column count (from fieldset's fullColumnList)
  const columnCount = extract.fieldset?.fullColumnList?.length || 0;
  if (columnCount > 0) {
    stats.push(`${columnCount} ${columnCount === 1 ? "column" : "columns"}`);
  }

  // Corpus name if available
  if (extract.corpus?.title) {
    stats.push(`from ${extract.corpus.title}`);
  }

  return stats;
}

// Main Component

interface ExtractListCardProps {
  extract: ExtractType;
  onView?: (extract: ExtractType) => void;
  onDelete?: (extract: ExtractType) => void;
  isMenuOpen?: boolean;
  menuPosition?: { x: number; y: number } | null;
  onOpenMenu?: (e: React.MouseEvent, extractId: string) => void;
  onCloseMenu?: () => void;
  /** Whether the card is currently selected (for inline selection mode) */
  isSelected?: boolean;
}

export const ExtractListCard: React.FC<ExtractListCardProps> = ({
  extract,
  onView,
  onDelete,
  isMenuOpen,
  menuPosition,
  onOpenMenu,
  onCloseMenu,
  isSelected = false,
}) => {
  const navigate = useNavigate();

  const handleClick = () => {
    // Don't navigate if menu is open
    if (isMenuOpen) return;

    // Use callback if provided, otherwise navigate directly
    if (onView) {
      onView(extract);
    } else {
      navigate(`/extracts/${extract.id}`);
    }
  };

  const handleContextMenu = (e: React.MouseEvent) => {
    if (onOpenMenu) {
      e.preventDefault();
      e.stopPropagation();
      onOpenMenu(e, extract.id);
    }
  };

  const handleMenuButtonClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onOpenMenu) {
      onOpenMenu(e, extract.id);
    }
  };

  // Handle keyboard shortcut (Shift+F10) for context menu
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.shiftKey && e.key === "F10" && onOpenMenu) {
        e.preventDefault();
        // Open menu at card center
        const rect = e.currentTarget.getBoundingClientRect();
        const syntheticEvent = {
          clientX: rect.left + rect.width / 2,
          clientY: rect.top + rect.height / 2,
          preventDefault: () => {},
          stopPropagation: () => {},
        } as React.MouseEvent;
        onOpenMenu(syntheticEvent, extract.id);
      }
    },
    [extract.id, onOpenMenu]
  );

  const statusLabel = getExtractStatus(extract).label;
  const stats = formatStats(extract);
  const permissions = getPermissions(extract.myPermissions || []);
  const canRemove = permissions.includes(PermissionTypes.CAN_REMOVE);

  // Add creation date to description
  const description = extract.created
    ? `Created ${formatExtractDate(extract.created)}`
    : "No description";

  return (
    <>
      <CardWrapper
        $isSelected={isSelected}
        onContextMenu={handleContextMenu}
        onKeyDown={handleKeyDown}
        tabIndex={0}
        role="article"
        aria-label={`Extract: ${extract.name || "Untitled Extract"}`}
      >
        <CollectionCard
          type="default"
          status={statusLabel}
          title={extract.name || "Untitled Extract"}
          description={description}
          stats={stats}
          onClick={handleClick}
          menu={
            <MenuButton
              type="button"
              className="oc-collection-card__menu-button"
              aria-label="Open menu"
              aria-haspopup="menu"
              aria-expanded={isMenuOpen}
              onClick={handleMenuButtonClick}
            >
              <KebabIcon />
            </MenuButton>
          }
        />
      </CardWrapper>

      {/* Floating Context Menu */}
      {isMenuOpen && menuPosition && (
        <ContextMenu
          position={menuPosition}
          onClose={onCloseMenu ?? (() => {})}
          aria-label="Extract actions"
          items={
            [
              {
                key: "view",
                icon: <Eye size={16} />,
                label: "View Details",
                visible: Boolean(onView),
                onClick: () => {
                  onView?.(extract);
                  onCloseMenu?.();
                },
              },
              {
                key: "delete",
                icon: <Trash2 size={16} />,
                label: "Delete",
                variant: "danger" as const,
                visible: canRemove && Boolean(onDelete),
                onClick: () => {
                  onDelete?.(extract);
                  onCloseMenu?.();
                },
              },
            ] satisfies ContextMenuItem[]
          }
        />
      )}
    </>
  );
};

export default ExtractListCard;
