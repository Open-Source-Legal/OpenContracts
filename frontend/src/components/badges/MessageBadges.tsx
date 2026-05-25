import React from "react";
import { createPortal } from "react-dom";
import styled from "styled-components";
import * as LucideIcons from "lucide-react";
import { useState, useRef, useLayoutEffect } from "react";
import {
  ChatMessageType,
  UserBadgeType,
  AgentConfigurationType,
} from "../../types/graphql-api";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import {
  CONTEXT_MENU_VIEWPORT_PADDING,
  POPOVER_GAP,
  POPOVER_Z_INDEX,
} from "../../assets/configurations/constants";

// Tooltip-specific bounds. Hoisted to module scope so they're visible to
// reviewers (no magic numbers buried inside a closure).
const TOOLTIP_HEIGHT_EST = 120; // generous upper bound for typical badge tooltips
const TOOLTIP_MAX_WIDTH = 220;

const BadgeContainer = styled.div`
  display: inline-flex;
  align-items: center;
  gap: 0.35em;
  flex-wrap: wrap;
`;

const MiniStyledBadge = styled.div<{ $badgeColor: string }>`
  display: inline-flex;
  align-items: center;
  gap: 0.3em;
  padding: 0.25em 0.5em;
  border-radius: 12px;
  font-weight: 600;
  font-size: 0.7em;
  background: ${(props) => props.$badgeColor};
  color: #ffffff;
  border: 1.5px solid rgba(255, 255, 255, 0.3);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
  transition: all 0.2s ease;
  cursor: default;
  white-space: nowrap;

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
  }
`;

const BadgeContent = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.5em;
  max-width: 200px;
`;

const BadgeTitle = styled.div`
  font-weight: 700;
  font-size: 1em;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const BadgeDescription = styled.div`
  font-size: 0.85em;
  color: ${OS_LEGAL_COLORS.textSecondary};
  line-height: 1.4;
`;

const BadgeMetadata = styled.div`
  font-size: 0.75em;
  color: ${OS_LEGAL_COLORS.textMuted};
  margin-top: 0.3em;
  border-top: 1px solid ${OS_LEGAL_COLORS.border};
  padding-top: 0.5em;
`;

const TooltipWrapper = styled.div`
  position: relative;
  display: inline-flex;
`;

const TooltipPopup = styled.div<{ $placement: "top" | "bottom" }>`
  position: fixed;
  /* Must outrank context menus (z=10000) and modals — POPOVER_Z_INDEX is
     the project's canonical "above everything but app shell overlays"
     layer. */
  z-index: ${POPOVER_Z_INDEX};
  padding: 0.75em;
  border-radius: 10px;
  background: white;
  box-shadow: 0 3px 15px rgba(0, 0, 0, 0.15);
  min-width: 180px;
  max-width: 220px;
  pointer-events: auto;

  &::after {
    content: "";
    position: absolute;
    left: var(--arrow-offset, 50%);
    transform: translateX(-50%);
    border: 6px solid transparent;
    ${({ $placement }) =>
      $placement === "top"
        ? `top: 100%; border-top-color: white;`
        : `bottom: 100%; border-bottom-color: white;`}
  }
`;

interface BadgeDisplayData {
  id: string;
  name: string;
  description: string;
  icon: string;
  color: string;
  badgeType?: string;
  isAutoAwarded?: boolean;
  awardedAt?: string;
  awardedBy?: { username: string };
  corpus?: { title: string };
}

interface AgentBadgeDisplayData {
  id: string;
  name: string;
  description?: string;
  icon: string;
  color: string;
  label: string;
}

/**
 * Badge display component for both user badges and agent badges
 * Displays small pill-style badges next to usernames in chat/thread messages
 */
export interface MessageBadgesProps {
  message: ChatMessageType;
  userBadges?: UserBadgeType[];
  maxBadges?: number;
  size?: "mini" | "tiny" | "small";
  showTooltip?: boolean;
}

/**
 * Extracts badge display data from agent configuration
 */
function getAgentBadgeData(
  agentConfig: AgentConfigurationType
): AgentBadgeDisplayData | null {
  if (!agentConfig.badgeConfig) return null;

  const badgeConfig = agentConfig.badgeConfig as any;

  return {
    id: agentConfig.id,
    name: agentConfig.name,
    description: agentConfig.description || undefined,
    icon: badgeConfig.icon || "Bot",
    color: badgeConfig.color || OS_LEGAL_COLORS.primaryBlue,
    label: badgeConfig.label || agentConfig.name,
  };
}

/**
 * Renders a single badge with optional tooltip.
 * Tooltip is portalled to document.body so it can escape ancestor
 * `overflow: hidden` containers (e.g. the sidebar shell).
 */
