import React, { useState, useMemo, useCallback } from "react";
import styled from "styled-components";
import { useNavigate } from "react-router-dom";
import { useMutation, useReactiveVar } from "@apollo/client";
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
import {
  editingCorpus,
  viewingCorpus,
  deletingCorpus,
  exportingCorpus,
  showAnalyzerSelectionForCorpus,
  userObj,
} from "../../graphql/cache";
import {
  StartForkCorpusInput,
  StartForkCorpusOutput,
  START_FORK_CORPUS,
} from "../../graphql/mutations";
import { navigateToCorpus } from "../../utils/navigationUtils";
import { getPermissions } from "../../utils/transform";
import { PermissionTypes } from "../types";
import { FetchMoreOnVisible } from "../widgets/infinite_scroll/FetchMoreOnVisible";
import { LoadingOverlay } from "../common/LoadingOverlay";
import { MCPShareButton } from "../common/MCPShareButton";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";

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

// Wrapper to handle right-click context menu on cards
const CardWrapper = styled.div`
  position: relative;
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
  currentUserEmail?: string
): string {
  const isOwner = corpus.creator?.email === currentUserEmail;
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
  corpuses: CorpusType[] | null;
  pageInfo: PageInfo | undefined;
  loading: boolean;
  fetchMore: (args?: any) => void | any;
  onCreateCorpus: () => void;
  onImportCorpus?: () => void;
  searchValue: string;
  onSearchChange: (value: string) => void;
  allowImport?: boolean;
}

export const CorpusListView: React.FC<CorpusListViewProps> = ({
  corpuses,
  pageInfo,
  loading,
  fetchMore,
  onCreateCorpus,
  onImportCorpus,
  searchValue,
  onSearchChange,
  allowImport = false,
}) => {
  const navigate = useNavigate();
  const currentUser = useReactiveVar(userObj);
  // Use userObj for auth check - consistent with NavMenu which gates protected items on user object
  // Note: authToken can be out of sync with userObj in some edge cases
  const isAuthenticated = Boolean(currentUser);
  const currentUserEmail = currentUser?.email;

  // Filter state
  const [activeFilter, setActiveFilter] = useState("all");

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

  // Filter corpuses based on active filter
  const filteredCorpuses = useMemo(() => {
    if (!corpuses) return [];

    switch (activeFilter) {
      case "my":
        return corpuses.filter((c) => c.creator?.email === currentUserEmail);
      case "shared":
        return corpuses.filter(
          (c) =>
            !c.isPublic &&
            c.creator?.email !== currentUserEmail &&
            (c.myPermissions?.length || 0) > 0
        );
      case "public":
        return corpuses.filter((c) => c.isPublic);
      default:
        return corpuses;
    }
  }, [corpuses, activeFilter, currentUserEmail]);

  // Calculate counts for filter tabs
  const filterCounts = useMemo(() => {
    if (!corpuses) return { my: 0, shared: 0, public: 0 };

    return {
      my: corpuses.filter((c) => c.creator?.email === currentUserEmail).length,
      shared: corpuses.filter(
        (c) =>
          !c.isPublic &&
          c.creator?.email !== currentUserEmail &&
          (c.myPermissions?.length || 0) > 0
      ).length,
      public: corpuses.filter((c) => c.isPublic).length,
    };
  }, [corpuses, currentUserEmail]);

  // Filter tabs configuration
  const filterItems: FilterTabItem[] = [
    { id: "all", label: "All" },
    { id: "my", label: "My Corpuses", count: String(filterCounts.my) },
    { id: "shared", label: "Shared", count: String(filterCounts.shared) },
    { id: "public", label: "Public", count: String(filterCounts.public) },
  ];

  // Calculate stats
  const stats = useMemo(() => {
    const list = corpuses || [];
    return {
      totalCorpuses: list.length,
      totalDocuments: list.reduce((sum, c) => sum + (c.documentCount || 0), 0),
      totalAnnotations: list.reduce(
        (sum, c) => sum + (c.annotations?.totalCount || 0),
        0
      ),
      sharedCount: list.filter(
        (c) => !c.isPublic && c.creator?.email !== currentUserEmail
      ).length,
    };
  }, [corpuses, currentUserEmail]);

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

          {/* Filter Tabs */}
          <FilterTabs
            items={filterItems}
            value={activeFilter}
            onChange={setActiveFilter}
          />
        </HeroSection>

        {/* Stats Grid */}
        <StatsContainer>
          <StatGrid columns={2}>
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
          <LoadingOverlay
            active={loading}
            inverted
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
                    currentUserEmail
                  );

                  return (
                    <CardWrapper
                      key={corpus.id}
                      onContextMenu={(e) => handleOpenContextMenu(e, corpus.id)}
                    >
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
                        description={corpus.description || "No description"}
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
        </CorpusListContainer>
      </ContentContainer>
    </PageContainer>
  );
};

export default CorpusListView;
