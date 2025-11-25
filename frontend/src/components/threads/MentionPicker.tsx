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
}

export interface MentionPickerRef {
  onKeyDown: (event: { event: KeyboardEvent }) => boolean;
}

/**
 * Mention picker component for @username autocomplete
 * Used with TipTap's Mention extension
 */
export const MentionPicker = forwardRef<MentionPickerRef, MentionPickerProps>(
  ({ users, onSelect, selectedIndex }, ref) => {
    const [selected, setSelected] = useState(selectedIndex);

    useEffect(() => {
      setSelected(selectedIndex);
    }, [selectedIndex]);

    useImperativeHandle(ref, () => ({
      onKeyDown: ({ event }: { event: KeyboardEvent }) => {
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

    if (users.length === 0) {
      return (
        <Container>
          <NoResults>No users found</NoResults>
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
