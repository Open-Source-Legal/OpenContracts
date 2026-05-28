import React, { useState, useMemo, useCallback } from "react";
import styled from "styled-components";
import { useNavigate } from "react-router-dom";
import { NetworkStatus, useMutation, useReactiveVar } from "@apollo/client";
import {
  SearchBox,
  FilterTabs,
  CollectionCard,
  CollectionList,
  StatBlock,
  StatGrid,
  Button,
  EmptyState,
} from "@os-legal/ui";
import type { FilterTabItem, CollectionType } from "@os-legal/ui";
import {
  Plus,
  Upload,
  Edit as EditIcon,
  Eye,
  Download,
  GitFork,
  Trash2,
} from "lucide-react";
import {
  ContextMenu,
  ContextMenuItem,
} from "../widgets/context-menu/ContextMenu";
import { toast } from "react-toastify";

import { CorpusType, PageInfo } from "../../types/graphql-api";
import { CorpusFilterCounts } from "../../graphql/queries";
import {
  editingCorpus,
  viewingCorpus,
  deletingCorpus,
  exportingCorpus,
  showAnalyzerSelectionForCorpus,
  userObj,
  backendUserObj,
} from "../../graphql/cache";
import { isOwnedBy } from "../../utils/userDisplay";
import {
  StartForkCorpusInput,
  StartForkCorpusOutput,
  START_FORK_CORPUS,
} from "../../graphql/mutations";
import { navigateToCorpus } from "../../utils/navigationUtils";
import { getPermissions } from "../../utils/transform";
import { PermissionTypes } from "../types";
import { FetchMoreOnVisible } from "../widgets/infinite_scroll/FetchMoreOnVisible";
import { FetchMoreFooter } from "../widgets/infinite_scroll/FetchMoreFooter";
import { LoadingOverlay } from "../common/LoadingOverlay";
import { MCPShareButton } from "../common/MCPShareButton";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { CorpusVoteWidget } from "./CorpusVoteWidget";

// ═══════════════════════════════════════════════════════════════════════════════
// STYLED COMPONENTS - Following DiscoveryLanding patterns
// ═══════════════════════════════════════════════════════════════════════════════

const PageContainer = styled.div`
  height: 100%;
  background: ${OS_LEGAL_COLORS.background};
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  overflow-y: auto;
  overflow-x: hidden;
`;

const ContentContainer = styled.main`
  max-width: 900px;
  margin: 0 auto;
  padding: 48px 24px 80px;

  @media (max-width: 768px) {
    padding: 32px 16px 60px;
  }
`;

const HeroSection = styled.section`
  margin-bottom: 48px;
`;

const HeroTitle = styled.h1`
  font-family: "Georgia", "Times New Roman", serif;
  font-size: 42px;
  font-weight: 400;
  line-height: 1.2;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0 0 16px;

  span {
    color: ${OS_LEGAL_COLORS.accent};
  }

  @media (max-width: 768px) {
    font-size: 32px;
  }
`;

const HeroSubtitle = styled.p`
  font-size: 17px;
  line-height: 1.6;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin: 0 0 32px;
  max-width: 600px;
`;

const SearchContainer = styled.div`
  margin-bottom: 16px;
`;

const StatsContainer = styled.div`
  margin-bottom: 48px;
  padding: 32px 0;

  /* Override stat value size like StatsSection does */
  [data-testid="stat-value"] {
    font-size: 36px !important;
  }

  @media (max-width: 768px) {
    padding: 24px 0;

    [data-testid="stat-value"] {
      font-size: 28px !important;
    }
  }
`;

const SectionHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  gap: 16px;
  flex-wrap: wrap;

  @media (max-width: 768px) {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
  }
`;

const SectionTitle = styled.h2`
  font-family: "Georgia", "Times New Roman", serif;
  font-size: 24px;
  font-weight: 400;
  color: ${OS_LEGAL_COLORS.accent};
  margin: 0;
`;

const ActionButtons = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;

  @media (max-width: 768px) {
    width: 100%;
    justify-content: flex-end;
  }

  /* Make buttons full-width on very small screens */
  @media (max-width: 480px) {
    flex-direction: column;
    gap: 8px;

    button {
      width: 100%;
      justify-content: center;
    }
  }
`;

