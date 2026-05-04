import React, { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@apollo/client";
import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { SearchBox, FilterTabs } from "@os-legal/ui";
import type { FilterTabItem } from "@os-legal/ui";
import {
  GET_CORPUS_CATEGORIES,
  GetCorpusCategoriesOutput,
} from "../../graphql/landing-queries";

interface NewHeroSectionProps {
  selectedCategory: string | null;
  onCategoryChange: (categoryId: string | null) => void;
}

/**
 * Minimal Hero Section - matches Storybook design
 *
 * Features:
 * - Clean white background (no gradient)
 * - Serif font (Georgia) for title
 * - "legal knowledge" on second line in teal
 * - Full-width search box
 * - FilterTabs directly below search
 */

const HeroSection = styled.section`
  margin-bottom: 48px;
`;

const HeroTitle = styled.h1`
  font-family: "Georgia", "Times New Roman", serif;
  font-size: 48px;
  font-weight: 400;
  line-height: 1.2;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0 0 20px;

  @media (max-width: 768px) {
    font-size: 36px;
  }
`;

const TealText = styled.span`
  color: ${OS_LEGAL_COLORS.accent};
`;

const HeroSubtitle = styled.p`
  font-size: 18px;
  line-height: 1.6;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin: 0 0 36px;
  max-width: 620px;
`;

const SearchContainer = styled.div`
  margin-bottom: 16px;
`;

const FilterContainer = styled.div`
  margin-bottom: 48px;
`;

export const NewHeroSection: React.FC<NewHeroSectionProps> = ({
  selectedCategory,
  onCategoryChange,
}) => {
  const [searchQuery, setSearchQuery] = useState("");
  const navigate = useNavigate();

  // Fetch categories for FilterTabs
  const { data: categoryData, loading: categoryLoading } =
    useQuery<GetCorpusCategoriesOutput>(GET_CORPUS_CATEGORIES);

  const handleSearchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setSearchQuery(e.target.value);
    },
    []
  );

  const handleSearchSubmit = useCallback(
    (value: string) => {
      if (value.trim()) {
        navigate(`/discover/search?q=${encodeURIComponent(value.trim())}`);
      }
    },
    [navigate]
  );

  // Build FilterTabs items
  const filterItems: FilterTabItem[] = React.useMemo(() => {
    const allItem: FilterTabItem = {
      id: "all",
      label: "All",
    };

    if (!categoryData?.corpusCategories?.edges) {
      return [allItem];
    }

    const categoryItems: FilterTabItem[] =
      categoryData.corpusCategories.edges.map(({ node }) => ({
        id: node.id,
        label: node.name,
        count: node.corpusCount > 0 ? String(node.corpusCount) : undefined,
      }));

    return [allItem, ...categoryItems];
  }, [categoryData]);

  const handleCategoryChange = (id: string) => {
    onCategoryChange(id === "all" ? null : id);
  };

  return (
    <HeroSection>
      <HeroTitle>
        The open platform for
        <br />
        <TealText>legal knowledge</TealText>
      </HeroTitle>
      <HeroSubtitle>
        Collaboratively annotate legislation, contracts, case law, and legal
        knowledge. Built by the community, for the community.
      </HeroSubtitle>

      {/* Search */}
      <SearchContainer>
        <SearchBox
          placeholder="Search across all legal knowledge..."
          value={searchQuery}
          onChange={handleSearchChange}
          onSubmit={handleSearchSubmit}
        />
      </SearchContainer>

      {/* Category Tabs */}
      <FilterContainer>
        <FilterTabs
          items={filterItems}
          value={selectedCategory || "all"}
          onChange={handleCategoryChange}
        />
      </FilterContainer>
    </HeroSection>
  );
};
