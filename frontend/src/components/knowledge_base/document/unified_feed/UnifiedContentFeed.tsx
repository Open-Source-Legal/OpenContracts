import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import styled from "styled-components";
import { motion, AnimatePresence } from "framer-motion";
import { Loader } from "semantic-ui-react";
import {
  UnifiedContentItem,
  ContentFilters,
  SortOption,
  ContentItemType,
  Note,
} from "./types";
import { useVisibleAnnotations } from "../../../annotator/hooks/useVisibleAnnotations";
import { usePdfAnnotations } from "../../../annotator/hooks/AnnotationHooks";
import {
  useTextSearchState,
  useSearchText,
} from "../../../annotator/context/DocumentAtom";
import { EmptyState } from "../StyledContainers";
import { FileText } from "lucide-react";
import { FetchMoreOnVisible } from "../../../widgets/infinite_scroll/FetchMoreOnVisible";
import { ContentItemRenderer } from "./ContentItemRenderer";

interface UnifiedContentFeedProps {
  /** Document notes */
  notes: Note[];
  /** Current filters */
  filters: ContentFilters;
  /** Current sort option */
  sortBy: SortOption;
  /** Whether feed is loading */
  isLoading?: boolean;
  /** Callback when an item is selected */
  onItemSelect?: (item: UnifiedContentItem) => void;
  /** Fetch more callback for infinite scroll */
  fetchMore?: () => Promise<void>;
  /** Read-only mode disables editing capabilities */
  readOnly?: boolean;
}

/* Styled Components */
const FeedContainer = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
`;

const FeedViewport = styled.div`
  flex: 1 1 auto;
  overflow-y: auto;
  position: relative;

  /* Pretty scrollbar */
  &::-webkit-scrollbar {
    width: 8px;
  }
  &::-webkit-scrollbar-track {
    background: #f1f5f9;
  }
  &::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 4px;
    &:hover {
      background: #94a3b8;
    }
  }