const CorpusListContainer = styled.section`
  position: relative;
  min-height: 200px;
`;

// Note: Using the class expected by CollectionCard for proper styling
const MenuButton = styled.button`
  && {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    background: transparent;
    border: none;
    border-radius: 6px;
    color: ${OS_LEGAL_COLORS.textSecondary};
    cursor: pointer;
    transition: all 0.15s;

    &:hover {
      background: ${OS_LEGAL_COLORS.surfaceLight};
      color: #334155;
    }
  }
`;

const EmptyStateWrapper = styled.div`
  padding: 48px 24px;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 16px;
`;

// Wrapper for each row in the corpus list.
//
// We reserve a fixed rail on the left (``padding-left``) so the vertical
// vote pill has somewhere to live without ever overlapping the corpus
// avatar inside ``CollectionCard``. The padding is applied unconditionally
// — personal corpora (where the vote widget is suppressed) keep the same
// indent so every row stays vertically aligned in the list.
const VOTE_RAIL_WIDTH = 36;

const CardWrapper = styled.div`
  position: relative;
  padding-left: ${VOTE_RAIL_WIDTH}px;

  @media (max-width: 480px) {
    padding-left: 30px;
  }
`;

// MCP button overlay for corpus cards. Always visible so MCP discovery is
// consistent across every tile — public corpora get a copy-able endpoint,
// private corpora get an explanation in the popover.
const MCPButtonOverlay = styled.div`
  position: absolute;
  top: 12px;
  right: 48px; /* Position left of the kebab menu */
  z-index: 10;
`;

// Vote pill rail — pinned to the dedicated ``VOTE_RAIL_WIDTH`` strip on
// the LEFT of the wrapper, vertically centred. Sits in the wrapper's
// padding so it never overlaps the corpus avatar inside CollectionCard.
// z-index matches the MCP overlay (10) so they share the same stacking
// context above the card body but below any open context menu
// (z-index >= 100 in the ContextMenu component).
const VoteWidgetOverlay = styled.div`
  position: absolute;
  top: 50%;
  left: 0;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  width: ${VOTE_RAIL_WIDTH}px;
  z-index: 10;

  @media (max-width: 480px) {
    width: 30px;
  }
`;

// Sort dropdown — a plain ``<select>`` styled to match the OS-Legal
// surface chrome.  Lives next to the search box at the top of the page.
const SortRow = styled.div`
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
`;

const SortLabel = styled.label`
  font-size: 13px;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textSecondary};
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
`;

const SortSelect = styled.select`
  appearance: none;
  /* Safari < 15 needs the vendor prefix to actually suppress the native
     dropdown affordance — without it, Safari renders the default chevron
     in addition to our custom one. */
  -webkit-appearance: none;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  padding: 6px 28px 6px 12px;
  font-size: 13px;
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  color: ${OS_LEGAL_COLORS.textPrimary};
  cursor: pointer;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2364748B' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><polyline points='6 9 12 15 18 9'/></svg>");
  background-repeat: no-repeat;
  background-position: right 8px center;

  &:hover {
    border-color: ${OS_LEGAL_COLORS.accent};
  }
  &:focus {
    outline: none;
    border-color: ${OS_LEGAL_COLORS.accent};
    box-shadow: 0 0 0 3px rgba(20, 184, 166, 0.15);
  }
`;

// Floating context menu (similar to old CorpusItem)

// ═══════════════════════════════════════════════════════════════════════════════
// ICONS
// ═══════════════════════════════════════════════════════════════════════════════

const KebabIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16">
    <circle cx="8" cy="3" r="1.5" fill="currentColor" />
    <circle cx="8" cy="8" r="1.5" fill="currentColor" />
    <circle cx="8" cy="13" r="1.5" fill="currentColor" />
  </svg>
);

const FolderIcon = () => (
  <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
    <path
      d="M4 12a4 4 0 014-4h8.343a4 4 0 012.829 1.172l1.656 1.656A4 4 0 0023.657 12H32a4 4 0 014 4v16a4 4 0 01-4 4H8a4 4 0 01-4-4V12z"
      fill="currentColor"
    />
  </svg>
);

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

