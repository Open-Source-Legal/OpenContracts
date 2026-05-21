import React from "react";
import styled from "styled-components";
import { List, Search, Maximize2 } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../../../../assets/configurations/osLegalStyles";

export interface MobileDocToolbarProps {
  zoomPercent: number;
  onSections: () => void;
  onFind: () => void;
  onFitWidth: () => void;
}

const Bar = styled.div`
  flex-shrink: 0;
  height: 36px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 8px;
  background: ${OS_LEGAL_COLORS.background};
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
`;

const Chip = styled.button`
  height: 24px;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 0 10px;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  background: white;
  font-size: 11px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
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
      <List size={13} /> Sections
    </Chip>
    <Chip aria-label="Find" onClick={onFind}>
      <Search size={13} /> Find
    </Chip>
    <Spacer />
    <Chip aria-label="Fit width" onClick={onFitWidth}>
      <Maximize2 size={13} /> {Math.round(zoomPercent)}%
    </Chip>
  </Bar>
);
