import React, {
  useState,
  useMemo,
  useCallback,
  useEffect,
  useRef,
} from "react";
import styled from "styled-components";
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
import { useNavigate } from "react-router-dom";
import {
  NetworkStatus,
  useMutation,
  useQuery,
  useReactiveVar,
} from "@apollo/client";
import {
  SearchBox,
  FilterTabs,
  CollectionList,
  StatBlock,
  StatGrid,
  Button,
  EmptyState,
} from "@os-legal/ui";
import { Plus, Database } from "lucide-react";
import type { FilterTabItem } from "@os-legal/ui";
import { toast } from "react-toastify";
import _ from "lodash";

import { ExtractType } from "../types/graphql-api";
import {
  extractSearchTerm,
  selectedExtractIds,
  showCreateExtractModal,
  showDeleteExtractModal,
  userObj,
} from "../graphql/cache";
import {
  GetExtractsOutput,
  GetExtractsInput,
  GET_EXTRACTS,
} from "../graphql/queries";
import {
  REQUEST_DELETE_EXTRACT,
  RequestDeleteExtractInputType,
  RequestDeleteExtractOutputType,
} from "../graphql/mutations";
import { ExtractListCard } from "../components/extracts/ExtractListCard";
import { ConfirmModal } from "../components/widgets/modals/ConfirmModal";
import { CreateExtractModal } from "../components/widgets/modals/CreateExtractModal";
import { FetchMoreOnVisible } from "../components/widgets/infinite_scroll/FetchMoreOnVisible";
import { FetchMoreFooter } from "../components/widgets/infinite_scroll/FetchMoreFooter";
import { LoadingOverlay } from "../components/common/LoadingOverlay";
import { DEBOUNCE } from "../assets/configurations/constants";

// Styled Components

const SearchContainer = styled.div`
  margin-bottom: 16px;
`;

const ActionButtons = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
`;

const ListContainer = styled.section`
  position: relative;
  min-height: 200px;