function mapCategoryToType(corpus: CorpusType): CollectionType {
  const categoryName = corpus.categories?.[0]?.name?.toLowerCase() || "";
  if (categoryName.includes("legislation")) return "legislation";
  if (categoryName.includes("contract")) return "contracts";
  if (categoryName.includes("case") || categoryName.includes("law"))
    return "case-law";
  if (categoryName.includes("knowledge")) return "knowledge";
  return "default";
}

function getVisibilityStatus(
  corpus: CorpusType,
  currentUserId?: string
): string {
  const isOwner = isOwnedBy(corpus.creator, { id: currentUserId });
  // Using Unicode symbols for visual flair
  if (corpus.isPublic) return "🌐 Public";
  if (isOwner) return "🔒 Private";
  return "👥 Shared";
}

function formatStats(corpus: CorpusType): string[] {
  const stats: string[] = [];
  const docCount = corpus.documentCount ?? 0;

  if (docCount > 0)
    stats.push(`${docCount} ${docCount === 1 ? "doc" : "docs"}`);

  // Add labelset name + label count together
  if (corpus.labelSet) {
    const totalLabels =
      (corpus.labelSet.docLabelCount || 0) +
      (corpus.labelSet.spanLabelCount || 0) +
      (corpus.labelSet.tokenLabelCount || 0);
    const labelsetName = corpus.labelSet.title || "Labeled";
    if (totalLabels > 0) {
      stats.push(
        `${labelsetName} (${totalLabels} ${
          totalLabels === 1 ? "label" : "labels"
        })`
      );
    } else {
      stats.push(labelsetName);
    }
  } else {
    stats.push("No Labels");
  }

  return stats;
}

function getCategoryBadge(corpus: CorpusType): string | undefined {
  if (corpus.categories && corpus.categories.length > 0) {
    return corpus.categories[0].name;
  }
  return undefined;
}

