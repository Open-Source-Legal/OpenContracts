import React, { useMemo } from "react";
import styled, { keyframes } from "styled-components";
import _ from "lodash";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { useReactiveVar } from "@apollo/client";
import { SearchBox, FilterTabs } from "@os-legal/ui";
import type { FilterTabItem } from "@os-legal/ui";
import { Loader2, PenLine, Sparkles } from "lucide-react";

import { selectedAnnotationIds } from "../../graphql/cache";
import { ServerAnnotationType, PageInfo } from "../../types/graphql-api";
import { FetchMoreOnVisible } from "../widgets/infinite_scroll/FetchMoreOnVisible";
import {
  ModernAnnotationCard,
  getAnnotationSource,
  getAnnotationLabelType,
} from "./ModernAnnotationCard";

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export type TypeFilterValue = "all" | "doc" | "text";
export type SourceFilterValue = "all" | "human" | "agent" | "structural";

export interface AnnotationStats {
  total: number;
  docLabels: number;
  textLabels: number;
  humanAnnotated: number;
}

export interface AnnotationsPanelProps {
  // Data
  items: ServerAnnotationType[];
  loading: boolean;
  pageInfo?: PageInfo | null;

  // Filters (controlled)
  typeFilter: TypeFilterValue;
  sourceFilter: SourceFilterValue;
  searchValue: string;

  // Filter handlers
  onTypeFilterChange: (value: TypeFilterValue) => void;
  onSourceFilterChange: (value: SourceFilterValue) => void;
  onSearchChange: (value: string) => void;
  onSearchSubmit?: (value: string) => void;

  // Pagination
  onFetchMore: () => void;

  // Item interaction
  onItemClick: (annotation: ServerAnnotationType) => void;

  // Optional features
  stats?: AnnotationStats;
  showStats?: boolean;
  similarityScores?: Map<string, number>;
  searchError?: Error | null;

  // Customization
  emptyStateMessage?: string;
  isSemanticSearch?: boolean;

  // Style
  style?: React.CSSProperties;
}

// ═══════════════════════════════════════════════════════════════════════════════
// STYLED COMPONENTS
// ═══════════════════════════════════════════════════════════════════════════════

const Container = styled.div`
  display: flex;
  flex-direction: column;
  flex: 1;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: ${OS_LEGAL_COLORS.background};
`;

const FiltersSection = styled.div`
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 1rem 1rem 0;
  background: ${OS_LEGAL_COLORS.background};
`;

const FiltersRow = styled.div`
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
`;

const SearchContainer = styled.div`
  flex: 1;
  max-width: 400px;

  @media (max-width: 768px) {
    max-width: none;
    width: 100%;
  }
`;

const AnnotationsGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;

  @media (max-width: 1024px) {
    grid-template-columns: 1fr;
  }
`;

const AnnotationsListContainer = styled.section`
  flex: 1;
  overflow-y: auto;
  position: relative;
  padding: 1rem;
  min-height: 0; /* Important for flex children to allow shrinking */
`;

const EmptyStateWrapper = styled.div`
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 24px;
  text-align: center;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 16px;
`;

const AnnotationIconWrapper = styled.div`
  width: 64px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  border-radius: 16px;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const EmptyTitle = styled.h3`
  font-size: 18px;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 24px 0 8px;
`;

const EmptyDescription = styled.p`
  font-size: 14px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin: 0;
  max-width: 300px;
`;

const ErrorBanner = styled.div`
  padding: 16px 24px;
  margin-bottom: 16px;
  background-color: ${OS_LEGAL_COLORS.dangerSurface};
  border: 1px solid ${OS_LEGAL_COLORS.dangerBorder};
  border-radius: 8px;
  color: ${OS_LEGAL_COLORS.danger};
  font-size: 14px;
`;

const LoadingMoreIndicator = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 24px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 14px;

  svg {
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    from {
      transform: rotate(0deg);
    }
    to {
      transform: rotate(360deg);
    }
  }
`;

// ── Skeleton loading state ──────────────────────────────────────────────────
// Cards-shaped placeholders that match the eventual ModernAnnotationCard layout.
// Replaces a dark inverted overlay that previously stretched across an
// undefined-height flex container, producing a tall near-black band on the
// otherwise light Browse Annotations page (issue #1560).
const skeletonShimmer = keyframes`
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
`;

const SkeletonBlock = styled.div<{
  $width?: string;
  $height?: string;
  $radius?: string;
}>`
  width: ${(p) => p.$width ?? "100%"};
  height: ${(p) => p.$height ?? "12px"};
  border-radius: ${(p) => p.$radius ?? "4px"};
  background: linear-gradient(
    90deg,
    ${OS_LEGAL_COLORS.surfaceLight} 0%,
    ${OS_LEGAL_COLORS.surfaceHover} 40%,
    ${OS_LEGAL_COLORS.surfaceLight} 80%
  );
  background-size: 200% 100%;
  animation: ${skeletonShimmer} 1.5s ease-in-out infinite;
`;

const SkeletonCard = styled.div`
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 240px;
`;

const SkeletonRow = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
`;

