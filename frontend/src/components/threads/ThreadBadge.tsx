import React from "react";
import styled from "styled-components";
import { Pin, Lock, Trash2 } from "lucide-react";
import { color } from "../../theme/colors";

interface ThreadBadgeProps {
  type: "pinned" | "locked" | "deleted";
  compact?: boolean;
}

const BadgeContainer = styled.span<{ $type: string }>`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;

  ${(props) => {
    switch (props.$type) {
      case "pinned":
        return `
          background: ${color.B2};
          color: ${color.B8};
        `;
      case "locked":
        return `
          background: ${color.R2};
          color: ${color.R8};
        `;
      case "deleted":
        return `
          background: ${color.N4};
          color: ${color.N7};
        `;
      default:
        return "";
    }
  }}
`;

/**
 * Visual indicator badge for thread states
 */
export function ThreadBadge({ type, compact = false }: ThreadBadgeProps) {
  const icons = {
    pinned: <Pin size={14} />,
    locked: <Lock size={14} />,
    deleted: <Trash2 size={14} />,
  };

  const labels = {
    pinned: "Pinned",
    locked: "Locked",
    deleted: "Deleted",
  };

  return (
    <BadgeContainer $type={type}>
      {icons[type]}
      {!compact && <span>{labels[type]}</span>}
    </BadgeContainer>
  );
}
