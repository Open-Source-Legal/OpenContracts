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
import styled from "styled-components";
import {
  OS_LEGAL_COLORS,
  accentAlpha,
} from "../assets/configurations/osLegalStyles";
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
  Chip,
  Avatar,
} from "@os-legal/ui";
import type { FilterTabItem } from "@os-legal/ui";
import {
  Plus,
  Grid,
  List,
  AlignJustify,
  MoreVertical,
  FileText,
  Loader2,
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
import { formatFileSize, formatRelativeTime } from "../utils/formatters";
import { getCreatorInitials } from "../utils/userDisplay";
import {
  VIEW_MODES,
  STATUS_FILTERS,
  DEBOUNCE,
  type ViewMode,
  type StatusFilter,
} from "../assets/configurations/constants";

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
// STYLED COMPONENTS - Following CorpusListView/DiscoveryLanding patterns
// ═══════════════════════════════════════════════════════════════════════════════

const SearchContainer = styled.div`
  margin-bottom: 16px;
`;

const FilterTabsRow = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
`;

const FilterButton = styled.button<{
  $active?: boolean;
  $hasFilters?: boolean;
}>`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: ${(props) =>
    props.$active ? OS_LEGAL_COLORS.surfaceLight : "white"};
  border: 1px solid
    ${(props) =>
      props.$hasFilters ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.border};
  border-radius: 8px;
  color: ${(props) =>
    props.$hasFilters ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.textSecondary};
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    border-color: ${(props) =>
      props.$hasFilters ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.borderHover};
  }

  svg {
    width: 16px;
    height: 16px;
  }
`;

const FilterBadge = styled.span`
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  background: ${OS_LEGAL_COLORS.accent};
  color: white;
  font-size: 11px;
  font-weight: 600;
  border-radius: 9px;
`;

const FilterPopupContainer = styled.div`
  position: relative;
`;

const FilterPopup = styled.div`
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  z-index: 50;
  min-width: 320px;
  padding: 16px;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.12);

  /* Override the harsh gradient labels from filter components */
  .ui.label {
    background: ${OS_LEGAL_COLORS.surfaceLight} !important;
    color: ${OS_LEGAL_COLORS.textTertiary} !important;
    box-shadow: none !important;
    font-size: 0.6875rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.05em !important;
  }

  @media (max-width: 640px) {
    left: 50%;
    transform: translateX(-50%);
    min-width: calc(100vw - 48px);
    max-width: 400px;
  }
`;

const FilterPopupHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
`;

const FilterPopupTitle = styled.span`
  font-size: 14px;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const FilterPopupClose = styled.button`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: ${OS_LEGAL_COLORS.textMuted};
  cursor: pointer;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    color: ${OS_LEGAL_COLORS.textTertiary};
  }
`;

const FilterPopupContent = styled.div`
  display: flex;
  flex-direction: column;
  gap: 12px;

  /* Give each child descending z-index so earlier dropdowns appear above later ones */
  & > *:nth-child(1) {
    position: relative;
    z-index: 30;
  }
  & > *:nth-child(2) {
    position: relative;
    z-index: 20;
  }
  & > *:nth-child(3) {
    position: relative;
    z-index: 10;
  }
  & > *:nth-child(4) {
    position: relative;
    z-index: 5;
  }
`;

const ClearFiltersButton = styled.button`
  margin-top: 8px;
  padding: 8px 12px;
  background: transparent;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 6px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;

  &:hover {
    background: ${OS_LEGAL_COLORS.dangerSurface};
    border-color: ${OS_LEGAL_COLORS.dangerBorder};
    color: ${OS_LEGAL_COLORS.danger};
  }
`;

const ActionButtons = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
`;

const ViewToggle = styled.div`
  display: flex;
  align-items: center;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  padding: 3px;
`;

const ViewToggleButton = styled.button<{ $active?: boolean }>`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  background: ${(props) =>
    props.$active ? OS_LEGAL_COLORS.surfaceLight : "transparent"};
  border: none;
  border-radius: 6px;
  color: ${(props) =>
    props.$active ? OS_LEGAL_COLORS.textPrimary : OS_LEGAL_COLORS.textMuted};
  cursor: pointer;
  transition: all 0.15s;

  &:hover {
    color: ${OS_LEGAL_COLORS.textTertiary};
  }
`;

const DocumentsListContainer = styled.section`
  position: relative;
  min-height: 200px;
`;

// ═══════════════════════════════════════════════════════════════════════════════
// DOCUMENT GRID STYLES
// ═══════════════════════════════════════════════════════════════════════════════

const DocumentsGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
`;

const DocumentCardWrapper = styled.div<{ $selected?: boolean }>`
  position: relative;
  display: flex;
  flex-direction: column;
  background: white;
  border: 1px solid
    ${(props) =>
      props.$selected ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.border};
  border-radius: 12px;
  overflow: hidden;
  transition: all 0.15s;
  cursor: pointer;
  box-shadow: ${(props) =>
    props.$selected ? `0 0 0 2px ${accentAlpha(0.2)}` : "none"};

  &:hover {
    border-color: ${(props) =>
      props.$selected ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.borderHover};
    box-shadow: ${(props) =>
      props.$selected
        ? `0 0 0 2px ${accentAlpha(0.2)}`
        : "0 4px 6px rgba(15, 23, 42, 0.04)"};
    transform: translateY(-2px);
  }
`;

const CardCheckbox = styled.div<{ $visible?: boolean }>`
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 10;
  opacity: ${(props) => (props.$visible ? 1 : 0)};
  transition: opacity 0.15s;

  ${DocumentCardWrapper}:hover & {
    opacity: 1;
  }
`;

const CardPreview = styled.div`
  position: relative;
  height: 160px;
  background: linear-gradient(
    135deg,
    ${OS_LEGAL_COLORS.surfaceHover} 0%,
    ${OS_LEGAL_COLORS.surfaceLight} 100%
  );
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
`;

const CardThumbnail = styled.img`
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center top;
`;

const CardPreviewPlaceholder = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 20px;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const PreviewLines = styled.div`
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 80%;
  max-width: 180px;
`;

const PreviewLine = styled.div<{ $width?: string }>`
  height: 6px;
  background: ${OS_LEGAL_COLORS.border};
  border-radius: 3px;
  width: ${(props) => props.$width || "100%"};
`;

const TypeBadge = styled.div`
  position: absolute;
  top: 12px;
  right: 12px;
`;

const ProcessingOverlay = styled.div`
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: rgba(248, 250, 252, 0.9);
  backdrop-filter: blur(2px);
`;

const ProcessingText = styled.span`
  font-size: 13px;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textTertiary};
`;

const CardBody = styled.div`
  padding: 16px;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
`;

const CardTitle = styled.h4`
  font-size: 14px;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.4;
  word-break: break-word;
`;

const CardMeta = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const MetaSeparator = styled.span`
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: ${OS_LEGAL_COLORS.textMuted};
  opacity: 0.5;
`;

const CardFooter = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-top: 1px solid ${OS_LEGAL_COLORS.border};
  background: ${OS_LEGAL_COLORS.background};
`;

const CardUploader = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: ${OS_LEGAL_COLORS.textTertiary};
`;

const CardMenuButton = styled.button`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: ${OS_LEGAL_COLORS.textMuted};
  cursor: pointer;
  opacity: 0;
  transition: all 0.15s;

  ${DocumentCardWrapper}:hover & {
    opacity: 1;
  }

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    color: ${OS_LEGAL_COLORS.textTertiary};
  }
`;

// ═══════════════════════════════════════════════════════════════════════════════
// DOCUMENT LIST STYLES
// ═══════════════════════════════════════════════════════════════════════════════

const DocumentsListView = styled.div`
  display: flex;
  flex-direction: column;
  gap: 2px;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  overflow: hidden;
`;

const ListHeader = styled.div`
  display: grid;
  grid-template-columns: 40px 1fr 100px 100px 120px 150px 48px;
  gap: 16px;
  padding: 12px 16px;
  background: ${OS_LEGAL_COLORS.background};
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: ${OS_LEGAL_COLORS.textMuted};

  @media (max-width: 768px) {
    grid-template-columns: 32px 1fr 80px 48px;

    & > :nth-child(3),
    & > :nth-child(5),
    & > :nth-child(6) {
      display: none;
    }
  }
`;

const ListItem = styled.div<{ $selected?: boolean }>`
  display: grid;
  grid-template-columns: 40px 1fr 100px 100px 120px 150px 48px;
  gap: 16px;
  padding: 12px 16px;
  align-items: center;
  cursor: pointer;
  transition: background 0.1s;
  background: ${(props) =>
    props.$selected ? accentAlpha(0.04) : "transparent"};

  &:hover {
    background: ${(props) =>
      props.$selected ? accentAlpha(0.06) : OS_LEGAL_COLORS.surfaceHover};
  }

  &:not(:last-child) {
    border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  }

  @media (max-width: 768px) {
    grid-template-columns: 32px 1fr 80px 48px;

    & > :nth-child(3),
    & > :nth-child(5),
    & > :nth-child(6) {
      display: none;
    }
  }
`;

const ListItemIcon = styled.div`
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const ListItemName = styled.span`
  font-size: 14px;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textPrimary};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const ListItemType = styled.span`
  font-size: 12px;
  text-transform: uppercase;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const ListItemSize = styled.span`
  font-size: 13px;
  color: ${OS_LEGAL_COLORS.textTertiary};
`;

