import React from "react";
import styled from "styled-components";
import { FileText, BookOpen, Bookmark, MoreHorizontal } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../../../../assets/configurations/osLegalStyles";
import { MOBILE_RADIUS, MOBILE_SHADOW } from "./mobileTheme";

export type MobileTabId = "document" | "summary" | "annotations" | "more";

export interface MobileTabBarProps {
  active: MobileTabId;
  onSelect: (id: MobileTabId) => void;
}

const TABS: { id: MobileTabId; label: string; Icon: LucideIcon }[] = [
  { id: "document", label: "Document", Icon: FileText },
  { id: "summary", label: "Summary", Icon: BookOpen },
  { id: "annotations", label: "Annotations", Icon: Bookmark },
  { id: "more", label: "More", Icon: MoreHorizontal },
];

/**
 * Bottom navigation chrome. Floats above the surface on a soft upward shadow
 * (no hard hairline border) and respects the device safe-area inset.
 */
const Bar = styled.div`
  flex-shrink: 0;
  display: flex;
  background: ${OS_LEGAL_COLORS.surface};
  box-shadow: ${MOBILE_SHADOW.chrome};
  padding: 6px 8px calc(6px + env(safe-area-inset-bottom));
`;

const Tab = styled.button<{ $active: boolean }>`
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 4px 0;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 11px;
  font-weight: ${(p) => (p.$active ? 600 : 500)};
  color: ${(p) =>
    p.$active ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.textSecondary};
  -webkit-tap-highlight-color: transparent;
  transition: color 0.16s ease;

  &:active {
    opacity: 0.7;
  }
`;

/** Soft accent-tinted pill that sits behind the active tab's icon. */
const IconWell = styled.span<{ $active: boolean }>`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 30px;
  border-radius: ${MOBILE_RADIUS.pill};
  background: ${(p) =>
    p.$active ? OS_LEGAL_COLORS.accentLight : "transparent"};
  transition: background 0.18s ease, transform 0.12s ease;

  ${Tab}:active & {
    transform: scale(0.94);
  }
`;

export const MobileTabBar: React.FC<MobileTabBarProps> = ({
  active,
  onSelect,
}) => (
  <Bar role="tablist">
    {TABS.map(({ id, label, Icon }) => {
      const isActive = active === id;
      return (
        <Tab
          key={id}
          role="tab"
          aria-selected={isActive}
          aria-label={label}
          $active={isActive}
          onClick={() => onSelect(id)}
        >
          <IconWell $active={isActive}>
            <Icon
              size={21}
              strokeWidth={isActive ? 2.4 : 2}
              fill={
                isActive && id !== "more" ? OS_LEGAL_COLORS.accentLight : "none"
              }
            />
          </IconWell>
          {label}
        </Tab>
      );
    })}
  </Bar>
);
