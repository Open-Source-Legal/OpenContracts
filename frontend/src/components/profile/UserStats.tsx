/**
 * User Stats Component
 *
 * Issue: #611 - Create User Profile Page with badge display and stats
 * Epic: #572 - Social Features Epic
 *
 * Displays user contribution statistics in a compact card format.
 */

import React from "react";
import styled from "styled-components";
import { MessageSquare, FileText, Tag, Upload } from "lucide-react";
import { color } from "../../theme/colors";

const StatsGrid = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;

  @media (max-width: 480px) {
    grid-template-columns: 1fr;
  }
`;

const StatCard = styled.div`
  padding: 1rem;
  background: ${color.N2};
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  transition: all 0.2s;

  &:hover {
    background: ${color.N3};
    transform: translateY(-2px);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  }
`;

const StatIcon = styled.div<{ $color: string }>`
  width: 40px;
  height: 40px;
  border-radius: 8px;
  background: ${({ $color }) => $color};
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  flex-shrink: 0;

  svg {
    width: 20px;
    height: 20px;
  }
`;

const StatInfo = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
`;

const StatValue = styled.div`
  font-size: 24px;
  font-weight: 700;
  color: ${color.N10};
  line-height: 1;
`;

const StatLabel = styled.div`
  font-size: 12px;
  color: ${color.N6};
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
`;

export interface UserStatsProps {
  totalMessages: number;
  totalThreads: number;
  totalAnnotations: number;
  totalDocuments: number;
}

export const UserStats: React.FC<UserStatsProps> = ({
  totalMessages,
  totalThreads,
  totalAnnotations,
  totalDocuments,
}) => {
  return (
    <StatsGrid>
      <StatCard>
        <StatIcon $color={color.B5}>
          <MessageSquare />
        </StatIcon>
        <StatInfo>
          <StatValue>{totalMessages.toLocaleString()}</StatValue>
          <StatLabel>Messages</StatLabel>
        </StatInfo>
      </StatCard>

      <StatCard>
        <StatIcon $color={color.P5}>
          <FileText />
        </StatIcon>
        <StatInfo>
          <StatValue>{totalThreads.toLocaleString()}</StatValue>
          <StatLabel>Threads</StatLabel>
        </StatInfo>
      </StatCard>

      <StatCard>
        <StatIcon $color={color.G5}>
          <Tag />
        </StatIcon>
        <StatInfo>
          <StatValue>{totalAnnotations.toLocaleString()}</StatValue>
          <StatLabel>Annotations</StatLabel>
        </StatInfo>
      </StatCard>

      <StatCard>
        <StatIcon $color={color.O5}>
          <Upload />
        </StatIcon>
        <StatInfo>
          <StatValue>{totalDocuments.toLocaleString()}</StatValue>
          <StatLabel>Documents</StatLabel>
        </StatInfo>
      </StatCard>
    </StatsGrid>
  );
};
