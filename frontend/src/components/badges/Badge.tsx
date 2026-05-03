import React, { useState, useRef, useEffect } from "react";
import * as LucideIcons from "lucide-react";
import styled from "styled-components";
import { computePosition, flip, shift, offset, arrow } from "@floating-ui/dom";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";

const StyledBadge = styled.span<{ $badgeColor: string }>`
  display: inline-flex;
  align-items: center;
  gap: 0.4em;
  padding: 0.4em 0.75em;
  border-radius: 20px;
  font-weight: 600;
  font-size: 0.85em;
  background: ${(props) => props.$badgeColor};
  color: #ffffff;
  border: 2px solid rgba(255, 255, 255, 0.3);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  transition: all 0.2s ease;
  cursor: default;
  max-width: 100%;
  overflow-wrap: anywhere;

  /* Touch-friendly tap target */
  @media (max-width: 768px) {
    padding: 0.5em 0.85em;
    min-height: 36px;
    cursor: pointer;
  }

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  }

  /* Disable hover transforms on touch devices */
  @media (hover: none) {
    &:hover {
      transform: none;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    }
  }
`;

const PopupContainer = styled.div<{ $show: boolean }>`
  position: absolute;
  z-index: 201;
  background: white;
  padding: 1em;
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  border: 1px solid ${OS_LEGAL_COLORS.border};
  opacity: ${(props) => (props.$show ? 1 : 0)};
  pointer-events: ${(props) => (props.$show ? "auto" : "none")};
  transition: opacity 0.2s ease;

  /* Mobile-responsive popup */
  @media (max-width: 768px) {
    position: fixed;
    left: 50% !important;
    top: 50% !important;
    transform: translate(-50%, -50%);
    width: calc(100vw - 2rem);
    max-width: 300px;
    padding: 1.25em;
  }
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
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const BadgeDescription = styled.div`
  font-size: 0.9em;
  color: ${OS_LEGAL_COLORS.textSecondary};
  line-height: 1.4;
`;

const BadgeMetadata = styled.div`
  font-size: 0.8em;
  color: ${OS_LEGAL_COLORS.textMuted};
  margin-top: 0.3em;
  border-top: 1px solid ${OS_LEGAL_COLORS.border};
  padding-top: 0.5em;
`;

const MobileOverlay = styled.div<{ $show: boolean }>`
  display: none;

  @media (max-width: 768px) {
    display: block;
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.3);
    z-index: 200;
    opacity: ${(props) => (props.$show ? 1 : 0)};
    pointer-events: ${(props) => (props.$show ? "auto" : "none")};
    transition: opacity 0.2s ease;
  }
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

  // Check if we're on a touch device or mobile viewport
  // Using both touch detection and viewport width ensures mobile UX in both real devices and tests
  const isMobileViewport =
    typeof window !== "undefined" && window.innerWidth <= 768;
  const isTouchDevice =
    typeof window !== "undefined" && "ontouchstart" in window;
  const useMobileBehavior = isTouchDevice || isMobileViewport;

  // Dynamically get the icon component from lucide-react
  const IconComponent = (LucideIcons[badge.icon as keyof typeof LucideIcons] ||
    LucideIcons.Award) as React.ComponentType<{ size: number }>;

  // Update popup position using floating-ui (only on non-mobile)
  const updatePosition = async () => {
    if (!badgeRef.current || !popupRef.current) return;

    // Skip positioning on mobile - we use fixed centered positioning via CSS
    if (window.innerWidth <= 768) return;

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
    if (!useMobileBehavior) {
      setShowPopup(true);
    }
  };

  const handleMouseLeave = () => {
    if (!useMobileBehavior) {
      setShowPopup(false);
    }
  };

  const handleClick = (e: React.MouseEvent) => {
    if (useMobileBehavior) {
      e.preventDefault();
      e.stopPropagation();
      setShowPopup((prev) => !prev);
    }
  };

  const handleOverlayClick = () => {
    setShowPopup(false);
  };

  const badgeElement = (
    <div
      ref={badgeRef}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
      style={{ display: "inline-block", maxWidth: "100%" }}
    >
      <StyledBadge $badgeColor={badge.color || "#05313d"}>
        <IconComponent size={size === "mini" ? 12 : 14} />
        {badge.name}
      </StyledBadge>
    </div>
  );

  if (!showTooltip) {
    return (
      <StyledBadge $badgeColor={badge.color || "#05313d"}>
        <IconComponent size={size === "mini" ? 12 : 14} />
        {badge.name}
      </StyledBadge>
    );
  }

  return (
    <>
      {badgeElement}
      <MobileOverlay
        $show={showPopup}
        onClick={handleOverlayClick}
        data-testid="badge-mobile-overlay"
      />
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
