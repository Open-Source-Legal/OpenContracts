import React from "react";
import styled from "styled-components";
import { color } from "../../theme/colors";
import {
  MessageCircle,
  ThumbsUp,
  Award,
  AtSign,
  CheckCircle,
  Lock,
  Unlock,
  Pin,
  Trash2,
  RotateCcw,
  MessageSquare,
} from "lucide-react";
import { useMutation } from "@apollo/client";
import {
  MARK_NOTIFICATION_READ,
  MARK_NOTIFICATION_UNREAD,
  DELETE_NOTIFICATION,
  MarkNotificationReadInput,
  MarkNotificationReadOutput,
  MarkNotificationUnreadInput,
  MarkNotificationUnreadOutput,
  DeleteNotificationInput,
  DeleteNotificationOutput,
} from "../../graphql/mutations";
import {
  GET_NOTIFICATIONS,
  GET_UNREAD_NOTIFICATION_COUNT,
} from "../../graphql/queries";
import { formatDistanceToNow } from "date-fns";
import type { NotificationNode } from "../../graphql/queries";

const ItemContainer = styled.div<{ $isRead?: boolean }>`
  display: flex;
  gap: 12px;
  padding: 12px;
  background: ${({ theme, $isRead }) => ($isRead ? color.N1 : color.N2)};
  border-bottom: 1px solid ${({ theme }) => color.N4};
  cursor: pointer;
  transition: background 0.15s ease;

  &:hover {
    background: ${({ theme }) => color.N3};
  }

  &:last-child {
    border-bottom: none;
  }
`;

const IconContainer = styled.div<{ $color: string }>`
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: ${({ $color }) => $color}15;
  display: flex;
  align-items: center;
  justify-content: center;
  color: ${({ $color }) => $color};

  svg {
    width: 20px;
    height: 20px;
  }
`;

const Content = styled.div`
  flex: 1;
  min-width: 0;
`;

const Header = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
`;

const Username = styled.span`
  font-weight: 600;
  color: ${({ theme }) => color.N10};
  font-size: 14px;
`;

const Time = styled.span`
  font-size: 12px;
  color: ${({ theme }) => color.N7};
`;

const UnreadDot = styled.span`
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: ${({ theme }) => color.B5};
  flex-shrink: 0;
`;

const Message = styled.p`
  margin: 0;
  font-size: 14px;
  color: ${({ theme }) => color.N10};
  line-height: 1.4;
`;

const ThreadTitle = styled.span`
  font-weight: 500;
  color: ${({ theme }) => color.B5};
`;

const Actions = styled.div`
  display: flex;
  gap: 8px;
  margin-top: 8px;
`;

const ActionButton = styled.button`
  padding: 4px 8px;
  font-size: 12px;
  background: transparent;
  border: 1px solid ${({ theme }) => color.N4};
  border-radius: 4px;
  color: ${({ theme }) => color.N7};
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: ${({ theme }) => color.N3};
    border-color: ${({ theme }) => color.B5};
    color: ${({ theme }) => color.B5};
  }
