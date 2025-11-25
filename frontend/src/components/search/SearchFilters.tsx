import React from "react";
import styled from "styled-components";
import { color } from "../../theme/colors";

export interface SearchFilters {
  corpusId: string | null;
  conversationType: string | null;
}

interface SearchFiltersProps {
  filters: SearchFilters;
  onChange: (filters: SearchFilters) => void;
  /** Optional corpus ID to pre-filter (disables corpus selector) */
  fixedCorpusId?: string;
  className?: string;
}

const FiltersContainer = styled.div`
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  align-items: center;

  @media (max-width: 640px) {
    flex-direction: column;
    align-items: stretch;
    gap: 0.75rem;
  }
`;

const FilterGroup = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  min-width: 200px;

  @media (max-width: 640px) {
    min-width: 0;
  }
`;

const FilterLabel = styled.label`
  font-size: 0.875rem;
  font-weight: 500;
  color: ${color.N7};
`;

const Select = styled.select`
  padding: 0.5rem 0.75rem;
  border: 1px solid ${color.N4};
  border-radius: 6px;
  background: ${color.N1};
  color: ${color.N10};
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s;

  &:hover:not(:disabled) {
    border-color: ${color.B5};
  }

  &:focus {
    outline: none;
    border-color: ${color.B5};
    box-shadow: 0 0 0 3px rgba(74, 144, 226, 0.1);
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    background: ${color.N2};
  }
`;

const ClearButton = styled.button`
  padding: 0.5rem 1rem;
  border: 1px solid ${color.N4};
  border-radius: 6px;
  background: ${color.N1};
  color: ${color.N7};
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  align-self: flex-end;

  &:hover {
    border-color: ${color.B5};
    background: ${color.N2};
    color: ${color.N10};
  }

  @media (max-width: 640px) {
    align-self: stretch;
  }
`;

/**
 * Search filters component
 * Provides dropdowns for filtering search results by corpus and conversation type
 */
export function SearchFilters({
  filters,
  onChange,
  fixedCorpusId,
  className,
}: SearchFiltersProps) {
  const hasActiveFilters = filters.conversationType !== null;

  const handleClearFilters = () => {
    onChange({
      corpusId: fixedCorpusId || null,
      conversationType: null,
    });
  };

  return (
    <FiltersContainer className={className}>
      <FilterGroup>
        <FilterLabel htmlFor="conversation-type-filter">
          Conversation Type
        </FilterLabel>
        <Select
          id="conversation-type-filter"
          value={filters.conversationType || ""}
          onChange={(e) =>
            onChange({
              ...filters,
              conversationType: e.target.value || null,
            })
          }
        >
          <option value="">All Types</option>
          <option value="thread">Discussions (Threads)</option>
          <option value="chat">Document Chats</option>
        </Select>
      </FilterGroup>

      {hasActiveFilters && (
        <ClearButton onClick={handleClearFilters} type="button">
          Clear Filters
        </ClearButton>
      )}
    </FiltersContainer>
  );
}
