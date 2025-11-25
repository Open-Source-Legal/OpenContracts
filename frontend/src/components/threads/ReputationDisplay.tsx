import React from "react";
import styled from "styled-components";
import { ReputationBadge, ReputationBreakdown } from "./ReputationBadge";
import { color } from "../../theme/colors";

const Container = styled.div<{ $layout?: "horizontal" | "vertical" }>`
  display: flex;
  flex-direction: ${({ $layout }) =>
    $layout === "vertical" ? "column" : "row"};
  gap: ${({ $layout }) => ($layout === "vertical" ? "8px" : "12px")};
  align-items: ${({ $layout }) =>
    $layout === "vertical" ? "flex-start" : "center"};
`;

const UserInfo = styled.div`
  display: flex;
  flex-direction: column;
  gap: 2px;
`;

const Username = styled.div`
  font-size: 14px;
  font-weight: 600;
  color: ${({ theme }) => color.N10};
`;

const UserRole = styled.div`
  font-size: 12px;
  color: ${({ theme }) => color.N6};
`;

const ReputationGroup = styled.div`
  display: flex;
  flex-direction: column;
  gap: 6px;
`;

export interface ReputationDisplayProps {
  /** Username to display */
  username: string;
  /** User's global reputation */
  globalReputation: number;
  /** Breakdown of global reputation */
  globalBreakdown?: ReputationBreakdown;
  /** Corpus-specific reputation (optional) */
  corpusReputation?: number;
  /** Breakdown of corpus reputation */
  corpusBreakdown?: ReputationBreakdown;
  /** User role/title (e.g., "Moderator", "Admin") */
  userRole?: string;
  /** Layout orientation */
  layout?: "horizontal" | "vertical";
  /** Show corpus reputation */
  showCorpusReputation?: boolean;
}

export function ReputationDisplay({
  username,
  globalReputation,
  globalBreakdown,
  corpusReputation,
  corpusBreakdown,
  userRole,
  layout = "horizontal",
  showCorpusReputation = true,
}: ReputationDisplayProps) {
  return (
    <Container $layout={layout}>
      <UserInfo>
        <Username>{username}</Username>
        {userRole && <UserRole>{userRole}</UserRole>}
      </UserInfo>

      <ReputationGroup>
        <ReputationBadge
          reputation={globalReputation}
          breakdown={globalBreakdown}
          label="Global"
          size="small"
          showIcon={true}
          showTooltip={!!globalBreakdown}
        />

        {showCorpusReputation && corpusReputation !== undefined && (
          <ReputationBadge
            reputation={corpusReputation}
            breakdown={corpusBreakdown}
            label="Corpus"
            size="small"
            showIcon={false}
            showTooltip={!!corpusBreakdown}
          />
        )}
      </ReputationGroup>
    </Container>
  );
}
