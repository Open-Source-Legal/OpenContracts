import React, { useState } from "react";
import styled from "styled-components";
import { Award } from "lucide-react";
import { color } from "../../theme/colors";

const Badge = styled.div<{ $size?: "small" | "medium" | "large" }>`
  display: inline-flex;
  align-items: center;
  gap: ${({ $size }) => {
    if ($size === "small") return "4px";
    if ($size === "large") return "8px";
    return "6px";
  }};
  padding: ${({ $size }) => {
    if ($size === "small") return "2px 6px";
    if ($size === "large") return "6px 12px";
    return "4px 8px";
  }};
  background: ${({ theme }) => color.N2};
  border: 1px solid ${({ theme }) => color.N4};
  border-radius: 12px;
  font-size: ${({ $size }) => {
    if ($size === "small") return "11px";
    if ($size === "large") return "14px";
    return "12px";
  }};
  font-weight: 600;
  color: ${({ theme }) => color.N10};
  cursor: ${({ title }) => (title ? "help" : "default")};
  transition: all 0.15s ease;
  position: relative;

  &:hover {
    border-color: ${({ theme, title }) => (title ? color.B5 : color.N4)};
  }

  svg {
    width: ${({ $size }) => {
      if ($size === "small") return "12px";
      if ($size === "large") return "18px";
      return "14px";
    }};
    height: ${({ $size }) => {
      if ($size === "small") return "12px";
      if ($size === "large") return "18px";
      return "14px";
    }};
    color: ${({ theme }) => color.Y6};
  }
`;

const ReputationValue = styled.span<{ $value: number }>`
  color: ${({ $value, theme }) => {
    if ($value >= 1000) return theme.color.success;
    if ($value >= 500) return color.B5;
    if ($value < 0) return color.R7;
    return color.N10;
  }};
`;

const Tooltip = styled.div`
  position: absolute;
  bottom: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  background: ${({ theme }) => color.N1};
  border: 1px solid ${({ theme }) => color.N4};
  border-radius: 6px;
  padding: 12px;
  min-width: 200px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 100;
  pointer-events: none;

  &::after {
    content: "";
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    border: 6px solid transparent;
    border-top-color: ${({ theme }) => color.N4};
  }

  &::before {
    content: "";
    position: absolute;
    top: calc(100% - 1px);
    left: 50%;
    transform: translateX(-50%);
    border: 5px solid transparent;
    border-top-color: ${({ theme }) => color.N1};
    z-index: 1;
  }
`;

const TooltipTitle = styled.div`
  font-size: 13px;
  font-weight: 600;
  color: ${({ theme }) => color.N10};
  margin-bottom: 8px;
`;

const TooltipSection = styled.div`
  margin-bottom: 6px;

  &:last-child {
    margin-bottom: 0;
  }
`;

const TooltipLabel = styled.div`
  font-size: 11px;
  color: ${({ theme }) => color.N6};
  margin-bottom: 2px;
`;

const TooltipValue = styled.div<{ $positive?: boolean }>`
  font-size: 13px;
  font-weight: 500;
  color: ${({ $positive, theme }) => {
    if ($positive === true) return theme.color.success;
    if ($positive === false) return color.N7;
    return color.N10;
  }};
`;

const Divider = styled.div`
  height: 1px;
  background: ${({ theme }) => color.N4};
  margin: 8px 0;
`;

export interface ReputationBreakdown {
  /** Total reputation score */
  total: number;
  /** Reputation from upvotes received */
  fromUpvotes?: number;
  /** Reputation from downvotes received */
  fromDownvotes?: number;
  /** Reputation from accepted answers */
  fromAcceptedAnswers?: number;
  /** Reputation from badges/achievements */
  fromBadges?: number;
  /** Corpus-specific reputation (if applicable) */
  corpusReputation?: number;
}

export interface ReputationBadgeProps {
  /** Reputation value to display */
  reputation: number;
  /** Detailed breakdown for tooltip */
  breakdown?: ReputationBreakdown;
  /** Size variant */
  size?: "small" | "medium" | "large";
  /** Show icon */
  showIcon?: boolean;
  /** Show tooltip on hover */
  showTooltip?: boolean;
  /** Custom label (e.g., "Global Reputation") */
  label?: string;
}

export function ReputationBadge({
  reputation,
  breakdown,
  size = "medium",
  showIcon = true,
  showTooltip = true,
  label,
}: ReputationBadgeProps) {
  const [showTooltipState, setShowTooltipState] = useState(false);

  // Format large numbers (e.g., 1.2k, 10k)
  const formatReputation = (value: number): string => {
    if (value >= 10000) {
      return `${Math.floor(value / 1000)}k`;
    }
    if (value >= 1000) {
      return `${(value / 1000).toFixed(1)}k`;
    }
    return value.toString();
  };

  const hasBreakdown = breakdown && showTooltip;

  return (
    <Badge
      $size={size}
      onMouseEnter={() => hasBreakdown && setShowTooltipState(true)}
      onMouseLeave={() => setShowTooltipState(false)}
      title={
        hasBreakdown ? "View reputation breakdown" : label || "Reputation score"
      }
      aria-label={`${label || "Reputation"}: ${reputation}`}
    >
      {showIcon && <Award />}
      {label && <span>{label}:</span>}
      <ReputationValue $value={reputation}>
        {formatReputation(reputation)}
      </ReputationValue>

      {showTooltipState && breakdown && (
        <Tooltip>
          <TooltipTitle>Reputation Breakdown</TooltipTitle>

          {breakdown.corpusReputation !== undefined && (
            <>
              <TooltipSection>
                <TooltipLabel>Corpus Reputation</TooltipLabel>
                <TooltipValue $positive={breakdown.corpusReputation > 0}>
                  {breakdown.corpusReputation}
                </TooltipValue>
              </TooltipSection>
              <Divider />
            </>
          )}

          <TooltipSection>
            <TooltipLabel>Total Reputation</TooltipLabel>
            <TooltipValue $positive={breakdown.total > 0}>
              {breakdown.total}
            </TooltipValue>
          </TooltipSection>

          {breakdown.fromUpvotes !== undefined && (
            <TooltipSection>
              <TooltipLabel>From Upvotes</TooltipLabel>
              <TooltipValue $positive={breakdown.fromUpvotes > 0}>
                +{breakdown.fromUpvotes}
              </TooltipValue>
            </TooltipSection>
          )}

          {breakdown.fromDownvotes !== undefined &&
            breakdown.fromDownvotes !== 0 && (
              <TooltipSection>
                <TooltipLabel>From Downvotes</TooltipLabel>
                <TooltipValue $positive={false}>
                  {breakdown.fromDownvotes}
                </TooltipValue>
              </TooltipSection>
            )}

          {breakdown.fromAcceptedAnswers !== undefined &&
            breakdown.fromAcceptedAnswers > 0 && (
              <TooltipSection>
                <TooltipLabel>From Accepted Answers</TooltipLabel>
                <TooltipValue $positive={true}>
                  +{breakdown.fromAcceptedAnswers}
                </TooltipValue>
              </TooltipSection>
            )}

          {breakdown.fromBadges !== undefined && breakdown.fromBadges > 0 && (
            <TooltipSection>
              <TooltipLabel>From Badges</TooltipLabel>
              <TooltipValue $positive={true}>
                +{breakdown.fromBadges}
              </TooltipValue>
            </TooltipSection>
          )}
        </Tooltip>
      )}
    </Badge>
  );
}
