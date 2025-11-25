import React from "react";
import { useQuery } from "@apollo/client";
import { Header, Message, Dimmer, Loader, Segment } from "semantic-ui-react";
import styled from "styled-components";
import { Badge, BadgeData } from "./Badge";
import {
  GET_USER_BADGES,
  GetUserBadgesInput,
  GetUserBadgesOutput,
} from "../../graphql/queries";

const BadgesContainer = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 0.75em;
  padding: 1em;
`;

const StyledSegment = styled(Segment)`
  &.ui.segment {
    border-radius: 16px;
    background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
    border: 1px solid rgba(226, 232, 240, 0.8);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  }
`;

const EmptyState = styled.div`
  text-align: center;
  padding: 3em 1em;
  color: #64748b;
  font-size: 1.1em;
`;

interface UserBadgesProps {
  userId: string;
  corpusId?: string;
  showTitle?: boolean;
  title?: string;
}

export const UserBadges: React.FC<UserBadgesProps> = ({
  userId,
  corpusId,
  showTitle = true,
  title = "Badges",
}) => {
  const { loading, error, data } = useQuery<
    GetUserBadgesOutput,
    GetUserBadgesInput
  >(GET_USER_BADGES, {
    variables: {
      userId,
      corpusId,
      limit: 100,
    },
    skip: !userId,
  });

  if (loading) {
    return (
      <StyledSegment>
        <Dimmer active inverted>
          <Loader>Loading badges...</Loader>
        </Dimmer>
        <div style={{ minHeight: "100px" }} />
      </StyledSegment>
    );
  }

  if (error) {
    return (
      <Message negative>
        <Message.Header>Error loading badges</Message.Header>
        <p>{error.message}</p>
      </Message>
    );
  }

  const userBadges = data?.userBadges?.edges?.map((edge) => edge.node) || [];

  if (userBadges.length === 0) {
    return (
      <StyledSegment>
        {showTitle && <Header as="h3">{title}</Header>}
        <EmptyState>No badges earned yet. Keep contributing!</EmptyState>
      </StyledSegment>
    );
  }

  // Transform UserBadgeNode to BadgeData format
  const badgeData: BadgeData[] = userBadges.map((ub) => ({
    id: ub.badge.id,
    name: ub.badge.name,
    description: ub.badge.description,
    icon: ub.badge.icon,
    color: ub.badge.color,
    badgeType: ub.badge.badgeType,
    awardedAt: ub.awardedAt,
    awardedBy: ub.awardedBy,
    corpus: ub.corpus,
  }));

  return (
    <StyledSegment>
      {showTitle && (
        <Header as="h3">
          {title} ({userBadges.length})
        </Header>
      )}
      <BadgesContainer>
        {badgeData.map((badge) => (
          <Badge key={badge.id} badge={badge} size="small" showTooltip={true} />
        ))}
      </BadgesContainer>
    </StyledSegment>
  );
};
