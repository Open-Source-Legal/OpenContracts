import React from "react";
import { useQuery } from "@apollo/client";
import styled from "styled-components";
import { Check } from "lucide-react";
import {
  GET_CORPUS_CATEGORIES,
  GetCorpusCategoriesOutput,
} from "../../graphql/landing-queries";

interface CategorySelectorProps {
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  disabled?: boolean;
}

const Container = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
`;

const ChipsContainer = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  min-height: 2.5rem;
  padding: 0.5rem;
  border: 2px solid #e5e5e5;
  border-radius: 10px;
  background: white;
  transition: all 0.2s ease;

  &:focus-within {
    border-color: #1a1a1a;
    box-shadow: 0 0 0 3px rgba(0, 0, 0, 0.08);
  }

  @media (max-width: 768px) {
    padding: 0.75rem;
    border-radius: 8px;
  }
`;

const CategoryChip = styled.button<{ $selected: boolean; $color?: string }>`
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.75rem;
  border-radius: 100px;
  border: 2px solid
    ${(props) => (props.$selected ? props.$color || "#6366f1" : "#e5e5e5")};
  background: ${(props) =>
    props.$selected ? props.$color || "#6366f1" : "white"};
  color: ${(props) => (props.$selected ? "white" : "#1a1a1a")};
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  outline: none;

  &:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  &:active:not(:disabled) {
    transform: translateY(0);
  }

  .icon {
    margin: 0 !important;
    font-size: 0.875rem;
  }

  @media (max-width: 768px) {
    padding: 0.5rem 1rem;
    font-size: 0.8125rem;
  }
`;

const ColorDot = styled.span<{ $color?: string }>`
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: ${(props) => props.$color || "#6366f1"};
  display: inline-block;
`;

const LoadingText = styled.div`
  color: #999;
  font-size: 0.875rem;
  padding: 0.5rem;
`;

const EmptyText = styled.div`
  color: #999;
  font-size: 0.875rem;
  padding: 0.5rem;
  font-style: italic;
`;

const ErrorText = styled.div`
  color: #dc2626;
  font-size: 0.875rem;
  padding: 0.5rem;
`;

export const CategorySelector: React.FC<CategorySelectorProps> = ({
  selectedIds,
  onChange,
  disabled = false,
}) => {
  const { data, loading, error } = useQuery<GetCorpusCategoriesOutput>(
    GET_CORPUS_CATEGORIES
  );

  const categories =
    data?.corpusCategories?.edges.map((edge) => edge.node) || [];

  const toggleCategory = (categoryId: string) => {
    if (disabled) return;

    if (selectedIds.includes(categoryId)) {
      onChange(selectedIds.filter((id) => id !== categoryId));
    } else {
      onChange([...selectedIds, categoryId]);
    }
  };

  if (error) {
    return (
      <Container>
        <ChipsContainer>
          <ErrorText>Failed to load categories</ErrorText>
        </ChipsContainer>
      </Container>
    );
  }

  if (loading) {
    return (
      <Container>
        <ChipsContainer>
          <LoadingText>Loading categories...</LoadingText>
        </ChipsContainer>
      </Container>
    );
  }

  if (categories.length === 0) {
    return (
      <Container>
        <ChipsContainer>
          <EmptyText>No categories available</EmptyText>
        </ChipsContainer>
      </Container>
    );
  }

  return (
    <Container>
      <ChipsContainer>
        {categories.map((category) => {
          const isSelected = selectedIds.includes(category.id);
          return (
            <CategoryChip
              key={category.id}
              type="button"
              $selected={isSelected}
              $color={category.color}
              onClick={() => toggleCategory(category.id)}
              disabled={disabled}
              title={category.description}
            >
              {!isSelected && <ColorDot $color={category.color} />}
              {isSelected && <Check size={14} />}
              {category.name}
            </CategoryChip>
          );
        })}
      </ChipsContainer>
    </Container>
  );
};