`;

const PageHeader = styled.div`
  position: sticky;
  top: 0;
  background: linear-gradient(to right, #f8fafc 0%, #ffffff 100%);
  backdrop-filter: blur(8px);
  padding: 1rem 1.25rem;
  margin: 0 -0.5rem;
  border-bottom: 2px solid #e2e8f0;
  border-top: 1px solid #f1f5f9;
  z-index: 10;
  font-weight: 600;
  font-size: 0.9375rem;
  color: #334155;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04);

  &:first-child {
    border-top: none;
  }
`;

const PageNumber = styled.span`
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  color: white;
  padding: 0.25rem 0.75rem;
  border-radius: 9999px;
  font-size: 0.8125rem;
  font-weight: 700;
  box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
`;

const ContentWrapper = styled.div`
  padding: 0.75rem 0.5rem;
`;

const DEFAULT_ROW_HEIGHT = 80; // px
const OVERSCAN_ROWS = 3;

/**
 * UnifiedContentFeed component that aggregates and displays all content types
 * in a virtualized, page-sorted feed.
 */
export const UnifiedContentFeed: React.FC<UnifiedContentFeedProps> = ({
  notes,
  filters,
  sortBy,
  isLoading = false,
  onItemSelect,
  fetchMore,
  readOnly = false,
}) => {
  /* Data sources */
  const visibleAnnotations = useVisibleAnnotations();
  const { pdfAnnotations } = usePdfAnnotations();
  const { textSearchMatches } = useTextSearchState();
  const { searchText } = useSearchText();

  /* Aggregate and filter content */
  const items = useMemo(() => {
    const unified: UnifiedContentItem[] = [];

    // Add notes (all on page 1) if enabled
    if (filters.contentTypes.has("note")) {
      notes.forEach((note) => {
        // Apply search filter if present
        if (filters.searchQuery) {
          const query = filters.searchQuery.toLowerCase();
          const matchesSearch =
            note.title?.toLowerCase().includes(query) ||
            note.content.toLowerCase().includes(query) ||
            note.creator.email.toLowerCase().includes(query);
          if (!matchesSearch) return;
        }

        unified.push({
          id: `note-${note.id}`,
          type: "note",
          pageNumber: 1,
          data: note,
          timestamp: new Date(note.created),
        });
      });
    }

    // Add annotations if enabled
    if (filters.contentTypes.has("annotation") && visibleAnnotations) {
      visibleAnnotations.forEach((ann) => {
        // Apply label filter if present
        if (
          filters.annotationFilters?.labels &&
          filters.annotationFilters.labels.size > 0 &&
          !filters.annotationFilters.labels.has(ann.annotationLabel.id)
        ) {
          return;
        }

        // Apply search filter if present
        if (filters.searchQuery) {
          const query = filters.searchQuery.toLowerCase();
          const matchesSearch =
            ann.rawText?.toLowerCase().includes(query) ||
            (ann.annotationLabel.text &&
              ann.annotationLabel.text.toLowerCase().includes(query));
          if (!matchesSearch) return;
        }

        unified.push({
          id: `ann-${ann.id}`,
          type: "annotation",
          pageNumber: ann.page !== undefined ? ann.page + 1 : 1, // Convert 0-based to 1-based
          data: ann,
          timestamp: undefined, // Annotations don't have created field
        });
      });
    }

    // Add relationships if enabled
    if (filters.contentTypes.has("relationship") && pdfAnnotations?.relations) {
      const relationships = filters.relationshipFilters?.showStructural
        ? pdfAnnotations.relations
        : pdfAnnotations.relations.filter((rel) => !rel.structural);

      relationships.forEach((rel) => {
        // Calculate minimum page from source/target annotations
        let minPage = 1;
        const allAnnotationIds = [...rel.sourceIds, ...rel.targetIds];

        allAnnotationIds.forEach((id) => {
          const ann = visibleAnnotations?.find((a) => a.id === id);
          if (ann && ann.page !== undefined) {
            const annPage = ann.page + 1; // Convert 0-based to 1-based
            minPage = minPage === 1 ? annPage : Math.min(minPage, annPage);
          }
        });

        // Apply search filter if present
        if (filters.searchQuery) {
          const query = filters.searchQuery.toLowerCase();
          const matchesSearch =
            rel.label.text && rel.label.text.toLowerCase().includes(query);
          if (!matchesSearch) return;
        }

        unified.push({
          id: `rel-${rel.id}`,
          type: "relationship",
          pageNumber: minPage,
          data: rel,
        });
      });
    }

    // Add search results if enabled and there's an active search
    if (
      filters.contentTypes.has("search") &&
      searchText &&
      textSearchMatches?.length > 0
    ) {
      textSearchMatches.forEach((result, idx) => {
        const pageNumber = "start_page" in result ? result.start_page : 1;

        unified.push({
          id: `search-${idx}`,
          type: "search",
          pageNumber: pageNumber || 1,
          data: result,
        });
      });
    }

    // Sort items based on selected option
    return unified.sort((a, b) => {
      switch (sortBy) {
        case "page":
          // Primary sort by page, secondary by type
          if (a.pageNumber !== b.pageNumber) {
            return a.pageNumber - b.pageNumber;
          }
          return a.type.localeCompare(b.type);

        case "type":
          // Primary sort by type, secondary by page
          if (a.type !== b.type) {
            return a.type.localeCompare(b.type);
          }
          return a.pageNumber - b.pageNumber;

        case "date":
          // Sort by timestamp (newest first), fallback to page
          const aTime = a.timestamp?.getTime() || 0;
          const bTime = b.timestamp?.getTime() || 0;
          if (aTime !== bTime) {
            return bTime - aTime;
          }
          return a.pageNumber - b.pageNumber;

        default:
          return 0;
      }
    });
  }, [
    notes,
    visibleAnnotations,
    pdfAnnotations.relations,
    textSearchMatches,
    searchText,
    filters,
    sortBy,
  ]);

  /* Group items by page for display */
  const itemsByPage = useMemo(() => {
    const grouped = new Map<number, UnifiedContentItem[]>();

    items.forEach((item) => {
      const page = item.pageNumber;
      if (!grouped.has(page)) {
        grouped.set(page, []);
      }
      grouped.get(page)!.push(item);
    });

    return grouped;
  }, [items]);

  /* Virtualization state */
  const viewportRef = useRef<HTMLDivElement>(null);
  const [visibleRange, setVisibleRange] = useState<[number, number]>([0, 10]);
  const rowCount = items.length + (fetchMore ? 1 : 0);

  const [rowHeights, setRowHeights] = useState<number[]>(
    new Array(rowCount).fill(DEFAULT_ROW_HEIGHT)
  );

  /* Keep row heights array in sync */
  useEffect(() => {
    setRowHeights((prev) => {
      if (prev.length === rowCount) return prev;
      const next = [...prev];
      while (next.length < rowCount) next.push(DEFAULT_ROW_HEIGHT);
      return next.slice(0, rowCount);
    });
  }, [rowCount]);

  /* Calculate cumulative heights */
  const cumulative = useMemo(() => {
    const out: number[] = [0];
    for (let i = 0; i < rowHeights.length; i++) {
      out.push(out[i] + rowHeights[i]);
    }
    return out;
  }, [rowHeights]);

  const containerHeight = cumulative[cumulative.length - 1];

  /* Update visible range based on scroll */
  const updateRange = useCallback(() => {
    const vp = viewportRef.current;
    if (!vp) return;

    const scrollTop = vp.scrollTop || 0;
    const vpHeight = vp.clientHeight || 600; // Default height for test environments

    let first = 0;
    while (first < rowCount && cumulative[first + 1] <= scrollTop) first++;

    let last = first;
    while (last < rowCount && cumulative[last] < scrollTop + vpHeight) last++;
    last = Math.min(last, rowCount - 1);

    const start = Math.max(0, first - OVERSCAN_ROWS);
    const end = Math.min(rowCount - 1, last + OVERSCAN_ROWS);

    if (start !== visibleRange[0] || end !== visibleRange[1]) {
      setVisibleRange([start, end]);
    }
  }, [cumulative, rowCount, visibleRange]);

  /* Attach scroll listener */
  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;

    updateRange();
    const onScroll = () => requestAnimationFrame(updateRange);

    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [updateRange]);

  /* Force initial range calculation after mount */
  useEffect(() => {
    // Use setTimeout to ensure DOM is ready
    const timer = setTimeout(() => {
      updateRange();
    }, 0);
    return () => clearTimeout(timer);
  }, [updateRange]);

  /* Measure row heights */
  const measureRow = useCallback(
    (index: number, element: HTMLDivElement | null) => {
      if (!element) return;

      const measured = Math.round(element.getBoundingClientRect().height);
      setRowHeights((prev) => {
        if (index >= prev.length) return prev;
        if (Math.abs(prev[index] - measured) < 1) return prev;
        const next = [...prev];
        next[index] = measured;
        return next;
      });
    },
    []
  );

  /* Render loading state */
  if (isLoading) {
    return (
      <FeedContainer>
        <Loader active inline="centered" content="Loading content..." />
      </FeedContainer>
    );
  }

  /* Render empty state */
  if (items.length === 0) {
    return (
      <FeedContainer data-testid="unified-content-feed-empty">
        <EmptyState
          icon={<FileText size={40} />}
          title="No content found"
          description="Try adjusting your filters or search query"
        />
      </FeedContainer>
    );
  }

  /* Track current page for headers */
  let currentPage = -1;

  return (
    <FeedContainer data-testid="unified-content-feed">
      <FeedViewport ref={viewportRef} data-testid="feed-viewport">
        <div
          style={{ position: "relative", height: containerHeight }}
          data-testid="feed-content"
        >
          {Array.from(
            { length: visibleRange[1] - visibleRange[0] + 1 },
            (_, i) => {
              const rowIdx = visibleRange[0] + i;

              // Handle fetch more sentinel
              if (rowIdx === items.length && fetchMore) {
                return (
                  <div
                    key="fetch-more"
                    style={{
                      position: "absolute",
                      top: cumulative[rowIdx],
                      width: "100%",
                    }}
                  >
                    <FetchMoreOnVisible
                      fetchNextPage={fetchMore}
                      fetchWithoutMotion
                    />
                  </div>
                );
              }

              if (rowIdx >= items.length) return null;

              const item = items[rowIdx];
              const showPageHeader = item.pageNumber !== currentPage;
              if (showPageHeader) {
                currentPage = item.pageNumber;
              }

              return (
                <div
                  key={item.id}
                  ref={(el) => measureRow(rowIdx, el)}
                  style={{
                    position: "absolute",
                    top: cumulative[rowIdx],
                    width: "100%",
                  }}
                >
                  {showPageHeader && (
                    <PageHeader>
                      <span>Page</span>
                      <PageNumber>{item.pageNumber}</PageNumber>
                    </PageHeader>
                  )}
                  <ContentWrapper>
                    <ContentItemRenderer
                      item={item}
                      onSelect={() => onItemSelect?.(item)}
                      readOnly={readOnly}
                    />
                  </ContentWrapper>
                </div>
              );
            }
          )}
        </div>
      </FeedViewport>
    </FeedContainer>
  );
};
