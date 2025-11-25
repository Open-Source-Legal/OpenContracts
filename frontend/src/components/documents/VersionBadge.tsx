import React from "react";
import styled from "styled-components";
import { Popup } from "semantic-ui-react";

// Badge container with conditional styling based on version state
const BadgeContainer = styled.div<{
  $hasHistory: boolean;
  $isOutdated: boolean;
}>`
  position: absolute;
  top: 8px;
  right: 8px;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 12px;
  cursor: ${(props) => (props.$hasHistory ? "pointer" : "default")};
  user-select: none;
  z-index: 10;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  backdrop-filter: blur(4px);

  /* Base state - no history */
  background: ${(props) => {
    if (props.$isOutdated) {
      return "rgba(249, 115, 22, 0.15)";
    } else if (props.$hasHistory) {
      return "rgba(59, 130, 246, 0.15)";
    } else {
      return "rgba(100, 116, 139, 0.1)";
    }
  }};

  color: ${(props) => {
    if (props.$isOutdated) {
      return "#c2410c";
    } else if (props.$hasHistory) {
      return "#1d4ed8";
    } else {
      return "#64748b";
    }
  }};

  border: 1px solid
    ${(props) => {
      if (props.$isOutdated) {
        return "rgba(249, 115, 22, 0.3)";
      } else if (props.$hasHistory) {
        return "rgba(59, 130, 246, 0.3)";
      } else {
        return "rgba(100, 116, 139, 0.2)";
      }
    }};

  &:hover {
    ${(props) =>
      props.$hasHistory &&
      `
      transform: scale(1.05);
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
      background: ${
        props.$isOutdated
          ? "rgba(249, 115, 22, 0.25)"
          : "rgba(59, 130, 246, 0.25)"
      };
    `}
  }

  &:active {
    ${(props) =>
      props.$hasHistory &&
      `
      transform: scale(0.98);
    `}
  }
`;

const VersionText = styled.span`
  letter-spacing: 0.3px;
`;

const HistoryIndicator = styled.span`
  margin-left: 4px;
  font-size: 9px;
  opacity: 0.8;
`;

const TooltipContent = styled.div`
  font-size: 12px;
  line-height: 1.4;

  .tooltip-title {
    font-weight: 600;
    margin-bottom: 4px;
    color: #0f172a;
  }

  .tooltip-info {
    color: #475569;
    margin-bottom: 2px;
  }

  .tooltip-action {
    margin-top: 6px;
    font-style: italic;
    color: #3b82f6;
    font-size: 11px;
  }
`;

export interface VersionBadgeProps {
  versionNumber: number;
  hasHistory: boolean;
  isLatest: boolean;
  versionCount?: number;
  onClick?: () => void;
  className?: string;
}

/**
 * Version Badge Component
 *
 * Displays version information on document cards with visual states:
 * - Gray: No version history (v1 only)
 * - Blue: Has history and is latest version
 * - Orange: Has history but is NOT the latest version
 *
 * Clicking the badge (when hasHistory=true) opens the version history panel.
 */
export const VersionBadge: React.FC<VersionBadgeProps> = ({
  versionNumber,
  hasHistory,
  isLatest,
  versionCount = 1,
  onClick,
  className,
}) => {
  const isOutdated = hasHistory && !isLatest;

  const handleClick = (e: React.MouseEvent) => {
    if (hasHistory && onClick) {
      e.stopPropagation();
      onClick();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (hasHistory && onClick && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      e.stopPropagation();
      onClick();
    }
  };

  const tooltipContent = (
    <TooltipContent>
      <div className="tooltip-title">
        {isOutdated ? "Outdated Version" : "Version Information"}
      </div>
      <div className="tooltip-info">Current: v{versionNumber}</div>
      {hasHistory && (
        <div className="tooltip-info">Total versions: {versionCount}</div>
      )}
      {isOutdated && (
        <div className="tooltip-info">
          A newer version is available (you are viewing v{versionNumber} of{" "}
          {versionCount})
        </div>
      )}
      {hasHistory && (
        <div className="tooltip-action">Click to view version history</div>
      )}
    </TooltipContent>
  );

  const badge = (
    <BadgeContainer
      $hasHistory={hasHistory}
      $isOutdated={isOutdated}
      onClick={handleClick}
      className={className}
      role={hasHistory ? "button" : undefined}
      aria-label={`Version ${versionNumber}${
        hasHistory ? `, click to view history` : ""
      }`}
      tabIndex={hasHistory ? 0 : undefined}
      onKeyDown={hasHistory ? handleKeyDown : undefined}
    >
      <VersionText>v{versionNumber}</VersionText>
      {hasHistory && (
        <HistoryIndicator>&#8226; {versionCount}</HistoryIndicator>
      )}
    </BadgeContainer>
  );

  // Wrap in tooltip if there's useful information to show
  if (hasHistory || versionNumber > 1) {
    return (
      <Popup
        trigger={badge}
        content={tooltipContent}
        position="bottom right"
        size="small"
        inverted={false}
        style={{
          padding: "10px 12px",
          borderRadius: "8px",
          boxShadow: "0 4px 12px rgba(0, 0, 0, 0.15)",
        }}
      />
    );
  }

  return badge;
};

export default VersionBadge;
