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
import { Plus, Tags } from "lucide-react";
import type { FilterTabItem } from "@os-legal/ui";
import { toast } from "react-toastify";
import _ from "lodash";

import { LabelSetType } from "../types/graphql-api";
import {
  labelsetSearchTerm,
  showNewLabelsetModal,
  userObj,
  deletingLabelset,
  editingLabelset,
} from "../graphql/cache";
import {
  GetLabelsetsWithLabelsInputs,
  GetLabelsetsWithLabelsOutputs,
  REQUEST_LABELSETS_WITH_ALL_LABELS,
} from "../graphql/queries";
import {
  CreateLabelsetInputs,
  CreateLabelsetOutputs,
  CREATE_LABELSET,
  DeleteLabelsetInputs,
  DeleteLabelsetOutputs,
  DELETE_LABELSET,
} from "../graphql/mutations";
import { ConfirmModal } from "../components/widgets/modals/ConfirmModal";
import { LabelSetFormFields } from "../components/forms/LabelSetFormFields";
import { validateTitleAndDescription } from "../components/forms/shared";
import { CRUDModal } from "../components/widgets/CRUD/CRUDModal";
import { LabelSetListCard } from "../components/labelsets/LabelSetListCard";
import { FetchMoreOnVisible } from "../components/widgets/infinite_scroll/FetchMoreOnVisible";
import { FetchMoreFooter } from "../components/widgets/infinite_scroll/FetchMoreFooter";
import { LoadingOverlay } from "../components/common/LoadingOverlay";
import { getLabelsetUrl } from "../utils/navigationUtils";

// ═══════════════════════════════════════════════════════════════════════════════
// STYLED COMPONENTS
// ═══════════════════════════════════════════════════════════════════════════════

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

// ═══════════════════════════════════════════════════════════════════════════════
// ICONS
// ═══════════════════════════════════════════════════════════════════════════════

