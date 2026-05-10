import React, { useState, useCallback, useEffect, useMemo } from "react";
import styled from "styled-components";
import { NetworkStatus, useMutation, useReactiveVar } from "@apollo/client";
import { useNavigate, useLocation } from "react-router-dom";
import { toast } from "react-toastify";
import { CollectionList, EmptyState, Button } from "@os-legal/ui";
import { Plus } from "lucide-react";

import { ExtractListCard, ExtractCardItem } from "./ExtractListCard";
import { LoadingOverlay } from "../common/LoadingOverlay";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { FetchMoreOnVisible } from "../widgets/infinite_scroll/FetchMoreOnVisible";
import { FetchMoreFooter } from "../widgets/infinite_scroll/FetchMoreFooter";
import { ExtractType, CorpusType, PageInfo } from "../../types/graphql-api";
import {
  showCreateExtractModal,
  selectedExtractIds,
  userObj,
} from "../../graphql/cache";
import {
  REQUEST_DELETE_EXTRACT,
  RequestDeleteExtractInputType,
  RequestDeleteExtractOutputType,
} from "../../graphql/mutations";
import { updateAnnotationSelectionParams } from "../../utils/navigationUtils";

// Modern styled components matching standalone Extracts view
const Container = styled.div`
  width: 100%;
  position: relative;
  padding: 1rem;
  background: ${OS_LEGAL_COLORS.background};
`;

const ListContainer = styled.section`
  position: relative;
  min-height: 200px;
`;

const EmptyStateWrapper = styled.div`
  padding: 48px 24px;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 16px;
`;

// Table icon for empty state
const TableIcon = () => (
  <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
    <path
      d="M6 8a4 4 0 014-4h20a4 4 0 014 4v24a4 4 0 01-4 4H10a4 4 0 01-4-4V8zm4-2a2 2 0 00-2 2v6h24V8a2 2 0 00-2-2H10zm22 10H8v16a2 2 0 002 2h20a2 2 0 002-2V16zm-22 4h8v4H10v-4zm10 0h10v4H20v-4zm-10 6h8v4H10v-4zm10 0h10v4H20v-4z"
      fill="currentColor"
    />
  </svg>
);

interface ExtractCardsProps {
  style?: Record<string, any>;
  read_only?: boolean;
  extracts: ExtractType[];
  opened_corpus: CorpusType | null;
  pageInfo: PageInfo | undefined;
  loading: boolean;
  /** NetworkStatus from useQuery. When omitted, footer falls back to `loading && hasNextPage`. */
  networkStatus?: NetworkStatus;
  loading_message: string;
  fetchMore: (args?: any) => void | any;
  /** If true, clicking selects via URL params instead of navigating away */
  useInlineSelection?: boolean;
  /** Filter extracts by status: all, running, completed, failed, not_started */
  activeFilter?: string;
}

export const ExtractCards = ({
  style,
  extracts,
  opened_corpus,
  loading_message,
  loading,
  networkStatus,
  fetchMore,
  pageInfo,
  useInlineSelection = false,
  activeFilter = "all",
}: ExtractCardsProps) => {
  const navigate = useNavigate();
  const location = useLocation();
  const currentUser = useReactiveVar(userObj);
  const selected_extract_ids = useReactiveVar(selectedExtractIds);
  // Use userObj for auth check - consistent with NavMenu pattern
  const isAuthenticated = Boolean(currentUser);

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

  // Context menu state
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [menuPosition, setMenuPosition] = useState<{
    x: number;
    y: number;
  } | null>(null);

  // Delete mutation
  const [tryDeleteExtract] = useMutation<
    RequestDeleteExtractOutputType,
    RequestDeleteExtractInputType
  >(REQUEST_DELETE_EXTRACT, {
    onCompleted: () => {
      toast.success("Extract deleted successfully");
    },
    onError: () => {
      toast.error("Failed to delete extract");
    },
  });

  // Handle click - either navigate or select inline
  const handleSelectExtract = useCallback(
    (extract: ExtractCardItem) => {
      if (useInlineSelection) {
        // Select via URL params - CentralRouteManager will update selectedExtractIds
        updateAnnotationSelectionParams(location, navigate, {
          extractIds: [extract.id],
        });
      } else {
        // Navigate to full extract page
        navigate(`/extracts/${extract.id}`);
      }
    },
    [useInlineSelection, location, navigate]
  );

  const handleDeleteExtract = useCallback(
    (extract: ExtractCardItem) => {
      tryDeleteExtract({ variables: { id: extract.id } });
    },
    [tryDeleteExtract]
  );

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

  const handleFetchMore = useCallback(() => {
    if (!loading && pageInfo?.hasNextPage) {
      fetchMore({
        variables: {
          cursor: pageInfo.endCursor,
        },
      });
    }
  }, [loading, pageInfo, fetchMore]);

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

  return (
    <Container style={style}>
      {/* Cover the list only on the initial load — fetchMore keeps existing rows visible. */}
      <LoadingOverlay
        active={loading && filteredExtracts.length === 0}
        size="large"
        content={loading_message}
      />

      <ListContainer>
        {filteredExtracts.length > 0 ? (
          <>
            <CollectionList gap="md">
              {filteredExtracts.map((extract) => (
                <ExtractListCard
                  key={extract.id}
                  extract={extract}
                  onView={handleSelectExtract}
                  onDelete={handleDeleteExtract}
                  isMenuOpen={openMenuId === extract.id}
                  menuPosition={openMenuId === extract.id ? menuPosition : null}
                  onOpenMenu={handleOpenContextMenu}
                  onCloseMenu={handleCloseMenu}
                  isSelected={
                    useInlineSelection &&
                    selected_extract_ids.includes(extract.id)
                  }
                />
              ))}
            </CollectionList>

            <FetchMoreOnVisible fetchNextPage={handleFetchMore} />
            <FetchMoreFooter
              visible={
                networkStatus === NetworkStatus.fetchMore ||
                (networkStatus === undefined &&
                  loading &&
                  Boolean(pageInfo?.hasNextPage))
              }
              message="Loading more extracts…"
              data-testid="extract-cards-fetch-more-spinner"
            />
          </>
        ) : !loading ? (
          <EmptyStateWrapper>
            <EmptyState
              icon={<TableIcon />}
              title={
                activeFilter !== "all"
                  ? `No ${activeFilter.replace("_", " ")} extracts`
                  : "No extracts in this corpus"
              }
              description={
                activeFilter !== "all"
                  ? "Try selecting a different filter to see more extracts."
                  : "Create an extract to pull structured data from documents in this corpus."
              }
              size="lg"
              action={
                activeFilter === "all" && isAuthenticated ? (
                  <Button
                    variant="primary"
                    leftIcon={<Plus size={16} />}
                    onClick={() => showCreateExtractModal(true)}
                  >
                    Create Extract
                  </Button>
                ) : undefined
              }
            />
          </EmptyStateWrapper>
        ) : null}
      </ListContainer>
    </Container>
  );
};
