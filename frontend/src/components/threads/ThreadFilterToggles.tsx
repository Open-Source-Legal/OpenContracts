import React from "react";
import styled from "styled-components";
import { useAtom } from "jotai";
import { Lock, Trash2 } from "lucide-react";
import { threadFiltersAtom } from "../../atoms/threadAtoms";
import { color } from "../../theme/colors";
import { spacing } from "../../theme/spacing";

const Container = styled.div`
  display: flex;
  align-items: center;
  gap: ${spacing.sm};
  flex-wrap: wrap;
`;

const Label = styled.span`
  font-size: 14px;
  color: ${color.N7};
  font-weight: 500;
`;

const ToggleButton = styled.button<{ $isActive: boolean }>`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid ${(props) => (props.$isActive ? color.B5 : color.N4)};
  border-radius: 6px;
  background: ${(props) => (props.$isActive ? color.B1 : color.N1)};
  color: ${(props) => (props.$isActive ? color.B8 : color.N7)};
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    border-color: ${(props) => (props.$isActive ? color.B6 : color.N5)};
    background: ${(props) => (props.$isActive ? color.B2 : color.N2)};
  }

  svg {
    width: 14px;
    height: 14px;
  }
`;

export interface ThreadFilterTogglesProps {
  /** Show moderator-only filters (e.g., deleted threads) */
  showModeratorFilters?: boolean;
  /** Optional className for styling */
  className?: string;
}

/**
 * Toggle buttons for filtering thread list
 * Updates threadFiltersAtom when toggles change
 */
export function ThreadFilterToggles({
  showModeratorFilters = false,
  className,
}: ThreadFilterTogglesProps) {
  const [filters, setFilters] = useAtom(threadFiltersAtom);

  const toggleShowLocked = () => {
    setFilters({ ...filters, showLocked: !filters.showLocked });
  };

  const toggleShowDeleted = () => {
    setFilters({ ...filters, showDeleted: !filters.showDeleted });
  };

  return (
    <Container className={className}>
      <Label>Show:</Label>

      <ToggleButton
        $isActive={filters.showLocked}
        onClick={toggleShowLocked}
        aria-label={
          filters.showLocked ? "Hide locked threads" : "Show locked threads"
        }
        aria-pressed={filters.showLocked}
      >
        <Lock />
        <span>Locked</span>
      </ToggleButton>

      {showModeratorFilters && (
        <ToggleButton
          $isActive={filters.showDeleted}
          onClick={toggleShowDeleted}
          aria-label={
            filters.showDeleted
              ? "Hide deleted threads"
              : "Show deleted threads"
          }
          aria-pressed={filters.showDeleted}
        >
          <Trash2 />
          <span>Deleted</span>
        </ToggleButton>
      )}
    </Container>
  );
}
