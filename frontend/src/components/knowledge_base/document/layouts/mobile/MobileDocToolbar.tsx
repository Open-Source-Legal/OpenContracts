import React from "react";
import styled from "styled-components";
import { List, Search, Maximize2 } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../../../../assets/configurations/osLegalStyles";
import { MOBILE_RADIUS, MOBILE_SHADOW } from "./mobileTheme";

export interface MobileDocToolbarProps {
  zoomPercent: number;
  onSections: () => void;
  onFind: () => void;
  onFitWidth: () => void;
}

/**
 * Floating document controls.
 *
 * Previously a full-width band wedged between the header and the page — which
 * ate vertical space and read as wasteful. Now the controls float as a single
 * compact pill in the top-right corner of the viewer, so the document fills the
 * entire surface and the controls stay one tap away. The frosted pill carries
 * its own elevation, so it stays legible over either a PDF or a text page.
 */
const Cluster = styled.div`
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px;
  border-radius: ${MOBILE_RADIUS.pill};
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  box-shadow: ${MOBILE_SHADOW.raised};
`;

/** Icon-only ghost control inside the floating pill. */
const IconButton = styled.button`
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: ${MOBILE_RADIUS.pill};
  background: transparent;
  color: ${OS_LEGAL_COLORS.accent};
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition: transform 0.12s ease, background 0.16s ease;

  &:active {
    transform: scale(0.92);
    background: ${OS_LEGAL_COLORS.surfaceLight};
  }
`;

/** Fit-width control — keeps a compact live zoom readout alongside the icon. */
const ZoomButton = styled(IconButton)`
  width: auto;
  gap: 5px;
  padding: 0 12px;
  font-size: 12px;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textTertiary};

  & svg {
    color: ${OS_LEGAL_COLORS.accent};
  }
`;

const Divider = styled.span`
  width: 1px;
  height: 18px;
  margin: 0 2px;
  background: ${OS_LEGAL_COLORS.border};
`;

export const MobileDocToolbar: React.FC<MobileDocToolbarProps> = ({
  zoomPercent,
  onSections,
  onFind,
  onFitWidth,
}) => (
  <Cluster>
    <IconButton aria-label="Sections" onClick={onSections}>
      <List size={17} />
    </IconButton>
    <IconButton aria-label="Find" onClick={onFind}>
      <Search size={17} />
    </IconButton>
    <Divider aria-hidden="true" />
    <ZoomButton aria-label="Fit width" onClick={onFitWidth}>
      <Maximize2 size={15} /> {Math.round(zoomPercent)}%
    </ZoomButton>
  </Cluster>
);
