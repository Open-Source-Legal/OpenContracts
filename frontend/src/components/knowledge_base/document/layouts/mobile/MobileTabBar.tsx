import React from "react";
import styled from "styled-components";
import { FileText, BookOpen, Bookmark, MoreHorizontal } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../../../../assets/configurations/osLegalStyles";

export type MobileTabId = "document" | "summary" | "annotations" | "more";

export interface MobileTabBarProps {
  active: MobileTabId;
  onSelect: (id: MobileTabId) => void;
}

const TABS: { id: MobileTabId; label: string; Icon: React.FC<any> }[] = [
  { id: "document", label: "Document", Icon: FileText },
  { id: "summary", label: "Summary", Icon: BookOpen },
  { id: "annotations", label: "Annotations", Icon: Bookmark },
  { id: "more", label: "More", Icon: MoreHorizontal },
];

const Bar = styled.div`
  flex-shrink: 0;
  height: 56px;
  display: flex;
  background: white;
  border-top: 1px solid ${OS_LEGAL_COLORS.border};
`;

const Tab = styled.button<{ $active: boolean }>`
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 11px;
  font-weight: 500;
  color: ${(p) =>
    p.$active ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.textSecondary};
`;

export const MobileTabBar: React.FC<MobileTabBarProps> = ({
  active,
  onSelect,
}) => (
  <Bar role="tablist">
    {TABS.map(({ id, label, Icon }) => (
      <Tab
        key={id}
        role="tab"
        aria-selected={active === id}
        aria-label={label}
        $active={active === id}
        onClick={() => onSelect(id)}
      >
        <Icon size={20} />
        {label}
      </Tab>
    ))}
  </Bar>
);
