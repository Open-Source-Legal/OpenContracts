import React from "react";
import styled from "styled-components";
import { useQuery, useMutation } from "@apollo/client";
import { color } from "../../theme/colors";
import { CheckCheck, Settings } from "lucide-react";
import {
  GET_NOTIFICATIONS,
  GET_UNREAD_NOTIFICATION_COUNT,
  type GetNotificationsOutput,
} from "../../graphql/queries";
import {
  MARK_ALL_NOTIFICATIONS_READ,
  type MarkAllNotificationsReadOutput,
} from "../../graphql/mutations";
import { NotificationItem } from "./NotificationItem";
import { useNavigate } from "react-router-dom";

const DropdownContainer = styled.div`
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 400px;
  max-height: 600px;
  background: ${({ theme }) => color.N1};
  border: 1px solid ${({ theme }) => color.N4};
  border-radius: 8px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  z-index: 1000;
  overflow: hidden;

  @media (max-width: 640px) {
    position: fixed;
    top: 60px;
    left: 8px;
    right: 8px;
    width: auto;
  }
`;

const Header = styled.div`
  padding: 16px;
  border-bottom: 1px solid ${({ theme }) => color.N4};
  display: flex;
  align-items: center;
  justify-content: space-between;
`;

const Title = styled.h3`
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: ${({ theme }) => color.N10};
`;

const HeaderActions = styled.div`
  display: flex;
  gap: 8px;
`;

const IconButton = styled.button`
  padding: 6px;
  background: transparent;
  border: 1px solid ${({ theme }) => color.N4};
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: ${({ theme }) => color.N7};
  transition: all 0.15s ease;

  &:hover {
    background: ${({ theme }) => color.N3};
    border-color: ${({ theme }) => color.B5};
    color: ${({ theme }) => color.B5};
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
  flex: 1;
  overflow-y: auto;
  max-height: 500px;
`;

const EmptyState = styled.div`
  padding: 48px 24px;
  text-align: center;
  color: ${({ theme }) => color.N7};
  font-size: 14px;
`;

const Footer = styled.div`
  padding: 12px;
  border-top: 1px solid ${({ theme }) => color.N4};
  display: flex;
  justify-content: center;
`;

const ViewAllButton = styled.button`
  padding: 8px 16px;
  background: transparent;
  border: 1px solid ${({ theme }) => color.N4};
  border-radius: 4px;
  font-size: 14px;
  font-weight: 500;
  color: ${({ theme }) => color.B5};
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: ${({ theme }) => color.B5};
    color: white;
    border-color: ${({ theme }) => color.B5};
  }
`;

const LoadingState = styled.div`
  padding: 48px 24px;
  text-align: center;
  color: ${({ theme }) => color.N7};
  font-size: 14px;
`;

export interface NotificationDropdownProps {
  onClose?: () => void;
  onViewAll?: () => void;
  maxItems?: number;
}

export function NotificationDropdown({
  onClose,
  onViewAll,
  maxItems = 10,
}: NotificationDropdownProps) {
  const navigate = useNavigate();

  const { data, loading } = useQuery<GetNotificationsOutput>(
    GET_NOTIFICATIONS,
    {
      variables: {
        limit: maxItems,
      },
      fetchPolicy: "cache-and-network",
    }
  );

  const [markAllRead, { loading: markingAll }] =
    useMutation<MarkAllNotificationsReadOutput>(MARK_ALL_NOTIFICATIONS_READ, {
      refetchQueries: [GET_NOTIFICATIONS, GET_UNREAD_NOTIFICATION_COUNT],
    });

  const notifications = data?.notifications?.edges?.map((e) => e.node) || [];
  const hasUnread = notifications.some((n) => !n.isRead);

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

    onClose?.();
  };

  const handleMarkAllRead = () => {
    markAllRead();
  };

  const handleViewAll = () => {
    navigate("/notifications");
    onClose?.();
  };

  return (
    <DropdownContainer>
      <Header>
        <Title>Notifications</Title>
        <HeaderActions>
          <IconButton
            onClick={handleMarkAllRead}
            disabled={!hasUnread || markingAll}
            title="Mark all as read"
            aria-label="Mark all as read"
          >
            <CheckCheck />
          </IconButton>
        </HeaderActions>
      </Header>

      <NotificationList>
        {loading && <LoadingState>Loading notifications...</LoadingState>}

        {!loading && notifications.length === 0 && (
          <EmptyState>No notifications yet</EmptyState>
        )}

        {!loading &&
          notifications.map((notification) => (
            <NotificationItem
              key={notification.id}
              notification={notification}
              onClick={handleNotificationClick}
              showActions={false}
            />
          ))}
      </NotificationList>

      {notifications.length > 0 && (
        <Footer>
          <ViewAllButton onClick={handleViewAll}>
            View all notifications
          </ViewAllButton>
        </Footer>
      )}
    </DropdownContainer>
  );
}
