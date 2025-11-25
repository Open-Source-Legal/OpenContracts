/**
 * Recent Activity Component
 *
 * Issue: #611 - Create User Profile Page with badge display and stats
 * Epic: #572 - Social Features Epic
 *
 * Displays user's recent activity (messages, annotations, documents uploaded).
 * Implements permission-aware filtering - only shows activities on objects
 * the requesting user has permission to see.
 */

import React from "react";
import { useQuery } from "@apollo/client";
import styled from "styled-components";
import { MessageSquare, FileText, Tag, Clock } from "lucide-react";
import { Dimmer, Loader, Message } from "semantic-ui-react";
import { formatDistanceToNow } from "date-fns";
import { gql } from "@apollo/client";
import { color } from "../../theme/colors";

const ActivityList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
`;

const ActivityItem = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  padding: 1rem;
  background: ${color.N2};
  border-radius: 8px;
  transition: all 0.2s;

  &:hover {
    background: ${color.N3};
    cursor: pointer;
  }
`;

const ActivityIcon = styled.div<{ $type: string }>`
  width: 36px;
  height: 36px;
  border-radius: 6px;
  background: ${({ $type }) => {
    switch ($type) {
      case "message":
        return color.B5;
      case "annotation":
        return color.G5;
      case "document":
        return color.O5;
      default:
        return color.N5;
    }
  }};
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  flex-shrink: 0;

  svg {
    width: 18px;
    height: 18px;
  }
`;

const ActivityContent = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
`;

const ActivityTitle = styled.div`
  font-size: 14px;
  font-weight: 600;
  color: ${color.N10};
`;

const ActivityDescription = styled.div`
  font-size: 13px;
  color: ${color.N7};
  line-height: 1.4;

  /* Truncate long text */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
`;

const ActivityTime = styled.div`
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 12px;
  color: ${color.N6};
  margin-top: 0.25rem;

  svg {
    width: 12px;
    height: 12px;
  }
`;

const EmptyState = styled.div`
  text-align: center;
  padding: 2rem 1rem;
  color: ${color.N6};
`;

// GraphQL query for recent user activity
const GET_RECENT_ACTIVITY = gql`
  query GetRecentActivity($userId: ID!) {
    userMessages(creatorId: $userId, first: 5, msgType: "HUMAN") {
      id
      content
      created
      conversation {
        id
        title
      }
    }
  }
`;

export interface RecentActivityProps {
  userId: string;
}

export const RecentActivity: React.FC<RecentActivityProps> = ({ userId }) => {
  const { data, loading, error } = useQuery(GET_RECENT_ACTIVITY, {
    variables: { userId },
    skip: !userId,
  });

  if (loading) {
    return (
      <div style={{ minHeight: "200px", position: "relative" }}>
        <Dimmer active inverted>
          <Loader>Loading activity...</Loader>
        </Dimmer>
      </div>
    );
  }

  if (error) {
    return (
      <Message negative>
        <Message.Header>Error loading activity</Message.Header>
        <p>{error.message}</p>
      </Message>
    );
  }

  const messages = data?.userMessages || [];

  if (messages.length === 0) {
    return <EmptyState>No recent activity to display</EmptyState>;
  }

  return (
    <ActivityList>
      {messages.map((message: any) => (
        <ActivityItem key={message.id}>
          <ActivityIcon $type="message">
            <MessageSquare />
          </ActivityIcon>
          <ActivityContent>
            <ActivityTitle>
              Posted in {message.conversation?.title || "a discussion"}
            </ActivityTitle>
            <ActivityDescription>
              {message.content.length > 150
                ? `${message.content.substring(0, 150)}...`
                : message.content}
            </ActivityDescription>
            <ActivityTime>
              <Clock />
              {formatDistanceToNow(new Date(message.created), {
                addSuffix: true,
              })}
            </ActivityTime>
          </ActivityContent>
        </ActivityItem>
      ))}
    </ActivityList>
  );
};