const SkeletonBadges = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
`;

// ═══════════════════════════════════════════════════════════════════════════════
// FILTER TAB CONFIGURATIONS
// ═══════════════════════════════════════════════════════════════════════════════

const TYPE_FILTER_TABS: FilterTabItem[] = [
  { id: "all", label: "All Types" },
  { id: "doc", label: "Doc Labels" },
  { id: "text", label: "Text Labels" },
];

const SOURCE_FILTER_TABS: FilterTabItem[] = [
  { id: "all", label: "All Sources" },
  { id: "human", label: "Human" },
  { id: "agent", label: "AI Agent" },
  { id: "structural", label: "Structural" },
];

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Render a single annotation card skeleton matching the ModernAnnotationCard layout.
 */
const AnnotationCardSkeleton: React.FC = () => (
  <SkeletonCard aria-hidden="true">
    <SkeletonRow>
      <SkeletonBlock $width="40%" $height="14px" />
      <SkeletonBadges>
        <SkeletonBlock $width="24px" $height="24px" $radius="6px" />
        <SkeletonBlock $width="48px" $height="20px" />
      </SkeletonBadges>
    </SkeletonRow>
    <SkeletonBlock $width="35%" $height="20px" />
    <SkeletonBlock $width="100%" $height="120px" $radius="8px" />
    <SkeletonRow>
      <SkeletonBlock $width="45%" $height="12px" />
      <SkeletonBlock $width="80px" $height="12px" />
    </SkeletonRow>
  </SkeletonCard>
);

/**
 * Apply client-side filtering by type and source to annotation items
 */
export function applyLocalFilters(
  items: ServerAnnotationType[],
  typeFilter: TypeFilterValue,
  sourceFilter: SourceFilterValue
): ServerAnnotationType[] {
  let filtered = items;

  // Filter by type (doc vs text)
  if (typeFilter !== "all") {
    filtered = filtered.filter((item) => {
      const labelType = getAnnotationLabelType(item);
      return labelType === typeFilter;
    });
  }

  // Filter by source (human vs agent vs structural)
  if (sourceFilter !== "all") {
    filtered = filtered.filter((item) => {
      const source = getAnnotationSource(item);
      return source === sourceFilter;
    });
  }

  return _.uniqBy(filtered, "id");
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export const AnnotationsPanel: React.FC<AnnotationsPanelProps> = ({
  items,
  loading,
  pageInfo,
  typeFilter,
  sourceFilter,
  searchValue,
  onTypeFilterChange,
  onSourceFilterChange,
  onSearchChange,
  onSearchSubmit,
  onFetchMore,
  onItemClick,
  similarityScores,
  searchError,
  emptyStateMessage,
  isSemanticSearch = false,
  style,
}) => {
  const selected_annotation_ids = useReactiveVar(selectedAnnotationIds);

  // Apply local filters - memoized to avoid re-running _.uniqBy on 2000+ items on every render
  const filteredItems = useMemo(
    () => applyLocalFilters(items, typeFilter, sourceFilter),
    [items, typeFilter, sourceFilter]
  );

  return (
    <Container style={style}>
      {/* Filters Section - Always visible */}
      <FiltersSection>
        <FiltersRow>
          <SearchContainer>
            <SearchBox
              placeholder="Search annotations..."
              value={searchValue}
              onChange={(e) => onSearchChange(e.target.value)}
              onSubmit={onSearchSubmit}
            />
          </SearchContainer>
        </FiltersRow>

        <FiltersRow>
          <FilterTabs
            items={TYPE_FILTER_TABS}
            value={typeFilter}
            onChange={(id) => onTypeFilterChange(id as TypeFilterValue)}
          />
        </FiltersRow>

        <FiltersRow>
          <FilterTabs
            items={SOURCE_FILTER_TABS}
            value={sourceFilter}
            onChange={(id) => onSourceFilterChange(id as SourceFilterValue)}
          />
        </FiltersRow>
      </FiltersSection>

      {/* Annotations Grid */}
      <AnnotationsListContainer>
        {/* Error display for search failures */}
        {searchError && (
          <ErrorBanner>
            <strong>Search failed:</strong>{" "}
            {searchError.message ||
              "An error occurred while searching. Please try again."}
          </ErrorBanner>
        )}

        <AnnotationsGrid>
          {filteredItems.length > 0 ? (
            filteredItems.map((annotation) => (
              <ModernAnnotationCard
                key={annotation.id}
                annotation={annotation}
                onClick={() => onItemClick(annotation)}
                isSelected={selected_annotation_ids.includes(annotation.id)}
                similarityScore={similarityScores?.get(annotation.id)}
              />
            ))
          ) : loading ? (
            <>
              {Array.from({ length: 6 }).map((_unused, idx) => (
                <AnnotationCardSkeleton key={`skeleton-${idx}`} />
              ))}
            </>
          ) : (
            <EmptyStateWrapper>
              <AnnotationIconWrapper>
                {isSemanticSearch ? (
                  <Sparkles size={32} />
                ) : (
                  <PenLine size={32} />
                )}
              </AnnotationIconWrapper>
              <EmptyTitle>
                {isSemanticSearch
                  ? "No matching annotations found"
                  : emptyStateMessage || "No annotations found"}
              </EmptyTitle>
              <EmptyDescription>
                {isSemanticSearch
                  ? "Try a different search query or adjust your filters to find semantically similar annotations."
                  : "Try adjusting your filters or search query to find what you're looking for."}
              </EmptyDescription>
            </EmptyStateWrapper>
          )}
        </AnnotationsGrid>

        {/* Loading more indicator */}
        {loading && filteredItems.length > 0 && (
          <LoadingMoreIndicator>
            <Loader2 size={20} />
            Loading more annotations...
          </LoadingMoreIndicator>
        )}

        {/* Infinite scroll trigger */}
        <FetchMoreOnVisible fetchNextPage={onFetchMore} />
      </AnnotationsListContainer>
    </Container>
  );
};

export default AnnotationsPanel;