`;

export interface NotificationItemProps {
  notification: NotificationNode;
  onClick?: (notification: NotificationNode) => void;
  showActions?: boolean;
}

const NOTIFICATION_CONFIG = {
  REPLY: {
    icon: MessageCircle,
    color: "#2196F3",
    getMessage: (n: NotificationNode) =>
      `${n.actor?.username || "Someone"} replied to your message${
        n.conversation?.title ? ` in "${n.conversation.title}"` : ""
      }`,
  },
  VOTE: {
    icon: ThumbsUp,
    color: "#4CAF50",
    getMessage: (n: NotificationNode) => {
      const voteType =
        n.data?.voteType === "DOWNVOTE" ? "downvoted" : "upvoted";
      return `${n.actor?.username || "Someone"} ${voteType} your message`;
    },
  },
  BADGE: {
    icon: Award,
    color: "#FF9800",
    getMessage: (n: NotificationNode) =>
      `You earned the "${n.data?.badgeName || "badge"}" badge!`,
  },
  MENTION: {
    icon: AtSign,
    color: "#9C27B0",
    getMessage: (n: NotificationNode) =>
      `${n.actor?.username || "Someone"} mentioned you${
        n.conversation?.title ? ` in "${n.conversation.title}"` : ""
      }`,
  },
  ACCEPTED: {
    icon: CheckCircle,
    color: "#4CAF50",
    getMessage: (n: NotificationNode) =>
      `${n.actor?.username || "Someone"} accepted your answer`,
  },
  THREAD_LOCKED: {
    icon: Lock,
    color: "#F44336",
    getMessage: (n: NotificationNode) =>
      `${n.actor?.username || "A moderator"} locked thread "${
        n.conversation?.title || "a thread"
      }"`,
  },
  THREAD_UNLOCKED: {
    icon: Unlock,
    color: "#4CAF50",
    getMessage: (n: NotificationNode) =>
      `${n.actor?.username || "A moderator"} unlocked thread "${
        n.conversation?.title || "a thread"
      }"`,
  },
  THREAD_PINNED: {
    icon: Pin,
    color: "#2196F3",
    getMessage: (n: NotificationNode) =>
      `${n.actor?.username || "A moderator"} pinned thread "${
        n.conversation?.title || "a thread"
      }"`,
  },
  THREAD_UNPINNED: {
    icon: Pin,
    color: "#757575",
    getMessage: (n: NotificationNode) =>
      `${n.actor?.username || "A moderator"} unpinned thread "${
        n.conversation?.title || "a thread"
      }"`,
  },
  MESSAGE_DELETED: {
    icon: Trash2,
    color: "#F44336",
    getMessage: (n: NotificationNode) =>
      `${n.actor?.username || "A moderator"} deleted your message`,
  },
  THREAD_DELETED: {
    icon: Trash2,
    color: "#F44336",
    getMessage: (n: NotificationNode) =>
      `${n.actor?.username || "A moderator"} deleted thread "${
        n.conversation?.title || "a thread"
      }"`,
  },
  MESSAGE_RESTORED: {
    icon: RotateCcw,
    color: "#4CAF50",
    getMessage: (n: NotificationNode) =>
      `${n.actor?.username || "A moderator"} restored your message`,
  },
  THREAD_RESTORED: {
    icon: RotateCcw,
    color: "#4CAF50",
    getMessage: (n: NotificationNode) =>
      `${n.actor?.username || "A moderator"} restored thread "${
        n.conversation?.title || "a thread"
      }"`,
  },
  THREAD_REPLY: {
    icon: MessageSquare,
    color: "#2196F3",
    getMessage: (n: NotificationNode) =>
      `${n.actor?.username || "Someone"} replied in thread "${
        n.conversation?.title || "a thread"
      }"`,
  },
};

export function NotificationItem({
  notification,
  onClick,
  showActions = true,
}: NotificationItemProps) {
  const config =
    NOTIFICATION_CONFIG[
      notification.notificationType as keyof typeof NOTIFICATION_CONFIG
    ] || NOTIFICATION_CONFIG.REPLY;

  const Icon = config.icon;

  const [markRead] = useMutation<
    MarkNotificationReadOutput,
    MarkNotificationReadInput
  >(MARK_NOTIFICATION_READ, {
    refetchQueries: [GET_NOTIFICATIONS, GET_UNREAD_NOTIFICATION_COUNT],
  });

  const [markUnread] = useMutation<
    MarkNotificationUnreadOutput,
    MarkNotificationUnreadInput
  >(MARK_NOTIFICATION_UNREAD, {
    refetchQueries: [GET_NOTIFICATIONS, GET_UNREAD_NOTIFICATION_COUNT],
  });

  const [deleteNotification] = useMutation<
    DeleteNotificationOutput,
    DeleteNotificationInput
  >(DELETE_NOTIFICATION, {
    refetchQueries: [GET_NOTIFICATIONS, GET_UNREAD_NOTIFICATION_COUNT],
  });

  const handleClick = () => {
    if (!notification.isRead) {
      markRead({ variables: { notificationId: notification.id } });
    }
    onClick?.(notification);
  };

  const handleMarkAsRead = (e: React.MouseEvent) => {
    e.stopPropagation();
    markRead({ variables: { notificationId: notification.id } });
  };

  const handleMarkAsUnread = (e: React.MouseEvent) => {
    e.stopPropagation();
    markUnread({ variables: { notificationId: notification.id } });
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm("Delete this notification?")) {
      deleteNotification({ variables: { notificationId: notification.id } });
    }
  };

  return (
    <ItemContainer $isRead={notification.isRead} onClick={handleClick}>
      <IconContainer $color={config.color}>
        <Icon />
      </IconContainer>

      <Content>
        <Header>
          {!notification.isRead && <UnreadDot />}
          <Time>
            {formatDistanceToNow(new Date(notification.createdAt), {
              addSuffix: true,
            })}
          </Time>
        </Header>

        <Message>{config.getMessage(notification)}</Message>

        {showActions && (
          <Actions>
            {notification.isRead ? (
              <ActionButton onClick={handleMarkAsUnread}>
                Mark as unread
              </ActionButton>
            ) : (
              <ActionButton onClick={handleMarkAsRead}>
                Mark as read
              </ActionButton>
            )}
            <ActionButton onClick={handleDelete}>Delete</ActionButton>
          </Actions>
        )}
      </Content>
    </ItemContainer>
  );
}