`;

// Icons

const TableIcon = () => (
  <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
    <path
      d="M6 8a4 4 0 014-4h20a4 4 0 014 4v24a4 4 0 01-4 4H10a4 4 0 01-4-4V8zm4-2a2 2 0 00-2 2v6h24V8a2 2 0 00-2-2H10zm22 10H8v16a2 2 0 002 2h20a2 2 0 002-2V16zm-22 4h8v4H10v-4zm10 0h10v4H20v-4zm-10 6h8v4H10v-4zm10 0h10v4H20v-4z"
      fill="currentColor"
    />
  </svg>
);

// Main Component

export const Extracts = () => {
  const currentUser = useReactiveVar(userObj);
  const extract_search_term = useReactiveVar(extractSearchTerm);
  const show_create_extract_modal = useReactiveVar(showCreateExtractModal);
  const show_delete_extract_modal = useReactiveVar(showDeleteExtractModal);
  const selected_extract_ids = useReactiveVar(selectedExtractIds);
  // Use userObj for auth check - consistent with NavMenu pattern
  const isAuthenticated = Boolean(currentUser);
  const currentUserEmail = currentUser?.email;

  // Local state
  const [searchCache, setSearchCache] = useState<string>(extract_search_term);
  const [activeFilter, setActiveFilter] = useState("all");
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [menuPosition, setMenuPosition] = useState<{
    x: number;
    y: number;
  } | null>(null);
  const [extractToDelete, setExtractToDelete] = useState<ExtractType | null>(
    null
  );

  // Debounced search
  const debouncedSearch = useRef(
    _.debounce((searchTerm: string) => {
      extractSearchTerm(searchTerm);
    }, DEBOUNCE.EXTRACT_SEARCH_MS)
  );

  // Cleanup debounce on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      debouncedSearch.current.cancel();
    };
  }, []);

  const handleSearchChange = (value: string) => {
    setSearchCache(value);
    debouncedSearch.current(value);
  };

  // GraphQL Query
  const { refetch, loading, networkStatus, data, fetchMore } = useQuery<
    GetExtractsOutput,
    GetExtractsInput
  >(GET_EXTRACTS, {
    variables: {
      searchText: extract_search_term,
    },
    notifyOnNetworkStatusChange: true,
  });

  // Delete mutation
  const [tryDeleteExtract] = useMutation<
    RequestDeleteExtractOutputType,
    RequestDeleteExtractInputType
  >(REQUEST_DELETE_EXTRACT, {
    onCompleted: () => {
      refetch();
      toast.success("Extract deleted successfully");
    },
    onError: () => {
      toast.error("Failed to delete extract");
    },
  });

  // Extract extracts from query data
  const extracts: ExtractType[] = useMemo(() => {
    if (!data?.extracts?.edges) return [];
    return data.extracts.edges
      .map((edge) => edge?.node)
      .filter(
        (node): node is ExtractType => node !== null && node !== undefined
      );
  }, [data]);

  // Filter extracts based on active filter
  const filteredExtracts = useMemo(() => {
    switch (activeFilter) {
      case "running":
        return extracts.filter((ex) => ex.started && !ex.finished && !ex.error);
      case "completed":
        return extracts.filter((ex) => ex.finished && !ex.error);
      case "failed":
        return extracts.filter((ex) => ex.error);
      case "not_started":
        return extracts.filter((ex) => !ex.started);
      default:
        return extracts;
    }
  }, [extracts, activeFilter]);

  // Calculate counts for filter tabs
  const filterCounts = useMemo(() => {
    return {
      running: extracts.filter((ex) => ex.started && !ex.finished && !ex.error)
        .length,
      completed: extracts.filter((ex) => ex.finished && !ex.error).length,
      failed: extracts.filter((ex) => ex.error).length,
      not_started: extracts.filter((ex) => !ex.started).length,
    };
  }, [extracts]);

  // Filter tabs configuration
  const filterItems: FilterTabItem[] = [
    { id: "all", label: "All" },
    { id: "running", label: "Running", count: String(filterCounts.running) },
    {
      id: "completed",
      label: "Completed",
      count: String(filterCounts.completed),
    },
    { id: "failed", label: "Failed", count: String(filterCounts.failed) },
    {
      id: "not_started",
      label: "Not Started",
      count: String(filterCounts.not_started),
    },
  ];

  // Calculate stats
  const stats = useMemo(() => {
    let totalDocuments = 0;
    let totalColumns = 0;

    extracts.forEach((ex) => {
      totalDocuments += ex.fullDocumentList?.length || 0;
      totalColumns += ex.fieldset?.fullColumnList?.length || 0;
    });

    return {
      totalExtracts: extracts.length,
      running: filterCounts.running,
      completed: filterCounts.completed,
      totalDocuments,
    };
  }, [extracts, filterCounts]);

  // Navigation
  const navigate = useNavigate();

  // Handlers
  const handleViewExtract = useCallback(
    (extract: ExtractType) => {
      navigate(`/extracts/${extract.id}`);
    },
    [navigate]
  );

  const handleDeleteExtract = (extract: ExtractType) => {
    setExtractToDelete(extract);
    showDeleteExtractModal(true);
  };

  const confirmDelete = async () => {
    if (extractToDelete) {
      await tryDeleteExtract({ variables: { id: extractToDelete.id } });
    }
    showDeleteExtractModal(false);
    setExtractToDelete(null);
  };

  const handleFetchMore = useCallback(() => {
    if (!loading && data?.extracts?.pageInfo?.hasNextPage) {
      fetchMore({
        variables: {
          cursor: data.extracts.pageInfo.endCursor,
        },
      });
    }
  }, [loading, data, fetchMore]);

  const handleOpenContextMenu = useCallback(
    (e: React.MouseEvent, extractId: string) => {
      e.preventDefault();
      e.stopPropagation();
      setMenuPosition({ x: e.clientX, y: e.clientY });
      setOpenMenuId(extractId);
    },
    []
  );

  const handleCloseMenu = useCallback(() => {
    setOpenMenuId(null);
    setMenuPosition(null);
  }, []);

  // Close menu when clicking outside or pressing Escape
  useEffect(() => {
    const handleClickOutside = () => {
      if (openMenuId) {
        handleCloseMenu();
      }
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && openMenuId) {
        e.preventDefault();
        handleCloseMenu();
      }
    };

    if (openMenuId) {
      const timer = setTimeout(() => {
        document.addEventListener("click", handleClickOutside);
        document.addEventListener("keydown", handleKeyDown);
      }, 100);
      return () => {
        clearTimeout(timer);
        document.removeEventListener("click", handleClickOutside);
        document.removeEventListener("keydown", handleKeyDown);
      };
    }
  }, [openMenuId, handleCloseMenu]);

  // Refetch on auth change
  useEffect(() => {
    if (currentUser) {
      refetch();
    }
  }, [currentUser, refetch]);

  // Determine section title based on filter
  const getSectionTitle = () => {
    switch (activeFilter) {
      case "running":
        return "Running Extracts";
      case "completed":
        return "Completed Extracts";
      case "failed":
        return "Failed Extracts";
      case "not_started":
        return "Not Started Extracts";
      default:
        return "Your Extracts";
    }
  };

  return (
    <PageContainer>
      <ContentContainer>
        {/* Modals */}
        <ConfirmModal
          message={`Are you sure you want to delete "${
            extractToDelete?.name || "this extract"
          }"?`}
          yesAction={confirmDelete}
          noAction={() => {
            showDeleteExtractModal(false);
            setExtractToDelete(null);
          }}
          toggleModal={() => {
            showDeleteExtractModal(false);
            setExtractToDelete(null);
          }}
          visible={show_delete_extract_modal}
        />

        <CreateExtractModal
          open={show_create_extract_modal}
          onClose={() => {
            showCreateExtractModal(false);
            refetch();
          }}
        />

        {/* Hero Section */}
        <HeroSection>
          <HeroTitle>
            Extract <span>structured data</span>
          </HeroTitle>
          <HeroSubtitle>
            Create and manage data extracts from your documents using AI-powered
            field extraction.
          </HeroSubtitle>

          {/* Search */}
          <SearchContainer>
            <SearchBox
              placeholder="Search extracts..."
              value={searchCache}
              onChange={(e) => handleSearchChange(e.target.value)}
              onSubmit={(value) => handleSearchChange(value)}
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
              value={stats.totalExtracts.toString()}
              label="Total Extracts"
              sublabel="in your library"
            />
            <StatBlock
              value={stats.running.toString()}
              label="Running"
              sublabel="in progress"
            />
            <StatBlock
              value={stats.completed.toString()}
              label="Completed"
              sublabel="finished successfully"
            />
            <StatBlock
              value={stats.totalDocuments.toString()}
              label="Documents"
              sublabel="across all extracts"
            />
          </StatGrid>
        </StatsContainer>

        {/* Extracts List Section */}
        <ListContainer>
          {/* Cover the list only on the initial load — fetchMore keeps existing rows visible. */}
          <LoadingOverlay
            active={loading && filteredExtracts.length === 0}
            size="large"
            content="Loading extracts..."
          />

          <SectionHeader>
            <SectionTitle>{getSectionTitle()}</SectionTitle>
            {isAuthenticated && (
              <ActionButtons>
                <Button
                  variant="primary"
                  size="sm"
                  leftIcon={<Plus size={16} />}
                  onClick={() => showCreateExtractModal(true)}
                >
                  New Extract
                </Button>
              </ActionButtons>
            )}
          </SectionHeader>

          {filteredExtracts.length > 0 ? (
            <>
              <CollectionList gap="md">
                {filteredExtracts.map((extract) => (
                  <ExtractListCard
                    key={extract.id}
                    extract={extract}
                    currentUserEmail={currentUserEmail}
                    onView={handleViewExtract}
                    onDelete={handleDeleteExtract}
                    isMenuOpen={openMenuId === extract.id}
                    menuPosition={
                      openMenuId === extract.id ? menuPosition : null
                    }
                    onOpenMenu={handleOpenContextMenu}
                    onCloseMenu={handleCloseMenu}
                  />
                ))}
              </CollectionList>

              {/* Infinite scroll trigger */}
              <FetchMoreOnVisible fetchNextPage={handleFetchMore} />
              <FetchMoreFooter
                visible={networkStatus === NetworkStatus.fetchMore}
                message="Loading more extracts…"
                data-testid="extracts-fetch-more-spinner"
              />
            </>
          ) : !loading ? (
            <EmptyStateWrapper>
              <EmptyState
                icon={<TableIcon />}
                title={
                  activeFilter !== "all"
                    ? `No ${getSectionTitle().toLowerCase()}`
                    : "No extracts yet"
                }
                description={
                  activeFilter !== "all"
                    ? "Try selecting a different filter to see more extracts."
                    : "Create your first extract to start pulling structured data from your documents."
                }
                size="lg"
                action={
                  activeFilter === "all" && isAuthenticated ? (
                    <Button
                      variant="primary"
                      leftIcon={<Plus size={16} />}
                      onClick={() => showCreateExtractModal(true)}
                    >
                      Create Your First Extract
                    </Button>
                  ) : undefined
                }
              />
            </EmptyStateWrapper>
          ) : null}
        </ListContainer>
      </ContentContainer>
    </PageContainer>
  );
};

export default Extracts;
