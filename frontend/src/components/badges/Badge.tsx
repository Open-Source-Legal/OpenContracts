import React, { useState, useRef, useEffect } from "react";
import { Label } from "semantic-ui-react";
import * as LucideIcons from "lucide-react";
import styled from "styled-components";
import { computePosition, flip, shift, offset, arrow } from "@floating-ui/dom";

const StyledBadge = styled(Label)<{ $badgeColor: string }>`
  &.ui.label {
    display: inline-flex !important;
    align-items: center;
    gap: 0.4em;
    padding: 0.4em 0.75em;
    border-radius: 20px;
    font-weight: 600;
    font-size: 0.85em;
    background: ${(props) => props.$badgeColor} !important;
    color: #ffffff !important;
    border: 2px solid rgba(255, 255, 255, 0.3);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    transition: all 0.2s ease;
    cursor: default;

    &:hover {
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    }
  }
`;

const PopupContainer = styled.div<{ $show: boolean }>`
  position: absolute;
  z-index: 10000;
  background: white;
  padding: 1em;
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  border: 1px solid #e2e8f0;
  opacity: ${(props) => (props.$show ? 1 : 0)};
  pointer-events: ${(props) => (props.$show ? "auto" : "none")};
  transition: opacity 0.2s ease;
`;

const BadgeContent = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.5em;
  max-width: 250px;
`;

const BadgeTitle = styled.div`
  font-weight: 700;
  font-size: 1.1em;
  color: #1e293b;
`;

const BadgeDescription = styled.div`
  font-size: 0.9em;
  color: #64748b;
  line-height: 1.4;
`;

const BadgeMetadata = styled.div`
  font-size: 0.8em;
  color: #94a3b8;
  margin-top: 0.3em;
  border-top: 1px solid #e2e8f0;
  padding-top: 0.5em;
`;

export interface BadgeData {
  id: string;
  name: string;
  description: string;
  icon: string;
  color: string;
  badgeType?: string;
  isAutoAwarded?: boolean;
  awardedAt?: string;
  awardedBy?: {
    username: string;
  };
  corpus?: {
    title: string;
  };
}

interface BadgeProps {
  badge: BadgeData;
  size?: "mini" | "tiny" | "small" | "medium" | "large";
  showTooltip?: boolean;
}

export const Badge: React.FC<BadgeProps> = ({
  badge,
  size = "small",
  showTooltip = true,
}) => {
  const [showPopup, setShowPopup] = useState(false);
  const badgeRef = useRef<HTMLDivElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);

  // Dynamically get the icon component from lucide-react
  const IconComponent = (LucideIcons[badge.icon as keyof typeof LucideIcons] ||
    LucideIcons.Award) as React.ComponentType<{ size: number }>;

  // Update popup position using floating-ui
  const updatePosition = async () => {
    if (!badgeRef.current || !popupRef.current) return;

    const { x, y } = await computePosition(badgeRef.current, popupRef.current, {
      placement: "top",
      middleware: [offset(8), flip(), shift({ padding: 8 })],
    });

    Object.assign(popupRef.current.style, {
      left: `${x}px`,
      top: `${y}px`,
    });
  };

  // Update position when popup shows
  useEffect(() => {
    if (showPopup) {
      updatePosition();
    }
  }, [showPopup]);

  const handleMouseEnter = () => {
    setShowPopup(true);
  };

  const handleMouseLeave = () => {
    setShowPopup(false);
  };

  const badgeElement = (
    <div
      ref={badgeRef}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      style={{ display: "inline-block" }}
    >
      <StyledBadge $badgeColor={badge.color || "#05313d"} size={size}>
        <IconComponent size={size === "mini" ? 12 : 14} />
        {badge.name}
      </StyledBadge>
    </div>
  );

  if (!showTooltip) {
    return (
      <StyledBadge $badgeColor={badge.color || "#05313d"} size={size}>
        <IconComponent size={size === "mini" ? 12 : 14} />
        {badge.name}
      </StyledBadge>
    );
  }

  return (
    <>
      {badgeElement}
      <PopupContainer
        ref={popupRef}
        $show={showPopup}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        <BadgeContent>
          <BadgeTitle>{badge.name}</BadgeTitle>
          <BadgeDescription>{badge.description}</BadgeDescription>
          <BadgeMetadata>
            {badge.badgeType === "CORPUS" && badge.corpus && (
              <div>Corpus: {badge.corpus.title}</div>
            )}
            {badge.badgeType === "GLOBAL" && <div>Global Badge</div>}
            {badge.isAutoAwarded && <div>Auto-awarded</div>}
            {badge.awardedAt && (
              <div>
                Awarded: {new Date(badge.awardedAt).toLocaleDateString()}
              </div>
            )}
            {badge.awardedBy && <div>By: {badge.awardedBy.username}</div>}
          </BadgeMetadata>
        </BadgeContent>
      </PopupContainer>
    </>
  );
};
