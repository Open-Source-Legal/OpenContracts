import React from "react";
import styled from "styled-components";
import { Search, X } from "lucide-react";
import { color } from "../../theme/colors";

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  placeholder?: string;
  autoFocus?: boolean;
  className?: string;
}

const SearchBarContainer = styled.div`
  position: relative;
  width: 100%;
`;

const Input = styled.input`
  width: 100%;
  padding: 0.875rem 3rem 0.875rem 3rem;
  border: 2px solid ${color.N4};
  border-radius: 8px;
  font-size: 1rem;
  color: ${color.N10};
  background: ${color.N1};
  transition: all 0.2s;

  &:focus {
    outline: none;
    border-color: ${color.B5};
    box-shadow: 0 0 0 3px rgba(74, 144, 226, 0.1);
  }

  &::placeholder {
    color: ${color.N5};
  }

  @media (max-width: 640px) {
    font-size: 0.9375rem;
    padding: 0.75rem 2.75rem;
  }
`;

const SearchIcon = styled.div`
  position: absolute;
  left: 1rem;
  top: 50%;
  transform: translateY(-50%);
  color: ${color.N6};
  pointer-events: none;
  display: flex;
  align-items: center;

  svg {
    width: 20px;
    height: 20px;
  }

  @media (max-width: 640px) {
    left: 0.875rem;

    svg {
      width: 18px;
      height: 18px;
    }
  }
`;

const ClearButton = styled.button`
  position: absolute;
  right: 1rem;
  top: 50%;
  transform: translateY(-50%);
  padding: 0.25rem;
  border: none;
  background: transparent;
  color: ${color.N6};
  cursor: pointer;
  border-radius: 4px;
  display: flex;
  align-items: center;
  transition: all 0.2s;

  &:hover {
    background: ${color.N3};
    color: ${color.N10};
  }

  svg {
    width: 16px;
    height: 16px;
  }

  @media (max-width: 640px) {
    right: 0.875rem;
  }
`;

/**
 * Search input bar component
 * Provides a search input with icons and clear functionality
 */
export function SearchBar({
  value,
  onChange,
  onSubmit,
  placeholder = "Search discussions...",
  autoFocus = false,
  className,
}: SearchBarProps) {
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      onSubmit();
    }
  };

  return (
    <SearchBarContainer className={className}>
      <SearchIcon aria-hidden="true">
        <Search />
      </SearchIcon>

      <Input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        autoFocus={autoFocus}
        aria-label="Search query"
      />

      {value && (
        <ClearButton
          onClick={() => onChange("")}
          aria-label="Clear search"
          type="button"
        >
          <X />
        </ClearButton>
      )}
    </SearchBarContainer>
  );
}
