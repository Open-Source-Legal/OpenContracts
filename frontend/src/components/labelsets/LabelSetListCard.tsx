import React from "react";
import styled from "styled-components";
import { useNavigate } from "react-router-dom";
import { CollectionCard } from "@os-legal/ui";
import { Edit as EditIcon, Eye, Copy, Trash2 } from "lucide-react";
import { LabelSetType } from "../../types/graphql-api";
import {
  ContextMenu,
  ContextMenuItem,
} from "../widgets/context-menu/ContextMenu";
import { getLabelsetUrl } from "../../utils/navigationUtils";
import { getPermissions } from "../../utils/transform";
import { isOwnedBy } from "../../utils/userDisplay";
import { PermissionTypes } from "../types";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";

// ═══════════════════════════════════════════════════════════════════════════════
// STYLED COMPONENTS
// ═══════════════════════════════════════════════════════════════════════════════

const CardWrapper = styled.div`
  position: relative;
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

// ═══════════════════════════════════════════════════════════════════════════════
// ICONS
// ═══════════════════════════════════════════════════════════════════════════════

const KebabIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16">
    <circle cx="8" cy="3" r="1.5" fill="currentColor" />
    <circle cx="8" cy="8" r="1.5" fill="currentColor" />
    <circle cx="8" cy="13" r="1.5" fill="currentColor" />
  </svg>
);

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

function getVisibilityStatus(
  labelset: LabelSetType,
  currentUserId?: string
): string {
  const isOwner = isOwnedBy(labelset.creator, { id: currentUserId });
  if (labelset.isPublic) return "Public";
  if (isOwner) return "Private";
  return "Shared";
}

function formatStats(labelset: LabelSetType): string[] {
  const stats: string[] = [];

  // Total labels count
  const totalLabels =
    (labelset.docLabelCount || 0) +
    (labelset.spanLabelCount || 0) +
    (labelset.tokenLabelCount || 0);
  stats.push(`${totalLabels} ${totalLabels === 1 ? "label" : "labels"}`);

  // Corpus uses
  const corpusCount = labelset.corpusCount || 0;
  if (corpusCount > 0) {
    stats.push(
      `Used in ${corpusCount} ${corpusCount === 1 ? "corpus" : "corpuses"}`
    );
  }

  // Breakdown by type if there are labels
  if (totalLabels > 0) {
    const breakdown: string[] = [];
    if (labelset.tokenLabelCount && labelset.tokenLabelCount > 0) {
      breakdown.push(`${labelset.tokenLabelCount} text`);
    }
    if (labelset.docLabelCount && labelset.docLabelCount > 0) {
      breakdown.push(`${labelset.docLabelCount} doc`);
    }
    if (labelset.spanLabelCount && labelset.spanLabelCount > 0) {
      breakdown.push(`${labelset.spanLabelCount} span`);
    }
    if (breakdown.length > 0) {
      stats.push(breakdown.join(", "));
    }
  }

  return stats;
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

interface LabelSetListCardProps {
  labelset: LabelSetType;
  currentUserId?: string;
  onEdit?: (labelset: LabelSetType) => void;
  onView?: (labelset: LabelSetType) => void;
  onDelete?: (labelset: LabelSetType) => void;
  onDuplicate?: (labelset: LabelSetType) => void;
  isMenuOpen?: boolean;
  menuPosition?: { x: number; y: number } | null;
  onOpenMenu?: (e: React.MouseEvent, labelsetId: string) => void;
  onCloseMenu?: () => void;
}

export const LabelSetListCard: React.FC<LabelSetListCardProps> = ({
  labelset,
  currentUserId,
  onEdit,
  onView,
  onDelete,
  onDuplicate,
  isMenuOpen,
  menuPosition,
  onOpenMenu,
  onCloseMenu,
}) => {
  const navigate = useNavigate();

  const handleClick = () => {
    // Don't navigate if menu is open
    if (isMenuOpen) return;

    const url = getLabelsetUrl(labelset);
    if (url !== "#") {
      navigate(url);
    }
  };

  const handleContextMenu = (e: React.MouseEvent) => {
    if (onOpenMenu) {
      e.preventDefault();
      e.stopPropagation();
      onOpenMenu(e, labelset.id);
    }
  };

  const handleMenuButtonClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onOpenMenu) {
      onOpenMenu(e, labelset.id);
    }
  };

  const visibilityStatus = getVisibilityStatus(labelset, currentUserId);
  const stats = formatStats(labelset);
  const permissions = getPermissions(labelset.myPermissions || []);
  const canUpdate = permissions.includes(PermissionTypes.CAN_UPDATE);
  const canRemove = permissions.includes(PermissionTypes.CAN_REMOVE);

  return (
    <>
      <CardWrapper onContextMenu={handleContextMenu}>
        <CollectionCard
          type="default"
          image={labelset.icon || undefined}
          imageAlt={labelset.title || "Label set icon"}
          status={visibilityStatus}
          title={labelset.title || "Untitled Label Set"}
          description={labelset.description || "No description"}
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
          aria-label="Label set actions"
          items={
            [
              {
                key: "edit",
                icon: <EditIcon size={16} />,
                label: "Edit",
                visible: canUpdate && Boolean(onEdit),
                onClick: () => {
                  onEdit?.(labelset);
                  onCloseMenu?.();
                },
              },
              {
                key: "view",
                icon: <Eye size={16} />,
                label: "View Details",
                visible: Boolean(onView),
                onClick: () => {
                  onView?.(labelset);
                  onCloseMenu?.();
                },
              },
              {
                key: "duplicate",
                icon: <Copy size={16} />,
                label: "Duplicate",
                visible: Boolean(onDuplicate),
                onClick: () => {
                  onDuplicate?.(labelset);
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
                  onDelete?.(labelset);
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

export default LabelSetListCard;
