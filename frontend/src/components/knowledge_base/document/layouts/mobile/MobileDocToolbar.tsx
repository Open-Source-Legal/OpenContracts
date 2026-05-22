import React from "react";
import styled from "styled-components";
import { List, Search, Maximize2 } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../../../../assets/configurations/osLegalStyles";
import { MOBILE_RADIUS } from "./mobileTheme";

export interface MobileDocToolbarProps {
  zoomPercent: number;
  onSections: () => void;
  onFind: () => void;
  onFitWidth: () => void;
}

/**
 * Thin document toolbar. Sits flush on the warm surface tint with no hard
 * hairline — the chips themselves carry the visual weight.
 */
const Bar = styled.div`
  flex-shrink: 0;
  height: 44px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  background: transparent;
`;

/** Light "ghost" chip — soft slate-tinted, no harsh border. */
const Chip = styled.button`
  height: 30px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 12px;
  border: none;
  border-radius: ${MOBILE_RADIUS.pill};
  background: ${OS_LEGAL_COLORS.surfaceLight};
  font-size: 12px;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition: transform 0.12s ease, background 0.16s ease;

  & svg {
    color: ${OS_LEGAL_COLORS.textSecondary};
  }

  &:active {
    transform: scale(0.95);
    background: ${OS_LEGAL_COLORS.border};
  }
`;

const Spacer = styled.div`
  flex: 1;
`;

export const MobileDocToolbar: React.FC<MobileDocToolbarProps> = ({
  zoomPercent,
  onSections,
  onFind,
  onFitWidth,
}) => (
  <Bar>
    <Chip aria-label="Sections" onClick={onSections}>
      <List size={14} /> Sections
    </Chip>
    <Chip aria-label="Find" onClick={onFind}>
      <Search size={14} /> Find
    </Chip>
    <Spacer />
    <Chip aria-label="Fit width" onClick={onFitWidth}>
      <Maximize2 size={14} /> {Math.round(zoomPercent)}%
    </Chip>
  </Bar>
);
