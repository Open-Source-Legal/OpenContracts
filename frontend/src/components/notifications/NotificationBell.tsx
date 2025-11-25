import React, { useState, useRef, useEffect } from "react";
import styled from "styled-components";
import { Bell } from "lucide-react";
import { color } from "../../theme/colors";
import { useQuery } from "@apollo/client";
import { GET_UNREAD_NOTIFICATION_COUNT } from "../../graphql/queries";
import { NotificationDropdown } from "./NotificationDropdown";

const BellContainer = styled.div`
  position: relative;
  display: inline-block;
`;

const BellButton = styled.button<{ $hasUnread?: boolean }>`
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: none;
  background: ${({ theme, $hasUnread }) =>
    $hasUnread ? color.B5 : "transparent"};
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  color: ${({ theme, $hasUnread }) => ($hasUnread ? "white" : color.N10)};

  &:hover {
    background: ${({ theme }) => color.N3};
    color: ${({ theme }) => color.B5};
  }

  svg {
    width: 20px;
    height: 20px;
  }
`;

const Badge = styled.span`
  position: absolute;
  top: 6px;
  right: 6px;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  background: ${({ theme }) => color.R7};
  color: white;
  font-size: 11px;
  font-weight: 700;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  pointer-events: none;
`;

export interface NotificationBellProps {
  /** Show full notification center instead of dropdown */
  fullPageMode?: boolean;
  /** Callback when notification center link clicked */
  onViewAll?: () => void;
  /** Polling interval in ms (default: 30000 = 30s) */
  pollInterval?: number;
}

export function NotificationBell({
  fullPageMode = false,
  onViewAll,
  pollInterval = 30000,
}: NotificationBellProps) {
  const [showDropdown, setShowDropdown] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const { data, startPolling, stopPolling } = useQuery(
    GET_UNREAD_NOTIFICATION_COUNT,
    {
      fetchPolicy: "cache-and-network",
    }
  );

  const unreadCount = data?.unreadNotificationCount || 0;

  useEffect(() => {
    if (pollInterval > 0) {
      startPolling(pollInterval);
      return () => stopPolling();
    }
  }, [pollInterval, startPolling, stopPolling]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setShowDropdown(false);
      }
    }

    if (showDropdown) {
      document.addEventListener("mousedown", handleClickOutside);
      return () =>
        document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [showDropdown]);

  const handleBellClick = () => {
    if (fullPageMode && onViewAll) {
      onViewAll();
    } else {
      setShowDropdown(!showDropdown);
    }
  };

  return (
    <BellContainer ref={containerRef}>
      <BellButton
        onClick={handleBellClick}
        $hasUnread={unreadCount > 0}
        title={`${unreadCount} unread notification${
          unreadCount !== 1 ? "s" : ""
        }`}
        aria-label={`Notifications (${unreadCount} unread)`}
      >
        <Bell />
        {unreadCount > 0 && (
          <Badge>{unreadCount > 99 ? "99+" : unreadCount}</Badge>
        )}
      </BellButton>

      {showDropdown && !fullPageMode && (
        <NotificationDropdown
          onClose={() => setShowDropdown(false)}
          onViewAll={onViewAll}
        />
      )}
    </BellContainer>
  );
}
