import React, { useState, useRef, useEffect } from "react";
import styled from "styled-components";
import { useAtom } from "jotai";
import { ChevronDown, Check } from "lucide-react";
import { threadSortAtom, ThreadSortOption } from "../../atoms/threadAtoms";
import { color } from "../../theme/colors";
import { spacing } from "../../theme/spacing";

const DropdownContainer = styled.div`
  position: relative;
`;

const DropdownButton = styled.button`
  display: flex;
  align-items: center;
  gap: ${spacing.xs};
  padding: ${spacing.xs} ${spacing.sm};
  border: 1px solid ${color.N4};
  border-radius: 6px;
  background: ${color.N1};
  color: ${color.N10};
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    border-color: ${color.B5};
    background: ${color.N2};
  }

  svg {
    width: 16px;
    height: 16px;
  }
`;

const DropdownMenu = styled.div<{ $isOpen: boolean }>`
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  min-width: 180px;
  background: ${color.N1};
  border: 1px solid ${color.N4};
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  opacity: ${(props) => (props.$isOpen ? 1 : 0)};
  visibility: ${(props) => (props.$isOpen ? "visible" : "hidden")};
  transform: ${(props) =>
    props.$isOpen ? "translateY(0)" : "translateY(-8px)"};
  transition: all 0.2s;
  z-index: 100;
`;

const MenuItem = styled.button<{ $isActive: boolean }>`
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: ${spacing.sm} ${spacing.md};
  border: none;
  background: ${(props) => (props.$isActive ? color.B1 : "transparent")};
  color: ${(props) => (props.$isActive ? color.B8 : color.N10)};
  font-size: 14px;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s;

  &:hover {
    background: ${(props) => (props.$isActive ? color.B1 : color.N2)};
  }

  &:first-child {
    border-radius: 6px 6px 0 0;
  }

  &:last-child {
    border-radius: 0 0 6px 6px;
  }

  svg {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
  }
`;

const MenuItemContent = styled.div`
  display: flex;
  flex-direction: column;
  gap: 2px;
`;

const MenuItemLabel = styled.span`
  font-weight: 500;
`;

const MenuItemDescription = styled.span`
  font-size: 12px;
  color: ${color.N6};
`;

interface SortOption {
  value: ThreadSortOption;
  label: string;
  description: string;
}

const SORT_OPTIONS: SortOption[] = [
  {
    value: "pinned",
    label: "Pinned First",
    description: "Show pinned threads at the top",
  },
  {
    value: "newest",
    label: "Newest",
    description: "Most recently created threads",
  },
  {
    value: "active",
    label: "Most Active",
    description: "Recently updated threads",
  },
  {
    value: "upvoted",
    label: "Most Upvoted",
    description: "Threads with most engagement",
  },
];

export interface ThreadSortDropdownProps {
  /** Optional className for styling */
  className?: string;
}

/**
 * Dropdown for sorting thread list
 * Updates threadSortAtom when selection changes
 */
export function ThreadSortDropdown({ className }: ThreadSortDropdownProps) {
  const [sortBy, setSortBy] = useAtom(threadSortAtom);
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const currentOption = SORT_OPTIONS.find((opt) => opt.value === sortBy);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => {
        document.removeEventListener("mousedown", handleClickOutside);
      };
    }
  }, [isOpen]);

  // Close on Escape key
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
      return () => {
        document.removeEventListener("keydown", handleKeyDown);
      };
    }
  }, [isOpen]);

  const handleSelect = (value: ThreadSortOption) => {
    setSortBy(value);
    setIsOpen(false);
  };

  return (
    <DropdownContainer ref={dropdownRef} className={className}>
      <DropdownButton
        onClick={() => setIsOpen(!isOpen)}
        aria-label="Sort threads"
        aria-expanded={isOpen}
        aria-haspopup="true"
      >
        <span>Sort: {currentOption?.label}</span>
        <ChevronDown />
      </DropdownButton>

      <DropdownMenu $isOpen={isOpen} role="menu">
        {SORT_OPTIONS.map((option) => (
          <MenuItem
            key={option.value}
            $isActive={sortBy === option.value}
            onClick={() => handleSelect(option.value)}
            role="menuitem"
            aria-label={`Sort by ${option.label}`}
          >
            <MenuItemContent>
              <MenuItemLabel>{option.label}</MenuItemLabel>
              <MenuItemDescription>{option.description}</MenuItemDescription>
            </MenuItemContent>
            {sortBy === option.value && <Check />}
          </MenuItem>
        ))}
      </DropdownMenu>
    </DropdownContainer>
  );
}
