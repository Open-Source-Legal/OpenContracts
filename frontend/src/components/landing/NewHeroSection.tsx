import React, { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@apollo/client";
import styled from "styled-components";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
} from "../../assets/configurations/osLegalStyles";
import {
  SMALL_MOBILE_BREAKPOINT,
  TABLET_BREAKPOINT,
  TABLET_LANDSCAPE_BREAKPOINT,
} from "../../assets/configurations/constants";
import { SearchBox, FilterTabs } from "@os-legal/ui";
import type { FilterTabItem } from "@os-legal/ui";
import { CiteMark } from "../brand/CiteMark";
import {
  GET_CORPUS_CATEGORIES,
  GetCorpusCategoriesOutput,
} from "../../graphql/landing-queries";
import { useLandingContent } from "../../config/landingContent";
import { renderInlineMarkup } from "../../config/landingContent/renderInlineMarkup";

interface NewHeroSectionProps {
  selectedCategory: string | null;
  onCategoryChange: (categoryId: string | null) => void;
}

/**
 * Landing hero — cite rebrand.
 *
 * Headline: "[•] The citation layer / underneath the public record."
 * - first line: slate ink
 * - second line: teal accent
 * - the `[•]` icon mark sits at roughly cap-height of the serif
 *
 * Subhead in muted slate with the word *cite* italicized in Source Serif.
 */

const HeroSection = styled.section`
  margin-bottom: 48px;
`;

const HeroTitleRow = styled.h1`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
  font-size: 42px;
  font-weight: 400;
  line-height: 1.1;
  letter-spacing: -0.5px;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0 0 20px;
  display: flex;
  flex-direction: column;
  gap: 4px;

  @media (max-width: ${TABLET_LANDSCAPE_BREAKPOINT - 1}px) {
    font-size: 36px;
  }
  @media (max-width: ${TABLET_BREAKPOINT - 1}px) {
    font-size: 30px;
  }
`;

const FirstLine = styled.span`
  display: flex;
  align-items: baseline;
  gap: 14px;

  @media (max-width: ${TABLET_BREAKPOINT - 1}px) {
    gap: 10px;
  }
`;

const MarkSlot = styled.span`
  /* Aligns the icon mark with the cap-height of the serif. */
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  transform: translateY(-2px);
`;

const SecondLine = styled.span`
  color: ${OS_LEGAL_COLORS.accent};
`;

const HeroSubtitle = styled.p`
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 14px;
  line-height: 1.6;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin: 0 0 36px;
  max-width: 620px;

  em {
    font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
    font-style: italic;
    font-weight: 400;
    color: ${OS_LEGAL_COLORS.textPrimary};
  }
`;

const SearchContainer = styled.div`
  margin-bottom: 16px;

  /* The @os-legal/ui SearchBox ships a mobile rule that sets the input to
     "flex: 1 1 100%", which forces it onto its own full-width row. That wraps
     the magnifying-glass icon onto a line by itself, above the placeholder
     (and pushes the submit button to a third row). Keep the icon and input on
     the same row on small screens; the full-width button can still wrap below.
     The two-class selector here out-specifies the library's single-class media
     rule, so it wins regardless of stylesheet injection order. */
  @media (max-width: ${SMALL_MOBILE_BREAKPOINT}px) {
    .oc-search-box__input {
      flex: 1 1 auto;
    }
  }
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
  const { hero } = useLandingContent();

  // Fetch categories for FilterTabs
  const { data: categoryData } = useQuery<GetCorpusCategoriesOutput>(
    GET_CORPUS_CATEGORIES
  );

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
      <HeroTitleRow>
        <FirstLine>
          {hero.showMark && (
            <MarkSlot aria-hidden="true">
              <CiteMark size={38} />
            </MarkSlot>
          )}
          {hero.primary}
        </FirstLine>
        <SecondLine>{hero.accent}</SecondLine>
      </HeroTitleRow>
      <HeroSubtitle>{renderInlineMarkup(hero.subheadline)}</HeroSubtitle>

      {/* Search */}
      <SearchContainer>
        <SearchBox
          placeholder={hero.searchPlaceholder}
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
