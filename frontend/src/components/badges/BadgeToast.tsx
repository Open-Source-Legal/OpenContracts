import React from "react";
import styled from "styled-components";
import * as LucideIcons from "lucide-react";
import { color } from "../../theme/colors";
import { spacing } from "../../theme/spacing";

const ToastContainer = styled.div`
  display: flex;
  align-items: center;
  gap: ${spacing.md};
  padding: ${spacing.sm};
  background: ${color.N1};
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  min-width: 300px;
`;

const BadgeIconContainer = styled.div<{ $color: string }>`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: ${(props) => props.$color};
  color: white;
  flex-shrink: 0;

  svg {
    width: 28px;
    height: 28px;
  }
`;

const ToastContent = styled.div`
  flex: 1;
  min-width: 0;
`;

const ToastTitle = styled.div`
  font-size: 14px;
  font-weight: 700;
  color: ${color.N10};
  margin-bottom: 2px;
`;

const ToastMessage = styled.div`
  font-size: 13px;
  color: ${color.N7};
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

export interface BadgeToastProps {
  badgeName: string;
  badgeIcon: string;
  badgeColor: string;
  isAutoAwarded: boolean;
  awardedBy?: {
    username: string;
  };
}

/**
 * Toast notification component for badge awards.
 * Displays a compact notification with badge icon, name, and awarding context.
 */
export function BadgeToast({
  badgeName,
  badgeIcon,
  badgeColor,
  isAutoAwarded,
  awardedBy,
}: BadgeToastProps) {
  // Get the icon component from lucide-react
  // Default to Award icon if the specified icon doesn't exist
  const IconComponent = (LucideIcons as any)[badgeIcon] || LucideIcons.Award;

  const message = isAutoAwarded
    ? `You earned the "${badgeName}" badge!`
    : `${
        awardedBy?.username || "Someone"
      } awarded you the "${badgeName}" badge!`;

  return (
    <ToastContainer>
      <BadgeIconContainer $color={badgeColor}>
        <IconComponent />
      </BadgeIconContainer>
      <ToastContent>
        <ToastTitle>Badge Earned!</ToastTitle>
        <ToastMessage>{message}</ToastMessage>
      </ToastContent>
    </ToastContainer>
  );
}
