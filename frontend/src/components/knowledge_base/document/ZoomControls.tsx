import React from "react";
import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import { ZOOM_MIN, ZOOM_MAX } from "../../../assets/configurations/constants";
import { ZoomIn, ZoomOut } from "lucide-react";

interface ZoomControlsProps {
  onZoomIn: () => void;
  onZoomOut: () => void;
  zoomLevel: number;
  className?: string;
}

const StyledZoomControls = styled.div`
  position: absolute;
  top: 1.5rem;
  right: 1.5rem;
  z-index: 900;

  @media (max-width: 768px) {
    position: absolute; /* Stay within document container */
    top: 1rem;
    right: 1rem;
  }

  .zoom-group {
    display: flex;
    align-items: center;
    background: rgba(255, 255, 255, 0.98);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(200, 200, 200, 0.8);
    border-radius: 12px;
    padding: 0.5rem;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.04);

    .zoom-controls {
      display: flex;
      gap: 0.5rem;
      align-items: center;

      button {
        width: 36px;
        height: 36px;
        border-radius: 8px;
        border: none;
        background: transparent;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        color: ${OS_LEGAL_COLORS.textTertiary};
        transition: all 0.2s ease;

        &:hover {
          background: rgba(0, 0, 0, 0.04);
          color: ${OS_LEGAL_COLORS.primaryBlue};
        }

        &:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        svg {
          width: 18px;
          height: 18px;
          stroke-width: 2.2;
        }
      }
    }

    .zoom-level {
      min-width: 48px;
      text-align: center;
      font-size: 0.875rem;
      color: ${OS_LEGAL_COLORS.textTertiary};
      font-weight: 500;
      padding: 0 0.5rem;
    }
  }
`;

export const ZoomControls: React.FC<ZoomControlsProps> = ({
  onZoomIn,
  onZoomOut,
  zoomLevel,
  className,
}) => {
  return (
    <StyledZoomControls className={className}>
      <div className="zoom-group">
        <div className="zoom-controls">
          <button
            onClick={onZoomOut}
            title="Zoom Out"
            disabled={zoomLevel <= ZOOM_MIN}
          >
            <ZoomOut />
          </button>
          <div className="zoom-level">{Math.round(zoomLevel * 100)}%</div>
          <button
            onClick={onZoomIn}
            title="Zoom In"
            disabled={zoomLevel >= ZOOM_MAX}
          >
            <ZoomIn />
          </button>
        </div>
      </div>
    </StyledZoomControls>
  );
};

export default ZoomControls;
