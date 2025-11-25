import React, { useState } from "react";
import styled from "styled-components";
import { useQuery, useMutation } from "@apollo/client";
import { color } from "../../theme/colors";
import { CheckCheck, Filter, X } from "lucide-react";
import {
  GET_NOTIFICATIONS,
  GET_UNREAD_NOTIFICATION_COUNT,
  type GetNotificationsOutput,
  type GetNotificationsInput,
} from "../../graphql/queries";
import {
  MARK_ALL_NOTIFICATIONS_READ,
  type MarkAllNotificationsReadOutput,
} from "../../graphql/mutations";
import { NotificationItem } from "./NotificationItem";
import { useNavigate } from "react-router-dom";

const Container = styled.div`
  max-width: 800px;
  margin: 0 auto;
  padding: 24px;

  @media (max-width: 640px) {
    padding: 16px;
  }
`;

const Header = styled.div`
  margin-bottom: 24px;
`;

const Title = styled.h1`
  margin: 0 0 16px 0;
  font-size: 24px;
  font-weight: 700;
  color: ${({ theme }) => color.N10};
`;

const Controls = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
`;

const FilterButtons = styled.div`
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
`;

const FilterButton = styled.button<{ $active?: boolean }>`
  padding: 8px 16px;
  font-size: 14px;
  font-weight: 500;
  border: 1px solid ${({ theme }) => color.N4};
  border-radius: 6px;
  background: ${({ theme, $active }) => ($active ? color.B5 : "transparent")};
  color: ${({ theme, $active }) => ($active ? "white" : color.N10)};
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: ${({ theme, $active }) => ($active ? color.B5 : color.N3)};
    border-color: ${({ theme }) => color.B5};
  }
`;

const ActionButton = styled.button`
  padding: 8px 16px;
  font-size: 14px;
  font-weight: 500;
  border: 1px solid ${({ theme }) => color.N4};
  border-radius: 6px;
  background: transparent;
  color: ${({ theme }) => color.B5};
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.15s ease;

  &:hover {
    background: ${({ theme }) => color.B5};
    color: white;
    border-color: ${({ theme }) => color.B5};
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  svg {
    width: 16px;
    height: 16px;
  }
`;

const NotificationList = styled.div`
  background: ${({ theme }) => color.N1};
  border: 1px solid ${({ theme }) => color.N4};
  border-radius: 8px;
  overflow: hidden;
`;

const EmptyState = styled.div`
  padding: 64px 24px;
  text-align: center;
  color: ${({ theme }) => color.N7};

  h3 {
    margin: 0 0 8px 0;
    font-size: 18px;
    font-weight: 600;
    color: ${({ theme }) => color.N10};
  }

  p {
    margin: 0;
    font-size: 14px;
  }
`;

const LoadingState = styled.div`
  padding: 64px 24px;
  text-align: center;
  color: ${({ theme }) => color.N7};
  font-size: 14px;
`;

const LoadMoreContainer = styled.div`
  padding: 16px;
  text-align: center;
  border-top: 1px solid ${({ theme }) => color.N4};
`;

const LoadMoreButton = styled.button`
  padding: 8px 24px;
  font-size: 14px;
  font-weight: 500;
  border: 1px solid ${({ theme }) => color.N4};
  border-radius: 6px;
  background: transparent;
  color: ${({ theme }) => color.B5};
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: ${({ theme }) => color.B5};
    color: white;
    border-color: ${({ theme }) => color.B5};
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
`;

type FilterType = "all" | "unread" | "read";

export function NotificationCenter() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState<FilterType>("all");

  const queryVariables: GetNotificationsInput = {
    limit: 50,
    ...(filter === "unread" && { isRead: false }),
    ...(filter === "read" && { isRead: true }),
  };

  const { data, loading, fetchMore } = useQuery<GetNotificationsOutput>(
    GET_NOTIFICATIONS,
    {
      variables: queryVariables,
      fetchPolicy: "cache-and-network",
    }
  );

  const [markAllRead, { loading: markingAll }] =
    useMutation<MarkAllNotificationsReadOutput>(MARK_ALL_NOTIFICATIONS_READ, {
      refetchQueries: [GET_NOTIFICATIONS, GET_UNREAD_NOTIFICATION_COUNT],
    });

  const notifications = data?.notifications?.edges?.map((e) => e.node) || [];
  const hasUnread = notifications.some((n) => !n.isRead);
  const hasMore = data?.notifications?.pageInfo?.hasNextPage || false;

  const handleNotificationClick = (notification: any) => {
    // Navigate to the relevant thread/message
    if (notification.conversation?.id) {
      const conversationId = notification.conversation.id;
      const corpusId = notification.conversation.chatWithCorpus?.id;

      if (corpusId) {
        navigate(
          `/corpus/${corpusId}/discussions/thread/${conversationId}${
            notification.message?.id
              ? `?message=${notification.message.id}`
              : ""
          }`
        );
      } else {
        navigate(
          `/discussions/thread/${conversationId}${
            notification.message?.id
              ? `?message=${notification.message.id}`
              : ""
          }`
        );
      }
    }
  };

  const handleMarkAllRead = () => {
    markAllRead();
  };

  const handleLoadMore = () => {
    if (hasMore && !loading) {
      fetchMore({
        variables: {
          ...queryVariables,
          cursor: data?.notifications?.pageInfo?.endCursor,
        },
      });
    }
  };

  return (
    <Container>
      <Header>
        <Title>Notifications</Title>
        <Controls>
          <FilterButtons>
            <FilterButton
              $active={filter === "all"}
              onClick={() => setFilter("all")}
            >
              All
            </FilterButton>
            <FilterButton
              $active={filter === "unread"}
              onClick={() => setFilter("unread")}
            >
              Unread
            </FilterButton>
            <FilterButton
              $active={filter === "read"}
              onClick={() => setFilter("read")}
            >
              Read
            </FilterButton>
          </FilterButtons>

          <ActionButton
            onClick={handleMarkAllRead}
            disabled={!hasUnread || markingAll}
          >
            <CheckCheck />
            Mark all as read
          </ActionButton>
        </Controls>
      </Header>

      <NotificationList>
        {loading && <LoadingState>Loading notifications...</LoadingState>}

        {!loading && notifications.length === 0 && (
          <EmptyState>
            <h3>
              {filter === "unread"
                ? "No unread notifications"
                : filter === "read"
                ? "No read notifications"
                : "No notifications yet"}
            </h3>
            <p>
              {filter === "all"
                ? "When you receive notifications, they'll appear here."
                : "Try changing the filter to see other notifications."}
            </p>
          </EmptyState>
        )}

        {!loading &&
          notifications.map((notification) => (
            <NotificationItem
              key={notification.id}
              notification={notification}
              onClick={handleNotificationClick}
              showActions={true}
            />
          ))}

        {!loading && hasMore && (
          <LoadMoreContainer>
            <LoadMoreButton onClick={handleLoadMore}>
              Load more notifications
            </LoadMoreButton>
          </LoadMoreContainer>
        )}
      </NotificationList>
    </Container>
  );
}