const ListItemUploader = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: ${OS_LEGAL_COLORS.textTertiary};
`;

const ListItemActions = styled.div`
  display: flex;
  justify-content: flex-end;
  opacity: 0;
  transition: opacity 0.1s;

  ${ListItem}:hover & {
    opacity: 1;
  }
`;

// ═══════════════════════════════════════════════════════════════════════════════
// COMPACT VIEW STYLES
// ═══════════════════════════════════════════════════════════════════════════════

const DocumentsCompactView = styled.div`
  display: flex;
  flex-direction: column;
  gap: 2px;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  overflow: hidden;
`;

const CompactItem = styled.div<{ $selected?: boolean }>`
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  cursor: pointer;
  transition: background 0.1s;
  background: ${(props) =>
    props.$selected ? accentAlpha(0.04) : "transparent"};

  &:hover {
    background: ${(props) =>
      props.$selected ? accentAlpha(0.06) : OS_LEGAL_COLORS.surfaceHover};
  }

  &:not(:last-child) {
    border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  }
`;

const CompactItemName = styled.span`
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textPrimary};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const CompactItemMeta = styled.span`
  font-size: 12px;
  color: ${OS_LEGAL_COLORS.textMuted};
  flex-shrink: 0;
`;

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
// HELPER FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

function getDocumentType(doc: DocumentType): string {
  // Use fileType field directly if available (preferred)
  if (doc.fileType) {
    const ft = doc.fileType.toLowerCase();
    if (ft === "pdf") return "PDF";
    if (ft === "docx" || ft === "doc") return "DOCX";
    if (ft === "txt") return "TXT";
    return ft.toUpperCase();
  }
  // Fallback: parse from title if it has a valid extension
  const fileName = doc.title || "";
  const parts = fileName.split(".");
  // Only use extension if there are multiple parts (filename.ext)
  if (parts.length > 1) {
    const ext = parts.pop()?.toLowerCase();
    if (ext === "pdf") return "PDF";
    if (ext === "docx" || ext === "doc") return "DOCX";
    if (ext === "txt") return "TXT";
    if (ext) return ext.toUpperCase();
  }
  // Default to PDF if no extension found
  return "PDF";
}

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
        <DocumentsListContainer>
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
                <DocumentsGrid>
                  {filteredDocuments.map((doc) => (
                    <DocumentCardWrapper
                      key={doc.id}
                      role="button"
                      tabIndex={0}
                      data-testid="document-card"
                      data-processing={String(Boolean(doc.backendLock))}
                      aria-label={`Open document ${doc.title || "Untitled"}`}
                      $selected={selected_document_ids.includes(doc.id)}
                      onClick={() => handleDocumentClick(doc)}
                      onContextMenu={(e) => handleContextMenu(e, doc)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          handleDocumentClick(doc);
                        }
                      }}
                    >
                      <CardCheckbox
                        $visible={selected_document_ids.includes(doc.id)}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <input
                          type="checkbox"
                          aria-label={`Select ${doc.title || "Untitled"}`}
                          checked={selected_document_ids.includes(doc.id)}
                          onChange={() => handleSelect(doc.id)}
                        />
                      </CardCheckbox>

                      <CardPreview>
                        {doc.icon ? (
                          <CardThumbnail
                            src={doc.icon}
                            alt={doc.title || "Document"}
                          />
                        ) : (
                          <CardPreviewPlaceholder>
                            <FileText size={48} />
                            <PreviewLines>
                              <PreviewLine />
                              <PreviewLine $width="85%" />
                              <PreviewLine $width="90%" />
                              <PreviewLine $width="70%" />
                            </PreviewLines>
                          </CardPreviewPlaceholder>
                        )}

                        <TypeBadge>
                          <Chip size="sm" variant="filled" color="default">
                            {getDocumentType(doc)}
                          </Chip>
                        </TypeBadge>

                        {doc.backendLock && (
                          <ProcessingOverlay>
                            <Loader2
                              size={24}
                              className="animate-spin"
                              style={{ animation: "spin 1s linear infinite" }}
                            />
                            <ProcessingText>Processing...</ProcessingText>
                          </ProcessingOverlay>
                        )}
                      </CardPreview>

                      <CardBody>
                        <CardTitle title={doc.title || "Untitled"}>
                          {doc.title || "Untitled"}
                        </CardTitle>
                        <CardMeta>
                          {doc.pageCount ? (
                            <span>{doc.pageCount} pages</span>
                          ) : (
                            <span>Document</span>
                          )}
                        </CardMeta>
                      </CardBody>

                      <CardFooter>
                        <CardUploader>
                          <Avatar
                            fallback={getCreatorInitials(doc.creator)}
                            size="xs"
                          />
                          <span>{formatRelativeTime(doc.created)}</span>
                        </CardUploader>
                        <CardMenuButton
                          aria-label="Open menu"
                          aria-haspopup="menu"
                          aria-expanded={contextMenu?.document.id === doc.id}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleContextMenu(e, doc);
                          }}
                        >
                          <MoreVertical size={16} />
                        </CardMenuButton>
                      </CardFooter>
                    </DocumentCardWrapper>
                  ))}
                </DocumentsGrid>
              )}

              {viewMode === VIEW_MODES.LIST && (
                <DocumentsListView role="table" aria-label="Documents list">
                  <ListHeader role="rowgroup">
                    <input
                      type="checkbox"
                      aria-label="Select all documents"
                      checked={
                        selected_document_ids.length ===
                          filteredDocuments.length &&
                        filteredDocuments.length > 0
                      }
                      onChange={handleSelectAll}
                    />
                    <span>Name</span>
                    <span>Type</span>
                    <span>Pages</span>
                    <span>Status</span>
                    <span>Uploaded</span>
                    <span></span>
                  </ListHeader>
                  {filteredDocuments.map((doc) => (
                    <ListItem
                      key={doc.id}
                      role="row"
                      tabIndex={0}
                      data-testid="document-card"
                      data-processing={String(Boolean(doc.backendLock))}
                      aria-label={`Open document ${doc.title || "Untitled"}`}
                      $selected={selected_document_ids.includes(doc.id)}
                      onClick={() => handleDocumentClick(doc)}
                      onContextMenu={(e) => handleContextMenu(e, doc)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          handleDocumentClick(doc);
                        }
                      }}
                    >
                      <div onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          aria-label={`Select ${doc.title || "Untitled"}`}
                          checked={selected_document_ids.includes(doc.id)}
                          onChange={() => handleSelect(doc.id)}
                        />
                      </div>
                      <ListItemName title={doc.title || "Untitled"}>
                        {doc.title || "Untitled"}
                      </ListItemName>
                      <ListItemType>{getDocumentType(doc)}</ListItemType>
                      <ListItemSize>
                        {doc.pageCount ? `${doc.pageCount} pages` : ""}
                      </ListItemSize>
                      <div>
                        <Chip
                          size="sm"
                          variant="soft"
                          color={doc.backendLock ? "warning" : "success"}
                        >
                          {doc.backendLock ? "Processing" : "Processed"}
                        </Chip>
                      </div>
                      <ListItemUploader>
                        <Avatar
                          fallback={getCreatorInitials(doc.creator)}
                          size="xs"
                        />
                        <span>{formatRelativeTime(doc.created)}</span>
                      </ListItemUploader>
                      <ListItemActions>
                        <CardMenuButton
                          aria-label="Open menu"
                          aria-haspopup="menu"
                          aria-expanded={contextMenu?.document.id === doc.id}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleContextMenu(e, doc);
                          }}
                        >
                          <MoreVertical size={16} />
                        </CardMenuButton>
                      </ListItemActions>
                    </ListItem>
                  ))}
                </DocumentsListView>
              )}

              {viewMode === VIEW_MODES.COMPACT && (
                <DocumentsCompactView>
                  {filteredDocuments.map((doc) => (
                    <CompactItem
                      key={doc.id}
                      role="listitem"
                      tabIndex={0}
                      data-testid="document-card"
                      data-processing={String(Boolean(doc.backendLock))}
                      aria-label={`Open document ${doc.title || "Untitled"}`}
                      $selected={selected_document_ids.includes(doc.id)}
                      onClick={() => handleDocumentClick(doc)}
                      onContextMenu={(e) => handleContextMenu(e, doc)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          handleDocumentClick(doc);
                        }
                      }}
                    >
                      <div onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          aria-label={`Select ${doc.title || "Untitled"}`}
                          checked={selected_document_ids.includes(doc.id)}
                          onChange={() => handleSelect(doc.id)}
                        />
                      </div>
                      <ListItemIcon>
                        <FileText size={20} />
                      </ListItemIcon>
                      <CompactItemName title={doc.title || "Untitled"}>
                        {doc.title || "Untitled"}
                      </CompactItemName>
                      <CompactItemMeta>
                        {doc.pageCount ? `${doc.pageCount} pages` : ""}
                      </CompactItemMeta>
                      <Chip
                        size="sm"
                        variant="soft"
                        color={doc.backendLock ? "warning" : "success"}
                      >
                        {doc.backendLock ? "Processing" : "Processed"}
                      </Chip>
                      <CardMenuButton
                        aria-label="Open menu"
                        aria-haspopup="menu"
                        aria-expanded={contextMenu?.document.id === doc.id}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleContextMenu(e, doc);
                        }}
                      >
                        <MoreVertical size={16} />
                      </CardMenuButton>
                    </CompactItem>
                  ))}
                </DocumentsCompactView>
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
        </DocumentsListContainer>

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
