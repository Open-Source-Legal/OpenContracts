import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import {
  NetworkStatus,
  useMutation,
  useQuery,
  useReactiveVar,
} from "@apollo/client";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import _ from "lodash";
import { OS_LEGAL_COLORS } from "../assets/configurations/osLegalStyles";
import {
  PageContainer,
  ContentContainer,
  HeroSection,
  HeroTitle,
  HeroSubtitle,
  StatsContainer,
  SectionHeader,
  SectionTitle,
  EmptyStateWrapper,
} from "../components/layout/PageLayout";
import {
  SearchBox,
  FilterTabs,
  StatBlock,
  StatGrid,
  Button,
  EmptyState,
} from "@os-legal/ui";
import type { FilterTabItem } from "@os-legal/ui";
import {
  Plus,
  Grid,
  List,
  AlignJustify,
  SlidersHorizontal,
  X,
  AlertCircle,
  ExternalLink,
  Eye,
  FolderOpen,
  Edit,
  CheckSquare,
  Trash2,
} from "lucide-react";
import {
  ContextMenu,
  ContextMenuItem,
} from "../components/widgets/context-menu/ContextMenu";

import {
  DeleteMultipleDocumentsInputs,
  DeleteMultipleDocumentsOutputs,
  DELETE_MULTIPLE_DOCUMENTS,
} from "../graphql/mutations";
import {
  RequestDocumentsForListInputs,
  RequestDocumentsForListOutputs,
  GET_DOCUMENTS_FOR_LIST,
  RequestDocumentStatsInputs,
  RequestDocumentStatsOutputs,
  GET_DOCUMENT_STATS,
} from "../graphql/queries";
import { buildDocumentStatsVariables } from "./documentStatsVariables";
import {
  documentSearchTerm,
  editingDocument,
  filterToCorpus,
  filterToLabelId,
  filterToLabelsetId,
  selectedDocumentIds,
  showAddDocsToCorpusModal,
  showDeleteDocumentsModal,
  viewingDocument,
  userObj,
  showBulkUploadModal,
  showUploadNewDocumentsModal,
  backendUserObj,
} from "../graphql/cache";

import { FilterToLabelSelector } from "../components/widgets/model-filters/FilterToLabelSelector";
import { DocumentType, LabelType } from "../types/graphql-api";
import { AddToCorpusModal } from "../components/modals/AddToCorpusModal";
import { ConfirmModal } from "../components/widgets/modals/ConfirmModal";
import { FilterToLabelsetSelector } from "../components/widgets/model-filters/FilterToLabelsetSelector";
import { FilterToCorpusSelector } from "../components/widgets/model-filters/FilterToCorpusSelector";
import { BulkUploadModal } from "../components/widgets/modals/BulkUploadModal";
import { FetchMoreOnVisible } from "../components/widgets/infinite_scroll/FetchMoreOnVisible";
import { FetchMoreFooter } from "../components/widgets/infinite_scroll/FetchMoreFooter";
import { LoadingOverlay } from "../components/common/LoadingOverlay";
import { navigateToDocument } from "../utils/navigationUtils";
import {
  VIEW_MODES,
  STATUS_FILTERS,
  DEBOUNCE,
  type ViewMode,
  type StatusFilter,
} from "../assets/configurations/constants";
import {
  ActionButtons,
  ClearFiltersButton,
  DocumentsSection,
  FilterBadge,
  FilterButton,
  FilterPopup,
  FilterPopupClose,
  FilterPopupContainer,
  FilterPopupContent,
  FilterPopupHeader,
  FilterPopupTitle,
  FilterTabsRow,
  SearchContainer,
  ViewToggle,
  ViewToggleButton,
} from "./Documents.styles";
import { DocumentsGridView } from "./DocumentsGridView";
import { DocumentsListView } from "./DocumentsListView";
import { DocumentsCompactView } from "./DocumentsCompactView";

// ═══════════════════════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════════════════════

// Initial page size for the list view. Subsequent pages are also 20 (see
// handleFetchMore below). Keeping the first page small means first paint pays
// for ~20 fully-resolved DocumentType rows instead of the connection's default
// cap (RELAY_CONNECTION_MAX_LIMIT = 100), which is the cost the slow render
// was actually charged.
const DOCUMENTS_PAGE_SIZE = 20;