const TagsIcon = () => (
  <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
    <path
      d="M8 10a2 2 0 012-2h10.586a2 2 0 011.414.586l10 10a2 2 0 010 2.828l-8.586 8.586a2 2 0 01-2.828 0l-10-10A2 2 0 018 18.586V10z"
      fill="currentColor"
    />
    <circle cx="14" cy="14" r="2" fill="white" />
  </svg>
);

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export const Labelsets = () => {
  const navigate = useNavigate();
  const currentUser = useReactiveVar(userObj);
  const labelset_search_term = useReactiveVar(labelsetSearchTerm);
  const show_new_label_modal = useReactiveVar(showNewLabelsetModal);
  const labelset_to_delete = useReactiveVar(deletingLabelset);
  // Use userObj for auth check - consistent with NavMenu pattern
  const isAuthenticated = Boolean(currentUser);
  const currentUserEmail = currentUser?.email;

  // Local state
  const [searchCache, setSearchCache] = useState<string>(labelset_search_term);
  const [activeFilter, setActiveFilter] = useState("all");
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [menuPosition, setMenuPosition] = useState<{
    x: number;
    y: number;
  } | null>(null);

  // Debounced search
  const debouncedSearch = useRef(
    _.debounce((searchTerm: string) => {
      labelsetSearchTerm(searchTerm);
    }, 500)
  );

  const handleSearchChange = (value: string) => {
    setSearchCache(value);
    debouncedSearch.current(value);
  };

  // GraphQL Query
  const { refetch, loading, networkStatus, data, fetchMore } = useQuery<
    GetLabelsetsWithLabelsOutputs,
    GetLabelsetsWithLabelsInputs
  >(REQUEST_LABELSETS_WITH_ALL_LABELS, {
    variables: {
      textSearch: labelset_search_term,
    },
    notifyOnNetworkStatusChange: true,
  });

  // Create mutation
  const [createLabelset, { loading: create_labelset_loading }] = useMutation<
    CreateLabelsetOutputs,
    CreateLabelsetInputs
  >(CREATE_LABELSET);

  // Delete mutation
  const [deleteLabelset, { loading: delete_labelset_loading }] = useMutation<
    DeleteLabelsetOutputs,
    DeleteLabelsetInputs
  >(DELETE_LABELSET);

  // Extract labelsets from query data
  const labelsets: LabelSetType[] = useMemo(() => {
    if (!data?.labelsets?.edges) return [];
    return data.labelsets.edges
      .map((edge) => edge.node)
      .filter((node): node is LabelSetType => node !== null);
  }, [data]);

  // Filter labelsets based on active filter
  const filteredLabelsets = useMemo(() => {
    switch (activeFilter) {
      case "my":
        return labelsets.filter((ls) => ls.creator?.email === currentUserEmail);
      case "shared":
        return labelsets.filter(
          (ls) =>
            !ls.isPublic &&
            ls.creator?.email !== currentUserEmail &&
            (ls.myPermissions?.length || 0) > 0
        );
      case "public":
        return labelsets.filter((ls) => ls.isPublic);
      default:
        return labelsets;
    }
  }, [labelsets, activeFilter, currentUserEmail]);

  // Calculate counts for filter tabs
  const filterCounts = useMemo(() => {
    return {
      my: labelsets.filter((ls) => ls.creator?.email === currentUserEmail)
        .length,
      shared: labelsets.filter(
        (ls) =>
          !ls.isPublic &&
          ls.creator?.email !== currentUserEmail &&
          (ls.myPermissions?.length || 0) > 0
      ).length,
      public: labelsets.filter((ls) => ls.isPublic).length,
    };
  }, [labelsets, currentUserEmail]);

  // Filter tabs configuration
  const filterItems: FilterTabItem[] = [
    { id: "all", label: "All" },
    { id: "my", label: "My Label Sets", count: String(filterCounts.my) },
    { id: "shared", label: "Shared", count: String(filterCounts.shared) },
    { id: "public", label: "Public", count: String(filterCounts.public) },
  ];

  // Calculate stats
  const stats = useMemo(() => {
    let totalLabels = 0;
    let totalCorpusUses = 0;

    labelsets.forEach((ls) => {
      totalLabels +=
        (ls.docLabelCount || 0) +
        (ls.spanLabelCount || 0) +
        (ls.tokenLabelCount || 0);
      totalCorpusUses += ls.corpusCount || 0;
    });

    return {
      totalLabelsets: labelsets.length,
      totalLabels,
      totalCorpusUses,
      sharedCount: filterCounts.shared,
    };
  }, [labelsets, filterCounts.shared]);

  // Handlers
  const handleCreateLabelset = (values: CreateLabelsetInputs) => {
    createLabelset({ variables: { ...values } })
      .then(() => {
        refetch();
        showNewLabelsetModal(false);
        toast.success("Successfully created new label set.");
      })
      .catch(() => {
        toast.error("Failed to create new label set.");
        showNewLabelsetModal(false);
      });
  };

  const handleDeleteLabelset = () => {
    if (!labelset_to_delete?.id) return;

    deleteLabelset({ variables: { id: labelset_to_delete.id } })
      .then((result) => {
        if (result.data?.deleteLabelset?.ok) {
          toast.success("Label set deleted successfully.");
          refetch();
        } else {
          toast.error(
            result.data?.deleteLabelset?.message ||
              "Failed to delete label set."
          );
        }
        deletingLabelset(null);
      })
      .catch(() => {
        toast.error("Failed to delete label set.");
        deletingLabelset(null);
      });
  };

  const handleFetchMore = useCallback(() => {
    if (!loading && data?.labelsets?.pageInfo?.hasNextPage) {
      fetchMore({
        variables: {
          cursor: data.labelsets.pageInfo.endCursor,
        },
      });
    }
  }, [loading, data, fetchMore]);

  const handleOpenContextMenu = useCallback(
    (e: React.MouseEvent, labelsetId: string) => {
      e.preventDefault();
      e.stopPropagation();
      setMenuPosition({ x: e.clientX, y: e.clientY });
      setOpenMenuId(labelsetId);
    },
    []
  );

  const handleCloseMenu = useCallback(() => {
    setOpenMenuId(null);
    setMenuPosition(null);
  }, []);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = () => {
      if (openMenuId) {
        handleCloseMenu();
      }
    };

    if (openMenuId) {
      const timer = setTimeout(() => {
        document.addEventListener("click", handleClickOutside);
      }, 100);
      return () => {
        clearTimeout(timer);
        document.removeEventListener("click", handleClickOutside);
      };
    }
  }, [openMenuId, handleCloseMenu]);

  // Determine section title based on filter
  const getSectionTitle = () => {
    switch (activeFilter) {
      case "my":
        return "My Label Sets";
      case "shared":
        return "Shared with Me";
      case "public":
        return "Public Label Sets";
      default:
        return "Your Label Sets";
    }
  };

  return (
    <PageContainer>
      <ContentContainer>
        {/* Modals */}
        {show_new_label_modal && (
          <CRUDModal
            open={show_new_label_modal}
            mode="CREATE"
            oldInstance={{}}
            modelName="labelset"
            onSubmit={handleCreateLabelset}
            onClose={() => showNewLabelsetModal(false)}
            hasFile={true}
            fileField="icon"
            fileLabel="Labelset Icon"
            fileIsImage={true}
            acceptedFileTypes="image/*"
            loading={create_labelset_loading}
            validate={validateTitleAndDescription}
            renderForm={(formData, onChange, disabled) => (
              <LabelSetFormFields
                formData={formData}
                onChange={onChange}
                disabled={disabled}
              />
            )}
          />
        )}

        {/* Delete Confirmation Modal */}
        <ConfirmModal
          message={`Are you sure you want to delete "${
            labelset_to_delete?.title || "this label set"
          }"? This action cannot be undone.`}
          visible={Boolean(labelset_to_delete)}
          yesAction={handleDeleteLabelset}
          noAction={() => deletingLabelset(null)}
          toggleModal={() => deletingLabelset(null)}
        />

        {/* Hero Section */}
        <HeroSection>
          <HeroTitle>
            Organize your <span>labels</span>
          </HeroTitle>
          <HeroSubtitle>
            Create and manage label sets for consistent document annotation
            across your corpuses.
          </HeroSubtitle>

          {/* Search */}
          <SearchContainer>
            <SearchBox
              placeholder="Search label sets..."
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
              value={stats.totalLabelsets.toString()}
              label="Label Sets"
              sublabel="in your library"
            />
            <StatBlock
              value={stats.totalLabels.toLocaleString()}
              label="Total Labels"
              sublabel="across all sets"
            />
            <StatBlock
              value={stats.totalCorpusUses.toString()}
              label="Corpus Uses"
              sublabel="total deployments"
            />
            <StatBlock
              value={stats.sharedCount.toString()}
              label="Shared"
              sublabel="with collaborators"
            />
          </StatGrid>
        </StatsContainer>

        {/* Label Sets List Section */}
        <ListContainer>
          {/* Cover the list only on the initial load — fetchMore keeps existing rows visible. */}
          <LoadingOverlay
            active={loading && filteredLabelsets.length === 0}
            size="large"
            content="Loading label sets..."
          />

          <SectionHeader>
            <SectionTitle>{getSectionTitle()}</SectionTitle>
            {isAuthenticated && (
              <ActionButtons>
                <Button
                  variant="primary"
                  size="sm"
                  leftIcon={<Plus size={16} />}
                  onClick={() => showNewLabelsetModal(true)}
                >
                  New Label Set
                </Button>
              </ActionButtons>
            )}
          </SectionHeader>

          {filteredLabelsets.length > 0 ? (
            <>
              <CollectionList gap="md">
                {filteredLabelsets.map((labelset) => (
                  <LabelSetListCard
                    key={labelset.id}
                    labelset={labelset}
                    currentUserEmail={currentUserEmail}
                    onEdit={(ls) => editingLabelset(ls)}
                    onView={(ls) => navigate(getLabelsetUrl(ls))}
                    onDelete={(ls) => deletingLabelset(ls)}
                    isMenuOpen={openMenuId === labelset.id}
                    menuPosition={
                      openMenuId === labelset.id ? menuPosition : null
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
                message="Loading more label sets…"
                data-testid="labelsets-fetch-more-spinner"
              />
            </>
          ) : !loading ? (
            <EmptyStateWrapper>
              <EmptyState
                icon={<TagsIcon />}
                title={
                  activeFilter !== "all"
                    ? `No ${getSectionTitle().toLowerCase()}`
                    : "No label sets yet"
                }
                description={
                  activeFilter !== "all"
                    ? "Try selecting a different filter to see more label sets."
                    : "Create your first label set to start organizing annotations across your documents."
                }
                size="lg"
                action={
                  activeFilter === "all" && isAuthenticated ? (
                    <Button
                      variant="primary"
                      leftIcon={<Plus size={16} />}
                      onClick={() => showNewLabelsetModal(true)}
                    >
                      Create Your First Label Set
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

export default Labelsets;
