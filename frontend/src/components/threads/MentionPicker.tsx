import React, {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useState,
} from "react";
import styled from "styled-components";
import { color } from "../../theme/colors";
import { spacing } from "../../theme/spacing";

const Container = styled.div`
  position: absolute;
  background: ${color.N1};
  border: 1px solid ${color.N4};
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  max-height: 200px;
  overflow-y: auto;
  z-index: 1000;
  min-width: 200px;

  /**
   * Mobile responsive adjustments - Part of Issue #686
   * Uses CSS environment variables for keyboard-aware positioning
   * and safe area insets for notched devices.
   */
  @media (max-width: 600px) {
    position: fixed;
    left: 8px !important;
    right: 8px !important;
    /* Position above keyboard using env() with fallback */
    bottom: max(80px, calc(env(safe-area-inset-bottom) + 80px)) !important;
    top: auto !important;
    min-width: unset;
    max-width: unset;
    width: calc(100% - 16px);
    /* Limit height to prevent overflow on small screens */
    max-height: min(40vh, 300px);
    border-radius: 12px;
    box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.25);
    /* Smooth appearance animation */
    animation: slideUp 0.2s ease-out;
  }

  @keyframes slideUp {
    from {
      opacity: 0;
      transform: translateY(16px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
`;

const MenuItem = styled.button<{ $isSelected: boolean }>`
  display: flex;
  align-items: center;
  gap: ${spacing.sm};
  width: 100%;
  padding: ${spacing.sm} ${spacing.md};
  border: none;
  background: ${(props) => (props.$isSelected ? color.B1 : "transparent")};
  color: ${color.N10};
  font-size: 14px;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s;

  &:hover {
    background: ${(props) => (props.$isSelected ? color.B1 : color.N2)};
  }

  &:first-child {
    border-radius: 6px 6px 0 0;
  }

  &:last-child {
    border-radius: 0 0 6px 6px;
  }

  /**
   * Mobile touch-friendly adjustments - Part of Issue #686
   * Larger touch targets for easier selection on touch devices.
   */
  @media (max-width: 600px) {
    padding: 14px 16px;
    min-height: 52px;
    font-size: 15px;

    &:active {
      background: ${color.B1};
    }

    /* First and last child border radius for mobile rounded corners */
    &:first-child {
      border-radius: 12px 12px 0 0;
    }

    &:last-child {
      border-radius: 0 0 12px 12px;
    }

    &:only-child {
      border-radius: 12px;
    }
  }
`;

const UserAvatar = styled.div`
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: ${color.B4};
  color: ${color.N1};
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
`;

const UserInfo = styled.div`
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
`;

const Username = styled.span`
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const Email = styled.span`
  font-size: 12px;
  color: ${color.N6};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const NoResults = styled.div`
  padding: ${spacing.md};
  text-align: center;
  color: ${color.N6};
  font-size: 13px;
`;

export interface MentionUser {
  id: string;
  username: string;
  email?: string;
}

export interface MentionPickerProps {
  users: MentionUser[];
  onSelect: (user: MentionUser) => void;
  selectedIndex: number;
  loading?: boolean;
  error?: string | null;
  /** Optional hint shown when the user list is empty (e.g. "Type 2+ characters to search"). */
  hint?: string;
}

export interface MentionPickerRef {
  onKeyDown: (event: { event: KeyboardEvent }) => boolean;
}

/**
 * Mention picker component for @username autocomplete.
 * Used with TipTap's Mention extension.
 *
 * NOTE: The primary render path uses `UnifiedMentionPicker` (which handles
 * users, corpuses, documents, annotations, and agents). This component is
 * exported as a standalone picker for consumers that only need user mentions.
 */
export const MentionPicker = forwardRef<MentionPickerRef, MentionPickerProps>(
  ({ users, onSelect, selectedIndex, loading, error, hint }, ref) => {
    const [selected, setSelected] = useState(selectedIndex);

    useEffect(() => {
      setSelected(selectedIndex);
    }, [selectedIndex]);

    useImperativeHandle(ref, () => ({
      onKeyDown: ({ event }: { event: KeyboardEvent }) => {
        // Guard: prevent phantom navigation when users array is empty
        // (e.g. during loading or error states).
        if (users.length === 0) {
          return false;
        }

        if (event.key === "ArrowUp") {
          setSelected((selected - 1 + users.length) % users.length);
          return true;
        }

        if (event.key === "ArrowDown") {
          setSelected((selected + 1) % users.length);
          return true;
        }

        if (event.key === "Enter") {
          if (users[selected]) {
            onSelect(users[selected]);
          }
          return true;
        }

        return false;
      },
    }));

    const getInitials = (username: string) => {
      return username.substring(0, 2).toUpperCase();
    };

    if (loading) {
      return (
        <Container>
          <NoResults>Searching users…</NoResults>
        </Container>
      );
    }

    if (error) {
      return (
        <Container>
          <NoResults>Failed to load users</NoResults>
        </Container>
      );
    }

    if (users.length === 0) {
      return (
        <Container>
          <NoResults>{hint ?? "No users found"}</NoResults>
        </Container>
      );
    }

    return (
      <Container>
        {users.map((user, index) => (
          <MenuItem
            key={user.id}
            $isSelected={index === selected}
            onClick={() => onSelect(user)}
            onMouseEnter={() => setSelected(index)}
          >
            <UserAvatar>{getInitials(user.username)}</UserAvatar>
            <UserInfo>
              <Username>@{user.username}</Username>
              {user.email && <Email>{user.email}</Email>}
            </UserInfo>
          </MenuItem>
        ))}
      </Container>
    );
  }
);

MentionPicker.displayName = "MentionPicker";