// ═══════════════════════════════════════════════════════════════════════════════
// ICONS
// ═══════════════════════════════════════════════════════════════════════════════

const DocumentIcon = () => (
  <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
    <path
      d="M12 6a4 4 0 00-4 4v28a4 4 0 004 4h24a4 4 0 004-4V18l-12-12H12z"
      fill="currentColor"
      opacity="0.1"
    />
    <path
      d="M12 6a4 4 0 00-4 4v28a4 4 0 004 4h24a4 4 0 004-4V18l-12-12H12z"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M28 6v12h12"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export const Documents = () => {
  const current_user = useReactiveVar(userObj);
  const backend_user = useReactiveVar(backendUserObj);
  const show_bulk_upload_modal = useReactiveVar(showBulkUploadModal);
  const show_upload_new_documents_modal = useReactiveVar(
    showUploadNewDocumentsModal
  );
  const filtered_to_labelset_id = useReactiveVar(filterToLabelsetId);
  const filtered_to_label_id = useReactiveVar(filterToLabelId);
  const filtered_to_corpus = useReactiveVar(filterToCorpus);
  const selected_document_ids = useReactiveVar(selectedDocumentIds);
  const document_search_term = useReactiveVar(documentSearchTerm);
  const show_add_docs_to_corpus_modal = useReactiveVar(
    showAddDocsToCorpusModal
  );
  const show_delete_documents_modal = useReactiveVar(showDeleteDocumentsModal);

  const [searchCache, setSearchCache] = useState<string>(document_search_term);
  const [viewMode, setViewMode] = useState<ViewMode>(VIEW_MODES.GRID);
  const [activeStatusFilter, setActiveStatusFilter] = useState<StatusFilter>(
    STATUS_FILTERS.ALL
  );
  const [contextMenu, setContextMenu] = useState<{
    document: DocumentType;
    position: { x: number; y: number };
  } | null>(null);
  const [showFilterPopup, setShowFilterPopup] = useState(false);

  const filterPopupRef = useRef<HTMLDivElement>(null);

  const navigate = useNavigate();

  // Build query variables. Memoized on the underlying primitives so Apollo's
  // ``useQuery`` only re-fetches when something the user actually changed (a
  // search term, a filter, the active corpus). Previously six separate
  // ``useEffect(refetch)`` hooks fired on the same dep set in addition to the
  // ``useQuery`` call itself, producing ~7 redundant network requests on first
  // mount.
  const documentVariables: RequestDocumentsForListInputs = useMemo(
    () => ({
      limit: DOCUMENTS_PAGE_SIZE,
      ...(document_search_term && { textSearch: document_search_term }),
      ...(filtered_to_label_id && { hasLabelWithId: filtered_to_label_id }),
      ...(filtered_to_corpus && { inCorpusWithId: filtered_to_corpus.id }),
    }),
    [document_search_term, filtered_to_label_id, filtered_to_corpus]
  );

  const {
    refetch: refetchDocuments,
    loading: documents_loading,
    networkStatus: documents_network_status,
    error: documents_error,
    data: documents_data,
    fetchMore: fetchMoreDocuments,
  } = useQuery<RequestDocumentsForListOutputs, RequestDocumentsForListInputs>(
    GET_DOCUMENTS_FOR_LIST,
    {
      variables: documentVariables,
      // No ``nextFetchPolicy`` override — let Apollo's default cache-first
      // behavior do its job. The previous ``"network-only"`` setting forced
      // every refetch (including the six redundant ones) to skip the cache,
      // which combined with the refetch storm hammered the backend on every
      // re-render of any parent reactive var.
      notifyOnNetworkStatusChange: true,
    }
  );

  // ``document_items`` was previously rebuilt on every render via
  // ``.map().filter()``, producing a fresh array reference each time. That
  // churned the ``useMemo`` deps below (``filteredDocuments``, ``stats``,
  // ``statusFilterItems``) and was also the same shape of bug that triggered
  // the production reload loop fixed in PR #1512 / #1517. Memoizing on the
  // stable Apollo ``edges`` reference breaks the cycle.
  const document_items = useMemo<DocumentType[]>(() => {
    const edges = documents_data?.documents?.edges ?? [];
    return edges
      .map((edge) => (edge?.node ? edge.node : undefined))
      .filter((item): item is DocumentType => !!item);
  }, [documents_data?.documents?.edges]);

  // Filter by status
  const filteredDocuments = useMemo(() => {
    if (activeStatusFilter === STATUS_FILTERS.ALL) return document_items;
    if (activeStatusFilter === STATUS_FILTERS.PROCESSED) {
      return document_items.filter((doc) => !doc.backendLock);
    }
    if (activeStatusFilter === STATUS_FILTERS.PROCESSING) {
      return document_items.filter((doc) => doc.backendLock);
    }
    // 'error' filter - would need error field in DocumentType
    return document_items;
  }, [document_items, activeStatusFilter]);

  // Stats are computed by a single backend ``aggregate()`` over
  // ``Document.objects.visible_to_user`` so the tile counters reflect the
  // user's full permission scope rather than the paginated edges that
  // happen to be loaded into Apollo's cache. The previous client-side
  // reduce over ``document_items`` was bounded by the page size and
  // additionally over-counted whenever filter changes leaked stale
  // edges into the cache (the documents connection has no keyArgs).
  const documentStatsVariables: RequestDocumentStatsInputs = useMemo(
    () =>
      buildDocumentStatsVariables({
        searchTerm: document_search_term,
        labelId: filtered_to_label_id,
        corpus: filtered_to_corpus,
      }),
    [document_search_term, filtered_to_label_id, filtered_to_corpus]
  );

  // ``cache-and-network`` so the tiles update when the user revisits the
  // view (e.g. after a document finishes processing and ``backendLock`` flips
  // from true to false in another session). Without it, the default
  // ``cache-first`` policy would never refetch as long as the variables
  // remained stable, leaving processed/processing counters stuck at the
  // values from the first visit.
  const { data: stats_data, error: stats_error } = useQuery<
    RequestDocumentStatsOutputs,
    RequestDocumentStatsInputs
  >(GET_DOCUMENT_STATS, {
    variables: documentStatsVariables,
    fetchPolicy: "cache-and-network",
  });

  // Surface stats failures in the console so they don't silently render as
  // zero counts (the same shape as the loading state). UI-side, we keep the
  // zero fallback rather than a dash because the rest of the view stays
  // usable; this is a complementary signal, not a hard error.
  useEffect(() => {
    if (stats_error) {
      console.error("Documents view: GET_DOCUMENT_STATS failed", stats_error);
    }
  }, [stats_error]);

  const stats = stats_data?.documentStats ?? {
    totalDocs: 0,
    totalPages: 0,
    processedCount: 0,
    processingCount: 0,
  };

  // Filter tabs configuration — ``All Documents`` reflects the full
  // permission-filtered total, NOT the paginated subset, so the badge
  // matches the tile counter to the right of it.
  const statusFilterItems: FilterTabItem[] = useMemo(
    () => [
      {
        id: STATUS_FILTERS.ALL,
        label: "All Documents",
        count: String(stats.totalDocs),
      },
      {
        id: STATUS_FILTERS.PROCESSED,
        label: "Processed",
        count: String(stats.processedCount),
      },
      {
        id: STATUS_FILTERS.PROCESSING,
        label: "Processing",
        count: String(stats.processingCount),
      },
    ],
    [stats.totalDocs, stats.processedCount, stats.processingCount]
  );

  // Apollo's ``useQuery`` automatically refetches when ``variables`` change
  // (deep-compared), so we no longer need the six separate ``useEffect`` hooks
  // that previously called ``refetchDocuments()`` on each reactive-var change.
  // Each of those effects fired on mount in addition to the initial
  // ``useQuery`` call, producing ~7 network requests for the same data on
  // every visit to /documents. Anything the user can change that should drive
  // a refetch is now a member of ``documentVariables``; anything that
  // shouldn't (``location`` re-renders, ``current_user`` settling, the
  // unrelated ``filtered_to_labelset_id`` reactive var) no longer triggers
  // one. ``filtered_to_labelset_id`` is intentionally NOT a query variable —
  // it's only used by the labelset filter UI to scope label-picker options;
  // the previous refetch on its change was a no-op against the backend.

  // Debounced search with consolidated cleanup to prevent memory leaks.
  // The ref ensures stable reference across renders, and the cleanup
  // directly accesses the ref to cancel any pending debounce on unmount.
  const debouncedSearch = useRef(
    _.debounce((searchTerm: string) => {
      documentSearchTerm(searchTerm);
    }, DEBOUNCE.SEARCH_MS)
  );

  useEffect(() => {
    // Capture ref for cleanup - access directly to ensure we cancel the current function
    const debounceFn = debouncedSearch.current;
    return () => {
      debounceFn.cancel();
    };
  }, []);

  const handleSearchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value;
      setSearchCache(value);
      debouncedSearch.current(value);
    },
    []
  );

  // Mutations
  const [tryDeleteDocuments] = useMutation<
    DeleteMultipleDocumentsOutputs,
    DeleteMultipleDocumentsInputs
  >(DELETE_MULTIPLE_DOCUMENTS, {
    onCompleted: () => {
      selectedDocumentIds([]);
      refetchDocuments();
    },
  });

  const handleDeleteDocuments = (
    ids: string[] | null,
    callback?: (args?: any) => void | any
  ) => {
    if (ids) {
      tryDeleteDocuments({ variables: { documentIdsToDelete: ids } })
        .then(() => {
          toast.success("SUCCESS - Deleted Documents");
          if (callback) callback();
        })
        .catch(() => {
          toast.error("ERROR - Could Not Delete Documents");
          if (callback) callback();
        });
    }
  };

  // Infinite scroll
  const handleFetchMore = useCallback(() => {
    if (
      !documents_loading &&
      documents_data?.documents?.pageInfo?.hasNextPage
    ) {
      fetchMoreDocuments({
        variables: {
          limit: DOCUMENTS_PAGE_SIZE,
          cursor: documents_data.documents.pageInfo.endCursor,
        },
      });
    }
  }, [documents_loading, documents_data, fetchMoreDocuments]);

  // Selection handlers
  const handleSelect = (docId: string) => {
    if (selected_document_ids.includes(docId)) {
      selectedDocumentIds(selected_document_ids.filter((id) => id !== docId));
    } else {
      selectedDocumentIds([...selected_document_ids, docId]);
    }
  };

  const handleSelectAll = () => {
    if (selected_document_ids.length === filteredDocuments.length) {
      selectedDocumentIds([]);
    } else {
      selectedDocumentIds(filteredDocuments.map((d) => d.id));
    }
  };

  // Context menu handlers
  const handleContextMenu = (e: React.MouseEvent, doc: DocumentType) => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({
      document: doc,
      position: { x: e.clientX, y: e.clientY },
    });
  };

  const handleCloseContextMenu = useCallback(() => {
    setContextMenu(null);
  }, []);

  // Close filter popup on click outside
  useEffect(() => {
    if (!showFilterPopup) return;

    const handleClickOutside = (event: MouseEvent) => {
      if (
        filterPopupRef.current &&
        !filterPopupRef.current.contains(event.target as Node)
      ) {
        setShowFilterPopup(false);
      }
    };

    // Delay to prevent immediate close from the button click
    const timer = setTimeout(() => {
      document.addEventListener("mousedown", handleClickOutside);
    }, DEBOUNCE.CLICK_OUTSIDE_DELAY_MS);

    return () => {
      clearTimeout(timer);
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [showFilterPopup]);

  // Document click handler
  const handleDocumentClick = (doc: DocumentType) => {
    if (contextMenu) return;
    navigateToDocument(doc, null, navigate, window.location.pathname);
  };

  // Get section title based on filter
  const getSectionTitle = () => {
    switch (activeStatusFilter) {
      case STATUS_FILTERS.PROCESSED:
        return "Processed Documents";
      case STATUS_FILTERS.PROCESSING:
        return "Processing Documents";
      default:
        return "All Documents";
    }
  };

  // Check if advanced filters are active and count them
  const activeFilterCount = [
    filtered_to_labelset_id,
    filtered_to_corpus,
    filtered_to_label_id,
  ].filter(Boolean).length;
  const hasAdvancedFilters = activeFilterCount > 0;

  // Clear all advanced filters
  const handleClearFilters = () => {
    filterToLabelsetId("");
    filterToCorpus(null);
    filterToLabelId("");
    setShowFilterPopup(false);
  };

  const allSelected =
    selected_document_ids.length === filteredDocuments.length &&
    filteredDocuments.length > 0;

  return (
    <PageContainer>
      <ContentContainer>
        {/* Modals */}
        <BulkUploadModal />
        <AddToCorpusModal
          open={show_add_docs_to_corpus_modal}
          onClose={() => showAddDocsToCorpusModal(false)}
          onSuccess={() => {
            toast.success("Documents added to corpus successfully!");
            selectedDocumentIds([]);
          }}
          documents={document_items}
          selectedDocumentIds={selected_document_ids}
          multiStep={true}
          title="Add Documents to Corpus"
        />
        <ConfirmModal
          message="Are you sure you want to delete these documents?"
          yesAction={() =>
            handleDeleteDocuments(
              selected_document_ids.length > 0 ? selected_document_ids : null,
              () => showDeleteDocumentsModal(false)
            )
          }
          noAction={() => showDeleteDocumentsModal(false)}
          toggleModal={() => showDeleteDocumentsModal(false)}
          visible={show_delete_documents_modal}
        />
        {/* Hero Section */}
        <HeroSection>
          <HeroTitle>
            Your <span>documents</span>
          </HeroTitle>
          <HeroSubtitle>
            Browse, search, and manage all documents across your corpuses.
            Upload new files or explore your existing library.
          </HeroSubtitle>

          <SearchContainer>
            <SearchBox
              placeholder="Search for documents..."
              value={searchCache}
              onChange={handleSearchChange}
              onSubmit={() => documentSearchTerm(searchCache)}
            />
          </SearchContainer>

          <FilterTabsRow>
            <FilterTabs
              items={statusFilterItems}
              value={activeStatusFilter}
              onChange={(id: string) =>
                setActiveStatusFilter(id as StatusFilter)
              }
            />
            <FilterPopupContainer ref={filterPopupRef}>
              <FilterButton
                $active={showFilterPopup}
                $hasFilters={hasAdvancedFilters}
                onClick={() => setShowFilterPopup(!showFilterPopup)}
                aria-expanded={showFilterPopup}
                aria-haspopup="dialog"
              >
                <SlidersHorizontal />
                Filters
                {activeFilterCount > 0 && (
                  <FilterBadge>{activeFilterCount}</FilterBadge>
                )}
              </FilterButton>
              {showFilterPopup && (
                <FilterPopup role="dialog" aria-label="Advanced filters">
                  <FilterPopupHeader>
                    <FilterPopupTitle>Advanced Filters</FilterPopupTitle>
                    <FilterPopupClose onClick={() => setShowFilterPopup(false)}>
                      <X size={16} />
                    </FilterPopupClose>
                  </FilterPopupHeader>
                  <FilterPopupContent>
                    <FilterToLabelsetSelector
                      fixed_labelset_id={
                        filtered_to_corpus?.labelSet?.id
                          ? filtered_to_corpus.labelSet.id
                          : undefined
                      }
                    />
                    <FilterToCorpusSelector
                      uses_labelset_id={filtered_to_labelset_id}
                    />
                    {filtered_to_labelset_id ||
                    filtered_to_corpus?.labelSet?.id ? (
                      <FilterToLabelSelector
                        label_type={LabelType.TokenLabel}
                        only_labels_for_labelset_id={
                          filtered_to_labelset_id
                            ? filtered_to_labelset_id
                            : filtered_to_corpus?.labelSet?.id
                            ? filtered_to_corpus.labelSet.id
                            : undefined
                        }
                      />
                    ) : null}
                    {hasAdvancedFilters && (
                      <ClearFiltersButton onClick={handleClearFilters}>
                        Clear all filters
                      </ClearFiltersButton>
                    )}
                  </FilterPopupContent>
                </FilterPopup>
              )}
            </FilterPopupContainer>
          </FilterTabsRow>
        </HeroSection>

        {/* Stats Grid */}
        <StatsContainer>
          <StatGrid columns={2}>
            <StatBlock
              value={stats.totalDocs.toString()}
              label="Documents"
              sublabel="in your library"
            />
            <StatBlock
              value={stats.totalPages.toLocaleString()}
              label="Pages"
              sublabel="total content"
            />
            <StatBlock
              value={stats.processedCount.toString()}
              label="Processed"
              sublabel="ready for analysis"
            />
            <StatBlock
              value={stats.processingCount.toString()}
              label="Processing"
              sublabel="being analyzed"
            />
          </StatGrid>
        </StatsContainer>

        {/* Documents Section */}
        <DocumentsSection>
          {/* Cover the grid only on the initial load — fetchMore keeps existing rows visible. */}
          <LoadingOverlay
            active={documents_loading && filteredDocuments.length === 0}
            size="large"
            content="Loading documents..."
          />

          <SectionHeader>
            <SectionTitle>{getSectionTitle()}</SectionTitle>
            <ActionButtons>
              <ViewToggle role="group" aria-label="Document view options">
                <ViewToggleButton
                  $active={viewMode === VIEW_MODES.GRID}
                  onClick={() => setViewMode(VIEW_MODES.GRID)}
                  title="Grid view"
                  aria-label="Grid view"
                  aria-pressed={viewMode === VIEW_MODES.GRID}
                >
                  <Grid size={16} />
                </ViewToggleButton>
                <ViewToggleButton
                  $active={viewMode === VIEW_MODES.LIST}
                  onClick={() => setViewMode(VIEW_MODES.LIST)}
                  title="List view"
                  aria-label="List view"
                  aria-pressed={viewMode === VIEW_MODES.LIST}
                >
                  <List size={16} />
                </ViewToggleButton>
                <ViewToggleButton
                  $active={viewMode === VIEW_MODES.COMPACT}
                  onClick={() => setViewMode(VIEW_MODES.COMPACT)}
                  title="Compact view"
                  aria-label="Compact view"
                  aria-pressed={viewMode === VIEW_MODES.COMPACT}
                >
                  <AlignJustify size={16} />
                </ViewToggleButton>
              </ViewToggle>

              {current_user &&
                (selected_document_ids.length > 0 ? (
                  <ActionButtons>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => showAddDocsToCorpusModal(true)}
                    >
                      Add to Corpus
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => showDeleteDocumentsModal(true)}
                      style={{ color: OS_LEGAL_COLORS.danger }}
                    >
                      Delete ({selected_document_ids.length})
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => selectedDocumentIds([])}
                    >
                      Clear
                    </Button>
                  </ActionButtons>
                ) : (
                  <ActionButtons>
                    <Button
                      variant="primary"
                      size="sm"
                      leftIcon={<Plus size={16} />}
                      onClick={() => showUploadNewDocumentsModal(true)}
                    >
                      Upload
                    </Button>
                    {backend_user && !backend_user.isUsageCapped && (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => showBulkUploadModal(true)}
                      >
                        Bulk Upload
                      </Button>
                    )}
                  </ActionButtons>
                ))}
            </ActionButtons>
          </SectionHeader>

          {filteredDocuments.length > 0 ? (
            <>
              {viewMode === VIEW_MODES.GRID && (
                <DocumentsGridView
                  documents={filteredDocuments}
                  selectedIds={selected_document_ids}
                  activeContextMenuDocId={contextMenu?.document.id}
                  onDocumentClick={handleDocumentClick}
                  onSelect={handleSelect}
                  onContextMenu={handleContextMenu}
                />
              )}

              {viewMode === VIEW_MODES.LIST && (
                <DocumentsListView
                  documents={filteredDocuments}
                  selectedIds={selected_document_ids}
                  activeContextMenuDocId={contextMenu?.document.id}
                  allSelected={allSelected}
                  onDocumentClick={handleDocumentClick}
                  onSelect={handleSelect}
                  onSelectAll={handleSelectAll}
                  onContextMenu={handleContextMenu}
                />
              )}

              {viewMode === VIEW_MODES.COMPACT && (
                <DocumentsCompactView
                  documents={filteredDocuments}
                  selectedIds={selected_document_ids}
                  activeContextMenuDocId={contextMenu?.document.id}
                  onDocumentClick={handleDocumentClick}
                  onSelect={handleSelect}
                  onContextMenu={handleContextMenu}
                />
              )}

              <FetchMoreOnVisible fetchNextPage={handleFetchMore} />
              <FetchMoreFooter
                visible={documents_network_status === NetworkStatus.fetchMore}
                message="Loading more documents…"
                data-testid="documents-fetch-more-spinner"
              />
            </>
          ) : documents_error ? (
            <EmptyStateWrapper>
              <EmptyState
                icon={<AlertCircle size={48} />}
                title="Failed to load documents"
                description={
                  documents_error.message ||
                  "An error occurred while loading documents. Please try again."
                }
                size="lg"
                action={
                  <Button variant="primary" onClick={() => refetchDocuments()}>
                    Try Again
                  </Button>
                }
              />
            </EmptyStateWrapper>
          ) : !documents_loading ? (
            <EmptyStateWrapper>
              <EmptyState
                icon={<DocumentIcon />}
                title={
                  activeStatusFilter !== STATUS_FILTERS.ALL
                    ? `No ${getSectionTitle().toLowerCase()}`
                    : hasAdvancedFilters
                    ? "No documents match your filters"
                    : "No documents yet"
                }
                description={
                  activeStatusFilter !== STATUS_FILTERS.ALL
                    ? "Try selecting a different filter to see more documents."
                    : hasAdvancedFilters
                    ? "Try adjusting your filters or clearing them to see more documents."
                    : "Upload your first document to get started with document analysis, annotation, and AI-powered insights."
                }
                size="lg"
                action={
                  activeStatusFilter === STATUS_FILTERS.ALL &&
                  !hasAdvancedFilters &&
                  current_user ? (
                    <Button
                      variant="primary"
                      leftIcon={<Plus size={16} />}
                      onClick={() => showUploadNewDocumentsModal(true)}
                    >
                      Upload Your First Document
                    </Button>
                  ) : undefined
                }
              />
            </EmptyStateWrapper>
          ) : null}
        </DocumentsSection>

        {/* Context Menu */}
        {contextMenu && (
          <ContextMenu
            position={contextMenu.position}
            onClose={handleCloseContextMenu}
            header={contextMenu.document.title || "Untitled"}
            aria-label="Document actions"
            items={
              [
                {
                  key: "open",
                  icon: <ExternalLink size={16} />,
                  label: "Open Document",
                  variant: "primary" as const,
                  onClick: () => {
                    handleDocumentClick(contextMenu.document);
                    handleCloseContextMenu();
                  },
                },
                {
                  key: "view",
                  icon: <Eye size={16} />,
                  label: "View Details",
                  onClick: () => {
                    viewingDocument(contextMenu.document);
                    handleCloseContextMenu();
                  },
                },
                {
                  key: "add-to-corpus",
                  icon: <FolderOpen size={16} />,
                  label: "Add to Corpus",
                  visible: Boolean(current_user),
                  onClick: () => {
                    selectedDocumentIds([contextMenu.document.id]);
                    showAddDocsToCorpusModal(true);
                    handleCloseContextMenu();
                  },
                },
                {
                  key: "edit",
                  icon: <Edit size={16} />,
                  label: "Edit Details",
                  visible: Boolean(current_user),
                  onClick: () => {
                    editingDocument(contextMenu.document);
                    handleCloseContextMenu();
                  },
                },
                {
                  key: "select",
                  icon: <CheckSquare size={16} />,
                  label: selected_document_ids.includes(contextMenu.document.id)
                    ? "Deselect"
                    : "Select",
                  visible: Boolean(current_user),
                  onClick: () => {
                    handleSelect(contextMenu.document.id);
                    handleCloseContextMenu();
                  },
                },
                {
                  key: "delete",
                  icon: <Trash2 size={16} />,
                  label: "Delete",
                  variant: "danger" as const,
                  visible: Boolean(current_user),
                  onClick: () => {
                    selectedDocumentIds([contextMenu.document.id]);
                    showDeleteDocumentsModal(true);
                    handleCloseContextMenu();
                  },
                },
              ] satisfies ContextMenuItem[]
            }
          />
        )}
      </ContentContainer>
    </PageContainer>
  );
};
