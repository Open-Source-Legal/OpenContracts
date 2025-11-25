import React from "react";
import styled from "styled-components";
import * as LucideIcons from "lucide-react";
import { Popup } from "semantic-ui-react";
import {
  ChatMessageType,
  UserBadgeType,
  AgentConfigurationType,
} from "../../types/graphql-api";

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
  color: #1e293b;
`;

const BadgeDescription = styled.div`
  font-size: 0.85em;
  color: #64748b;
  line-height: 1.4;
`;

const BadgeMetadata = styled.div`
  font-size: 0.75em;
  color: #94a3b8;
  margin-top: 0.3em;
  border-top: 1px solid #e2e8f0;
  padding-top: 0.5em;
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
    color: badgeConfig.color || "#4A90E2",
    label: badgeConfig.label || agentConfig.name,
  };
}

/**
 * Renders a single badge with optional tooltip
 */
function BadgeItem({
  badge,
  showTooltip,
}: {
  badge: BadgeDisplayData | AgentBadgeDisplayData;
  showTooltip: boolean;
}) {
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

  // Create detailed popup content
  const popupContent = (
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
            <div>Awarded: {new Date(badge.awardedAt).toLocaleDateString()}</div>
          )}
          {badge.awardedBy && <div>By: {badge.awardedBy.username}</div>}
        </BadgeMetadata>
      )}
    </BadgeContent>
  );

  return (
    <Popup
      trigger={badgeElement}
      content={popupContent}
      position="top center"
      hoverable
      inverted={false}
      style={{
        padding: "0.75em",
        borderRadius: "10px",
        boxShadow: "0 3px 15px rgba(0, 0, 0, 0.15)",
      }}
    />
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
        <MiniStyledBadge $badgeColor="#6b7280" title="More badges available">
          +{userBadges.length - maxBadges} more
        </MiniStyledBadge>
      )}
    </BadgeContainer>
  );
};
