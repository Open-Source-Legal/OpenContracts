import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import styled from "styled-components";
import { motion, AnimatePresence } from "framer-motion";
import { Loader, Button, Icon } from "semantic-ui-react";
import { toast } from "react-toastify";
import { List, useListCallbackRef, useDynamicRowHeight } from "react-window";
import AutoSizer from "react-virtualized-auto-sizer";
import {
  UnifiedContentItem,
  ContentFilters,
  SortOption,
  ContentItemType,
  Note,
} from "./types";
import { useAllAnnotations } from "../../../annotator/hooks/useAllAnnotations";
import { usePdfAnnotations } from "../../../annotator/hooks/AnnotationHooks";
import { useAnnotationDisplay } from "../../../annotator/context/UISettingsAtom";
import { useAnnotationControls } from "../../../annotator/context/UISettingsAtom";
import {
  useTextSearchState,
  useSearchText,
  useDocumentState,
} from "../../../annotator/context/DocumentAtom";
import { useCorpusState } from "../../../annotator/context/CorpusAtom";
import { EmptyState } from "../StyledContainers";
import { FileText } from "lucide-react";
import { FetchMoreOnVisible } from "../../../widgets/infinite_scroll/FetchMoreOnVisible";
import { ContentItemRenderer } from "./ContentItemRenderer";
import { RelationshipActionModal } from "./RelationshipActionModal";
import { useRelationshipActions } from "../../../annotator/hooks/useRelationshipActions";

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
  /** Document ID - required for creating relationships */
  documentId?: string;
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
  position: relative;

  /* Pretty scrollbar for react-window */
  & > div > div::-webkit-scrollbar {
    width: 8px;
  }
  & > div > div::-webkit-scrollbar-track {
    background: #f1f5f9;
  }
  & > div > div::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 4px;
    &:hover {
      background: #94a3b8;
    }
  }