function BadgeItem({
  badge,
  showTooltip,
}: {
  badge: BadgeDisplayData | AgentBadgeDisplayData;
  showTooltip: boolean;
}) {
  const [isHovered, setIsHovered] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [tooltipPos, setTooltipPos] = useState<{
    top?: number; // set when placement === "bottom"
    bottom?: number; // set when placement === "top"
    left: number;
    placement: "top" | "bottom";
    arrowOffset: number;
  } | null>(null);

  // Recompute portal position whenever the tooltip becomes visible.
  // Uses fixed coords from the badge's bounding rect, then flips below
  // if there isn't enough room above (avoids clipping near the top of
  // a scroll container).  ``position: fixed`` doesn't follow the badge
  // when an ancestor scrolls, so we also re-run the math on any
  // capture-phase scroll / resize while the tooltip is visible.
  useLayoutEffect(() => {
    if (!isHovered || !wrapperRef.current) {
      setTooltipPos(null);
      return;
    }
    const computePosition = () => {
      const node = wrapperRef.current;
      if (!node) return;
      const rect = node.getBoundingClientRect();
      // Hide when the badge has scrolled fully out of the viewport so
      // the tooltip doesn't float as a free-standing artifact over the
      // rest of the UI.
      if (rect.bottom < 0 || rect.top > window.innerHeight) {
        setTooltipPos(null);
        return;
      }
      const placement: "top" | "bottom" =
        rect.top - TOOLTIP_HEIGHT_EST - POPOVER_GAP <
        CONTEXT_MENU_VIEWPORT_PADDING
          ? "bottom"
          : "top";

      // Center horizontally on the badge, clamped to viewport.
      const centerX = rect.left + rect.width / 2;
      let left = centerX - TOOLTIP_MAX_WIDTH / 2;
      left = Math.max(
        CONTEXT_MENU_VIEWPORT_PADDING,
        Math.min(
          left,
          window.innerWidth - TOOLTIP_MAX_WIDTH - CONTEXT_MENU_VIEWPORT_PADDING
        )
      );
      const arrowOffset = centerX - left; // px from tooltip's left edge to arrow center

      // Capture BOTH ``top`` and ``bottom`` here so the JSX doesn't have
      // to re-read ``window.innerHeight`` at render time — that read
      // could race with a resize between the effect firing and the next
      // paint and cause a 1-frame misalignment.
      if (placement === "top") {
        const bottom = window.innerHeight - (rect.top - POPOVER_GAP);
        setTooltipPos({ bottom, left, placement, arrowOffset });
      } else {
        const top = rect.bottom + POPOVER_GAP;
        setTooltipPos({ top, left, placement, arrowOffset });
      }
    };

    computePosition();
    // Re-position on ANY scroll (capture phase so ancestor scroll
    // containers, not just window, trigger it).  Without this the
    // tooltip drifts when the sidebar scrolls while the user holds the
    // cursor still over a badge.
    window.addEventListener("scroll", computePosition, true);
    window.addEventListener("resize", computePosition);
    return () => {
      window.removeEventListener("scroll", computePosition, true);
      window.removeEventListener("resize", computePosition);
    };
  }, [isHovered]);

  // Dynamically get the icon component from lucide-react
  const IconComponent = (LucideIcons[badge.icon as keyof typeof LucideIcons] ||
    LucideIcons.Award) as React.ComponentType<{ size: number }>;

  const badgeElement = (
    <MiniStyledBadge $badgeColor={badge.color || "#05313d"}>
      <IconComponent size={10} />
      {"label" in badge ? badge.label : badge.name}
    </MiniStyledBadge>
  );

  if (!showTooltip) {
    return badgeElement;
  }

  const tooltipContent = tooltipPos && (
    <TooltipPopup
      $placement={tooltipPos.placement}
      style={{
        top: tooltipPos.top,
        bottom: tooltipPos.bottom,
        left: tooltipPos.left,
        // Anchor the arrow under the badge center even when the tooltip
        // is clamped to the viewport edge (consumed by ::after in
        // TooltipPopup via var(--arrow-offset)).  React.CSSProperties
        // doesn't model CSS custom properties, so cast through
        // ``Record<string, string>`` rather than ``any`` to keep the
        // any-baseline gate honest.
        ...({
          "--arrow-offset": `${tooltipPos.arrowOffset}px`,
        } as Record<string, string>),
      }}
    >
      <BadgeContent>
        <BadgeTitle>{badge.name}</BadgeTitle>
        <BadgeDescription>{badge.description}</BadgeDescription>
        {"badgeType" in badge && (
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
        )}
      </BadgeContent>
    </TooltipPopup>
  );

  return (
    <TooltipWrapper
      ref={wrapperRef}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {badgeElement}
      {isHovered &&
        tooltipContent &&
        createPortal(tooltipContent, document.body)}
    </TooltipWrapper>
  );
}

/**
 * Main component that displays badges for both users and bots
 */
export const MessageBadges: React.FC<MessageBadgesProps> = ({
  message,
  userBadges = [],
  maxBadges = 3,
  showTooltip = true,
}) => {
  // Check if this is a bot/agent message
  const agentBadge = message.agentConfiguration
    ? getAgentBadgeData(message.agentConfiguration)
    : null;

  // Convert UserBadgeType to BadgeDisplayData
  const badgeDisplayData: BadgeDisplayData[] = userBadges
    .slice(0, maxBadges)
    .map((userBadge) => ({
      id: userBadge.id,
      name: userBadge.badge.name,
      description: userBadge.badge.description,
      icon: userBadge.badge.icon,
      color: userBadge.badge.color,
      badgeType: userBadge.badge.badgeType,
      isAutoAwarded: userBadge.badge.isAutoAwarded,
      awardedAt: userBadge.awardedAt,
      awardedBy: userBadge.awardedBy
        ? { username: userBadge.awardedBy.username || "" }
        : undefined,
      corpus: userBadge.corpus
        ? { title: userBadge.corpus.title || "" }
        : undefined,
    }));

  // If no badges to display, return null
  if (!agentBadge && badgeDisplayData.length === 0) {
    return null;
  }

  return (
    <BadgeContainer>
      {/* Agent badge (if present) */}
      {agentBadge && <BadgeItem badge={agentBadge} showTooltip={showTooltip} />}

      {/* User badges */}
      {badgeDisplayData.map((badge) => (
        <BadgeItem key={badge.id} badge={badge} showTooltip={showTooltip} />
      ))}

      {/* Show "+X more" if there are more badges */}
      {userBadges.length > maxBadges && (
        <MiniStyledBadge
          $badgeColor={OS_LEGAL_COLORS.textSecondary}
          title="More badges available"
        >
          +{userBadges.length - maxBadges} more
        </MiniStyledBadge>
      )}
    </BadgeContainer>
  );
};