function getLastUpdatedText(corpus: CorpusType): string {
  // If we had a modified date, we'd format it here
  // For now, return empty or a placeholder
  return "";
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

interface CorpusListViewProps {
  /**
   * Already filtered to the active tab on the server. The component does
   * NOT apply additional client-side tab filtering — that would be
   * incorrect once the server is the source of truth for which corpuses
   * belong to each tab and pagination is filter-aware.
   */
  corpuses: CorpusType[] | null;
  pageInfo: PageInfo | undefined;
  loading: boolean;
  /** NetworkStatus from useQuery. When omitted, footer falls back to `loading && hasNextPage`. */
  networkStatus?: NetworkStatus;
  fetchMore: (args?: any) => void | any;
  onCreateCorpus: () => void;
  onImportCorpus?: () => void;
  searchValue: string;
  onSearchChange: (value: string) => void;
  allowImport?: boolean;
  activeFilter: string;
  onFilterChange: (filter: string) => void;
  filterCounts: CorpusFilterCounts;
  /**
   * Current sort key (empty string = "default" / let the backend apply
   * its intrinsic ``ordering = ("created",)``).  Other valid values
   * mirror the backend ``CorpusFilter.order_by`` tuple-mapping:
   * "top" / "-top", "-modified", "title".
   */
  sortValue: string;
  onSortChange: (sort: string) => void;
}

export const CorpusListView: React.FC<CorpusListViewProps> = ({
  corpuses,
  pageInfo,
  loading,
  networkStatus,
  fetchMore,
  onCreateCorpus,
  onImportCorpus,
  searchValue,
  onSearchChange,
  allowImport = false,
  activeFilter,
  onFilterChange,
  filterCounts,
  sortValue,
  onSortChange,
}) => {
  const navigate = useNavigate();
  const currentUser = useReactiveVar(userObj);
  const backendUser = useReactiveVar(backendUserObj);
  // Use userObj for auth check - consistent with NavMenu which gates protected items on user object
  // Note: authToken can be out of sync with userObj in some edge cases
  const isAuthenticated = Boolean(currentUser);
  // Ownership keys off the backend user id (the public GraphQL UserType)
  // so we don't depend on the redacted email field.
  const currentUserId = backendUser?.id;

  // Track which menu is open and its position
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [menuPosition, setMenuPosition] = useState<{
    x: number;
    y: number;
  } | null>(null);

  // Fork mutation
  const [startForkCorpus] = useMutation<
    StartForkCorpusOutput,
    StartForkCorpusInput
  >(START_FORK_CORPUS, {
    onCompleted: () => {
      toast.success(
        "SUCCESS! Fork started. Refresh the corpus page to view fork progress."
      );
    },
    onError: () => {
      toast.error("ERROR! Could not start corpus fork.");
    },
  });

  // Server pre-filters by activeFilter, so the corpuses prop is the list to render.
  const filteredCorpuses = corpuses ?? [];

  // Filter tabs configuration
  const filterItems: FilterTabItem[] = [
    { id: "all", label: "All", count: String(filterCounts.all) },
    { id: "my", label: "My Corpuses", count: String(filterCounts.mine) },
    { id: "shared", label: "Shared", count: String(filterCounts.shared) },
    { id: "public", label: "Public", count: String(filterCounts.public) },
  ];

  // Stat block totals. The corpus total is tab-scoped (matches the active
  // filter and the visible list) so the stat block agrees with the tab badge
  // the user just selected. Doc/annotation sums come from the currently
  // loaded page(s) of the active filter — they're an approximation that
  // grows as the user paginates. Shared count is always the global "shared
  // with me" total from the server.
  const stats = useMemo(() => {
    const list = corpuses || [];
    const tabKey =
      activeFilter === "my"
        ? "mine"
        : activeFilter === "shared"
        ? "shared"
        : activeFilter === "public"
        ? "public"
        : "all";
    return {
      totalCorpuses: filterCounts[tabKey as keyof CorpusFilterCounts],
      totalDocuments: list.reduce((sum, c) => sum + (c.documentCount || 0), 0),
      totalAnnotations: list.reduce(
        (sum, c) => sum + (c.annotations?.totalCount || 0),
        0
      ),
      sharedCount: filterCounts.shared,
    };
  }, [corpuses, filterCounts, activeFilter]);

  // Handle infinite scroll
  const handleFetchMore = useCallback(() => {
    if (!loading && pageInfo?.hasNextPage) {
      fetchMore({
        variables: {
          limit: 20,
          cursor: pageInfo.endCursor,
        },
      });
    }
  }, [loading, pageInfo, fetchMore]);

  // Handle corpus navigation
  const handleCorpusClick = useCallback(
    (corpus: CorpusType) => {
      // Don't navigate if menu is open
      if (openMenuId) return;
      navigateToCorpus(corpus, navigate, window.location.pathname);
    },
    [navigate, openMenuId]
  );

  // Handle opening context menu
  const handleOpenContextMenu = useCallback(
    (e: React.MouseEvent, corpusId: string) => {
      e.preventDefault();
      e.stopPropagation();
      setMenuPosition({ x: e.clientX, y: e.clientY });
      setOpenMenuId(corpusId);
    },
    []
  );

  // Handle closing context menu
  const handleCloseMenu = useCallback(() => {
    setOpenMenuId(null);
    setMenuPosition(null);
  }, []);

  // Handle search submit
  const handleSearchSubmit = useCallback(
    (value: string) => {
      onSearchChange(value);
    },
    [onSearchChange]
  );

  // Handle fork
  const handleFork = useCallback(
    (corpusId: string) => {
      startForkCorpus({ variables: { corpusId } });
    },
    [startForkCorpus]
  );

  // Determine section title based on filter
  const getSectionTitle = () => {
    switch (activeFilter) {
      case "my":
        return "My Corpuses";
      case "shared":
        return "Shared with Me";
      case "public":
        return "Public Corpuses";
      default:
        return "Your Corpuses";
    }
  };

  return (
    <PageContainer>
      <ContentContainer>
        {/* Hero Section */}
        <HeroSection>
          <HeroTitle>
            Your <span>corpuses</span>
          </HeroTitle>
          <HeroSubtitle>
            Organize documents, collaborate on annotations, and build knowledge
            collections.
          </HeroSubtitle>

          {/* Search */}
          <SearchContainer>
            <SearchBox
              placeholder="Search your corpuses..."
              value={searchValue}
              onChange={(e) => onSearchChange(e.target.value)}
              onSubmit={handleSearchSubmit}
            />
          </SearchContainer>

          {/* Sort dropdown — lives between the search box and the filter
              tabs so it remains visible across all four tabs without
              competing with the tab badge cluster. */}
          <SortRow>
            <SortLabel htmlFor="corpus-list-sort">Sort by</SortLabel>
            <SortSelect
              id="corpus-list-sort"
              data-testid="corpus-list-sort-select"
              value={sortValue}
              onChange={(e) => onSortChange(e.target.value)}
            >
              <option value="-created">Newest first</option>
              <option value="created">Oldest first</option>
              <option value="-modified">Recently updated</option>
              <option value="-top">Top (most upvotes)</option>
              <option value="top">Most downvoted</option>
              <option value="title">Title (A–Z)</option>
            </SortSelect>
          </SortRow>

          {/* Filter Tabs */}
          <FilterTabs
            items={filterItems}
            value={activeFilter}
            onChange={onFilterChange}
          />
        </HeroSection>

        {/* Stats Grid */}
        <StatsContainer>
          <StatGrid columns={4}>
            <StatBlock
              value={stats.totalCorpuses.toString()}
              label="Corpuses"
              sublabel="in your library"
            />
            <StatBlock
              value={stats.totalDocuments.toLocaleString()}
              label="Documents"
              sublabel="across all corpuses"
            />
            <StatBlock
              value={stats.totalAnnotations.toLocaleString()}
              label="Annotations"
              sublabel="total contributions"
            />
            <StatBlock
              value={stats.sharedCount.toString()}
              label="Shared"
              sublabel="with collaborators"
            />
          </StatGrid>
        </StatsContainer>

        {/* Corpus List Section */}
        <CorpusListContainer>
          {/* Cover the list only on the initial load — fetchMore keeps existing rows visible. */}
          <LoadingOverlay
            active={loading && filteredCorpuses.length === 0}
            size="large"
            content="Loading corpuses..."
          />

          <SectionHeader>
            <SectionTitle>{getSectionTitle()}</SectionTitle>
            {isAuthenticated && (
              <ActionButtons>
                {allowImport && onImportCorpus && (
                  <Button
                    variant="secondary"
                    size="sm"
                    leftIcon={<Upload size={16} />}
                    onClick={onImportCorpus}
                  >
                    Import
                  </Button>
                )}
                <Button
                  variant="primary"
                  size="sm"
                  leftIcon={<Plus size={16} />}
                  onClick={onCreateCorpus}
                >
                  New Corpus
                </Button>
              </ActionButtons>
            )}
          </SectionHeader>

          {filteredCorpuses.length > 0 ? (
            <>
              <CollectionList gap="md">
                {filteredCorpuses.map((corpus) => {
                  // Status shows visibility only (with icon)
                  const visibilityStatus = getVisibilityStatus(
                    corpus,
                    currentUserId
                  );

                  return (
                    <CardWrapper
                      key={corpus.id}
                      onContextMenu={(e) => handleOpenContextMenu(e, corpus.id)}
                    >
                      {/* Vertical vote pill in the wrapper's left rail.
                          Hidden on the user's own personal corpus — voting
                          on "My Documents" would be self-vote anyway and
                          the widget would render a permanently-disabled
                          control. The rail (padding-left on CardWrapper)
                          is reserved regardless so all rows stay aligned. */}
                      {!corpus.isPersonal && (
                        <VoteWidgetOverlay>
                          <CorpusVoteWidget
                            corpusId={corpus.id}
                            score={corpus.score ?? 0}
                            myVote={corpus.myVote ?? null}
                            creatorId={corpus.creator?.id}
                            orientation="vertical"
                            testId={`corpus-vote-${corpus.id}`}
                          />
                        </VoteWidgetOverlay>
                      )}
                      {/* MCP Share button overlay — always shown for
                          consistent discovery; popover content adapts based
                          on whether the corpus is public. */}
                      {corpus.slug && (
                        <MCPButtonOverlay>
                          <MCPShareButton
                            corpusSlug={corpus.slug}
                            isPublic={Boolean(corpus.isPublic)}
                            size="sm"
                            showLabel={false}
                            testId={`mcp-share-${corpus.id}`}
                          />
                        </MCPButtonOverlay>
                      )}
                      <CollectionCard
                        type={mapCategoryToType(corpus)}
                        badge={getCategoryBadge(corpus)}
                        image={corpus.icon || undefined}
                        imageAlt={corpus.title || "Corpus icon"}
                        status={visibilityStatus}
                        title={corpus.title || "Untitled Corpus"}
                        description={
                          corpus.descriptionPreview ||
                          corpus.description ||
                          "No description"
                        }
                        stats={formatStats(corpus)}
                        onClick={() => handleCorpusClick(corpus)}
                        menu={
                          <MenuButton
                            type="button"
                            className="oc-collection-card__menu-button"
                            aria-label="Open menu"
                            aria-haspopup="menu"
                            aria-expanded={openMenuId === corpus.id}
                            onClick={(e) => handleOpenContextMenu(e, corpus.id)}
                          >
                            <KebabIcon />
                          </MenuButton>
                        }
                      />
                    </CardWrapper>
                  );
                })}
              </CollectionList>

              {/* Floating Context Menu */}
              {(() => {
                if (!openMenuId || !menuPosition) return null;

                const corpus = filteredCorpuses.find(
                  (c) => c.id === openMenuId
                );
                if (!corpus) return null;

                const permissions = getPermissions(corpus.myPermissions || []);
                const canUpdate = permissions.includes(
                  PermissionTypes.CAN_UPDATE
                );
                const canRemove = permissions.includes(
                  PermissionTypes.CAN_REMOVE
                );

                return (
                  <ContextMenu
                    position={menuPosition}
                    onClose={handleCloseMenu}
                    aria-label="Corpus actions"
                    items={
                      [
                        {
                          key: "edit",
                          icon: <EditIcon size={16} />,
                          label: "Edit",
                          visible: canUpdate,
                          onClick: () => {
                            editingCorpus(corpus);
                            handleCloseMenu();
                          },
                        },
                        {
                          key: "view",
                          icon: <Eye size={16} />,
                          label: "View Details",
                          onClick: () => {
                            viewingCorpus(corpus);
                            handleCloseMenu();
                          },
                        },
                        {
                          key: "export",
                          icon: <Download size={16} />,
                          label: "Export",
                          onClick: () => {
                            exportingCorpus(corpus);
                            handleCloseMenu();
                          },
                        },
                        {
                          key: "fork",
                          icon: <GitFork size={16} />,
                          label: "Fork",
                          onClick: () => {
                            handleFork(corpus.id);
                            handleCloseMenu();
                          },
                        },
                        {
                          key: "delete",
                          icon: <Trash2 size={16} />,
                          label: "Delete",
                          variant: "danger" as const,
                          visible: canRemove && !corpus.isPersonal,
                          onClick: () => {
                            deletingCorpus(corpus);
                            handleCloseMenu();
                          },
                        },
                      ] satisfies ContextMenuItem[]
                    }
                  />
                );
              })()}
            </>
          ) : !loading ? (
            <EmptyStateWrapper>
              <EmptyState
                icon={<FolderIcon />}
                title={
                  activeFilter !== "all"
                    ? `No ${getSectionTitle().toLowerCase()}`
                    : "No corpuses yet"
                }
                description={
                  activeFilter !== "all"
                    ? "Try selecting a different filter to see more corpuses."
                    : "Create your first corpus to start organizing documents, annotations, and collaborative analysis."
                }
                size="lg"
                action={
                  activeFilter === "all" && isAuthenticated ? (
                    <Button
                      variant="primary"
                      leftIcon={<Plus size={16} />}
                      onClick={onCreateCorpus}
                    >
                      Create Your First Corpus
                    </Button>
                  ) : undefined
                }
              />
            </EmptyStateWrapper>
          ) : null}

          {/* Infinite scroll trigger */}
          <FetchMoreOnVisible fetchNextPage={handleFetchMore} />
          <FetchMoreFooter
            visible={
              networkStatus === NetworkStatus.fetchMore ||
              (networkStatus === undefined &&
                loading &&
                Boolean(pageInfo?.hasNextPage))
            }
            message="Loading more corpuses…"
            data-testid="corpuses-fetch-more-spinner"
          />
        </CorpusListContainer>
      </ContentContainer>
    </PageContainer>
  );
};

export default CorpusListView;