`;

const PageHeader = styled.div`
  background: linear-gradient(to right, #f8fafc 0%, #ffffff 100%);
  backdrop-filter: blur(8px);
  padding: 1rem 1.25rem;
  margin: 0 -0.5rem;
  border-bottom: 2px solid #e2e8f0;
  border-top: 1px solid #f1f5f9;
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

const SelectionToolbar = styled(motion.div)`
  position: sticky;
  top: 0;
  z-index: 20;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  color: white;
  padding: 0.75rem 1rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  border-radius: 0;

  .selection-info {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    font-weight: 600;
  }

  .selection-actions {
    display: flex;
    gap: 0.5rem;
  }
`;

// Base heights for different content types - includes padding, margins, and chrome
const ESTIMATED_HEIGHTS = {
  pageHeader: 90,
  note: 200,
  annotation: 160, // Accounts for padding (0.875rem top/bottom) + margin (0.5rem top/bottom) + content
  relationship: 220,
  search: 140,
};

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
  documentId: propDocumentId,
}) => {
  /* Data sources - bypass showSelectedOnly filter for feed */
  const allAnnotations = useAllAnnotations();
  const { pdfAnnotations } = usePdfAnnotations();
  const allRelationships = pdfAnnotations?.relations ?? [];

  // Get display settings for structural filtering only (ignore showSelectedOnly)
  const { showStructural } = useAnnotationDisplay();
  const { spanLabelsToView } = useAnnotationControls();

  const { textSearchMatches } = useTextSearchState();
  const { searchText } = useSearchText();
  const { activeDocument } = useDocumentState();
  const { selectedCorpus } = useCorpusState();

  // Use prop documentId if available, otherwise fall back to atom
  const documentId = propDocumentId || activeDocument?.id;

  /* Multi-select state */
  const [selectedAnnotationIds, setSelectedAnnotationIds] = useState<string[]>(
    []
  );
  const [showRelationshipModal, setShowRelationshipModal] = useState(false);

  /* Relationship actions hook */
  const {
    addAnnotationsToRelationship,
    createRelationship,
    isLoading: relationshipActionLoading,
  } = useRelationshipActions();

  /* Clear selection when filters change */
  useEffect(() => {
    setSelectedAnnotationIds([]);
  }, [filters, sortBy]);

  /* Ref for List and dynamic height management */
  const [listRef, setListRef] = useListCallbackRef();
  const rowHeightManager = useDynamicRowHeight({
    defaultRowHeight: ESTIMATED_HEIGHTS.annotation,
  });

  /* Aggregate and filter content - apply all filters EXCEPT showSelectedOnly */
  const contentItems = useMemo(() => {
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

    // Add annotations if enabled - apply structural and label filters only
    if (filters.contentTypes.has("annotation") && allAnnotations) {
      allAnnotations.forEach((ann) => {
        // Filter structural annotations based on showStructural setting
        if (ann.structural && !showStructural) {
          return;
        }

        // Apply label filter if present
        const labelFilterActive =
          spanLabelsToView && spanLabelsToView.length > 0
            ? new Set(spanLabelsToView.map((l) => l.id))
            : null;

        if (
          labelFilterActive &&
          !labelFilterActive.has(ann.annotationLabel.id)
        ) {
          return;
        }

        // Also check filters.annotationFilters if provided
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

    // Add relationships if enabled - apply structural filter only
    if (filters.contentTypes.has("relationship")) {
      allRelationships.forEach((rel) => {
        // Filter structural relationships based on showStructural setting
        if (rel.structural && !showStructural) {
          return;
        }

        // Calculate minimum page from source/target annotations
        let minPage = 1;
        const allAnnotationIds = [...rel.sourceIds, ...rel.targetIds];

        allAnnotationIds.forEach((id) => {
          const ann = allAnnotations?.find((a) => a.id === id);
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
    allAnnotations,
    allRelationships,
    showStructural,
    spanLabelsToView,
    textSearchMatches,
    searchText,
    filters,
    sortBy,
  ]);

  /* Create flattened list with page headers for virtualization */
  type VirtualItem =
    | { type: "header"; pageNumber: number; id: string }
    | { type: "content"; item: UnifiedContentItem; id: string };

  const virtualItems = useMemo(() => {
    const items: VirtualItem[] = [];
    let currentPage = -1;

    contentItems.forEach((item) => {
      // Add page header if this is a new page
      if (item.pageNumber !== currentPage) {
        currentPage = item.pageNumber;
        items.push({
          type: "header",
          pageNumber: currentPage,
          id: `header-${currentPage}`,
        });
      }

      // Add content item
      items.push({
        type: "content",
        item,
        id: item.id,
      });
    });

    return items;
  }, [contentItems]);

  /* Optionally reset scroll when filters change - commented out to preserve position */
  // useEffect(() => {
  //   if (listRef) {
  //     listRef.scrollToRow({ index: 0 });
  //   }
  // }, [filters, sortBy, listRef]);

  /* Selection handlers - MUST be before early returns */
  const handleToggleSelection = useCallback((annotationId: string) => {
    setSelectedAnnotationIds((prev) => {
      if (prev.includes(annotationId)) {
        return prev.filter((id) => id !== annotationId);
      } else {
        return [...prev, annotationId];
      }
    });
  }, []);

  const handleClearSelection = useCallback(() => {
    setSelectedAnnotationIds([]);
  }, []);

  const handleSelectAll = useCallback(() => {
    // Select all annotations from current items
    const annotationIds = contentItems
      .filter((item) => item.type === "annotation")
      .map((item) => (item.data as any).id);
    setSelectedAnnotationIds(annotationIds);
  }, [contentItems]);

  /* Height function with dynamic measurement fallback */
  const rowHeight = useMemo(() => {
    return {
      ...rowHeightManager,
      getRowHeight: (index: number) => {
        // First check if we have a measured height
        const measured = rowHeightManager.getRowHeight(index);
        if (measured !== undefined) return measured;

        // Otherwise estimate
        const virtualItem = virtualItems[index];
        if (!virtualItem) return ESTIMATED_HEIGHTS.annotation;

        if (virtualItem.type === "header") {
          return ESTIMATED_HEIGHTS.pageHeader;
        }

        const item = virtualItem.item;
        switch (item.type) {
          case "note": {
            const note = item.data as any;
            const contentLength = note.content?.length || 0;
            return (
              ESTIMATED_HEIGHTS.note + Math.floor(contentLength / 100) * 20
            );
          }
          case "annotation": {
            const ann = item.data as any;
            const textLength = ann.rawText?.length || 0;
            const extraLines = Math.floor(textLength / 50);
            return ESTIMATED_HEIGHTS.annotation + extraLines * 20;
          }
          case "relationship": {
            const rel = item.data as any;
            const sourceCount = rel.sourceIds?.length || 0;
            const targetCount = rel.targetIds?.length || 0;
            return (
              ESTIMATED_HEIGHTS.relationship + (sourceCount + targetCount) * 10
            );
          }
          case "search":
            return ESTIMATED_HEIGHTS.search;
          default:
            return ESTIMATED_HEIGHTS.annotation;
        }
      },
      getAverageRowHeight: () => ESTIMATED_HEIGHTS.annotation,
    };
  }, [virtualItems, rowHeightManager]);

  /* Row renderer component for List */
  const RowComponent = ({
    index,
    style,
  }: {
    index: number;
    style: React.CSSProperties;
  }): React.ReactElement => {
    const virtualItem = virtualItems[index];
    if (!virtualItem) return <div style={style} />;

    const hasCorpus = !!selectedCorpus?.id;

    if (virtualItem.type === "header") {
      return (
        <div style={style}>
          <PageHeader>
            <span>Page</span>
            <PageNumber>{virtualItem.pageNumber}</PageNumber>
          </PageHeader>
        </div>
      );
    }

    // Render content item
    const item = virtualItem.item;
    const isAnnotation = item.type === "annotation";
    const annotationId = isAnnotation ? (item.data as any).id : null;
    const isSelected =
      annotationId && selectedAnnotationIds.includes(annotationId);

    return (
      <div style={style}>
        <ContentWrapper
          style={{
            background: isSelected ? "rgba(59, 130, 246, 0.1)" : undefined,
            borderLeft: isSelected ? "4px solid #3b82f6" : undefined,
          }}
        >
          <ContentItemRenderer
            item={item}
            onSelect={() => {
              onItemSelect?.(item);
            }}
            onToggleMultiSelect={
              isAnnotation && annotationId && !readOnly && hasCorpus
                ? () => handleToggleSelection(annotationId)
                : undefined
            }
            isMultiSelected={isSelected}
            readOnly={readOnly}
          />
        </ContentWrapper>
      </div>
    );
  };

  /* Render loading state */
  if (isLoading) {
    return (
      <FeedContainer>
        <Loader active inline="centered" content="Loading content..." />
      </FeedContainer>
    );
  }

  /* Render empty state */
  if (contentItems.length === 0) {
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

  /* Relationship modal handlers */
  const handleAddToExistingRelationship = async (
    relationshipId: string,
    role: "source" | "target"
  ) => {
    await addAnnotationsToRelationship(
      relationshipId,
      selectedAnnotationIds,
      role
    );
    setSelectedAnnotationIds([]);
  };

  const handleCreateNewRelationship = async (
    labelId: string,
    sourceIds: string[],
    targetIds: string[]
  ) => {
    if (!documentId || !selectedCorpus?.id) {
      console.error("Missing document or corpus ID", {
        documentId,
        corpusId: selectedCorpus?.id,
      });
      toast.error("Missing document or corpus ID");
      return;
    }
    await createRelationship(
      sourceIds,
      targetIds,
      labelId,
      selectedCorpus.id,
      documentId
    );
    setSelectedAnnotationIds([]);
  };

  /* Only show relationship actions if corpus is available */
  const hasCorpus = !!selectedCorpus?.id;

  return (
    <FeedContainer data-testid="unified-content-feed">
      {/* Selection Toolbar - only show if corpus is available */}
      <AnimatePresence>
        {hasCorpus && selectedAnnotationIds.length > 0 && (
          <SelectionToolbar
            initial={{ y: -60, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -60, opacity: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
          >
            <div className="selection-info">
              <Icon name="check circle" />
              <span>
                {selectedAnnotationIds.length} annotation
                {selectedAnnotationIds.length !== 1 ? "s" : ""} selected
              </span>
            </div>
            <div className="selection-actions">
              <Button
                size="small"
                inverted
                onClick={() => setShowRelationshipModal(true)}
                disabled={relationshipActionLoading}
              >
                <Icon name="linkify" />
                Add to Relationship
              </Button>
              <Button
                size="small"
                inverted
                onClick={handleSelectAll}
                disabled={
                  contentItems.filter((item) => item.type === "annotation")
                    .length === selectedAnnotationIds.length
                }
              >
                <Icon name="check square outline" />
                Select All
              </Button>
              <Button size="small" inverted onClick={handleClearSelection}>
                <Icon name="close" />
                Clear
              </Button>
            </div>
          </SelectionToolbar>
        )}
      </AnimatePresence>

      <FeedViewport data-testid="feed-viewport">
        <div style={{ width: "100%", height: "100%" }}>
          <AutoSizer>
            {({ height, width }: { height: number; width: number }) => (
              <div
                style={{
                  width: `${width}px`,
                  height: `${height}px`,
                  position: "relative",
                }}
              >
                <List<Record<string, never>>
                  listRef={setListRef}
                  defaultHeight={height}
                  rowCount={virtualItems.length}
                  rowHeight={rowHeight}
                  rowComponent={RowComponent}
                  rowProps={{}}
                  overscanCount={5}
                  style={{
                    width: "100%",
                    height: "100%",
                  }}
                />
              </div>
            )}
          </AutoSizer>
        </div>
      </FeedViewport>

      {/* Relationship Action Modal */}
      {hasCorpus && !readOnly && (
        <RelationshipActionModal
          open={showRelationshipModal}
          onClose={() => setShowRelationshipModal(false)}
          selectedAnnotationIds={selectedAnnotationIds}
          existingRelationships={allRelationships}
          corpusId={selectedCorpus.id}
          documentId={documentId || ""}
          annotations={allAnnotations}
          onAddToExisting={handleAddToExistingRelationship}
          onCreate={handleCreateNewRelationship}
        />
      )}
    </FeedContainer>
  );
};
