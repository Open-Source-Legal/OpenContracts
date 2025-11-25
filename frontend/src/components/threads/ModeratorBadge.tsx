import React from "react";
import styled from "styled-components";
import { Shield } from "lucide-react";
import { color } from "../../theme/colors";

const Badge = styled.span<{ $size?: "small" | "medium" }>`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: ${({ $size }) => ($size === "small" ? "2px 6px" : "4px 8px")};
  background: ${({ theme }) => color.B5}15;
  border: 1px solid ${({ theme }) => color.B5}40;
  border-radius: 4px;
  font-size: ${({ $size }) => ($size === "small" ? "11px" : "12px")};
  font-weight: 600;
  color: ${({ theme }) => color.B5};

  svg {
    width: ${({ $size }) => ($size === "small" ? "12px" : "14px")};
    height: ${({ $size }) => ($size === "small" ? "12px" : "14px")};
  }
`;

export interface ModeratorBadgeProps {
  /** Size variant */
  size?: "small" | "medium";
  /** Show icon */
  showIcon?: boolean;
  /** Custom label (default: "MOD") */
  label?: string;
}

export function ModeratorBadge({
  size = "small",
  showIcon = true,
  label = "MOD",
}: ModeratorBadgeProps) {
  return (
    <Badge $size={size} title="Moderator" aria-label="Moderator">
      {showIcon && <Shield />}
      <span>{label}</span>
    </Badge>
  );
}
