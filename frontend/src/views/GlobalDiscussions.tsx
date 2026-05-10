import React, { useState, useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import styled from "styled-components";
import {
  accentAlpha,
  OS_LEGAL_COLORS,
} from "../assets/configurations/osLegalStyles";
import {
  DiscoveryContainer,
  DiscoveryHeader,
  DiscoveryTitle,
  DiscoveryFilterBar,
  DiscoverySectionHeader,
  DiscoverySectionIcon,
  DiscoverySectionTitle,
  DiscoverySectionCount,
} from "../components/layout/DiscoveryViewLayout";
import { motion } from "framer-motion";
import {
  MessageSquare,
  MessageCircle,
  Database,
  FileText,
  Plus,
} from "lucide-react";
import { FilterTabs, SearchBox } from "@os-legal/ui";
import type { FilterTabItem } from "@os-legal/ui";
import { useQuery } from "@apollo/client";
import {
  GET_CONVERSATIONS,
  GetConversationsInputs,
  GetConversationsOutputs,
} from "../graphql/queries";
import { ThreadListItem } from "../components/threads/ThreadListItem";
import {
  CORPUS_COLORS,
  CORPUS_FONTS,
  CORPUS_RADII,
  mediaQuery,
} from "../components/threads/styles/discussionStyles";
import { ModernLoadingDisplay } from "../components/widgets/ModernLoadingDisplay";
import { FILTER_TAB_ICON_SIZE } from "../assets/configurations/constants";

// Custom hook for debounced value
function useDebouncedValue<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
}

const TitleRow = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.25rem;
`;

const SearchContainer = styled.div`
  flex: 1;
  min-width: 12.5rem;
  max-width: 20rem;

  ${mediaQuery.mobile} {
    min-width: 100%;
    max-width: none;
  }
`;

const FAB = styled(motion.button)`
  position: fixed;
  bottom: 2rem;
  right: 2rem;
  width: 3rem;
  height: 3rem;
  border-radius: ${CORPUS_RADII.xl};
  background: linear-gradient(
    135deg,
    ${CORPUS_COLORS.teal[600]} 0%,
    ${CORPUS_COLORS.teal[700]} 100%
  );
  border: none;
  color: ${CORPUS_COLORS.white};
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 8px 24px ${accentAlpha(0.4)};
  z-index: 100;

  &:hover {
    box-shadow: 0 12px 32px ${accentAlpha(0.5)};
  }

  ${mediaQuery.mobile} {
    bottom: 1rem;
    right: 1rem;
  }
`;

const SectionContainer = styled(motion.div)`
  margin-bottom: 2rem;
`;

const ThreadGrid = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
`;

const EmptyState = styled.div`
  text-align: center;
  padding: 1.5rem 1rem;
  color: ${CORPUS_COLORS.slate[400]};
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.8125rem;
`;

const LoadingContainer = styled.div`
  padding: 2rem;
  display: flex;
  justify-content: center;
`;

type FilterTab = "all" | "corpus" | "document" | "general";

const VALID_FILTER_TABS = new Set<FilterTab>([
  "all",
  "corpus",
  "document",
  "general",
]);

const FILTER_ITEMS: FilterTabItem[] = [
  {
    id: "all",
    label: "All",
    icon: <MessageSquare size={FILTER_TAB_ICON_SIZE} />,
  },
  {
    id: "corpus",
    label: "Corpus",
    icon: <Database size={FILTER_TAB_ICON_SIZE} />,
  },
  {
    id: "document",
    label: "Document",
    icon: <FileText size={FILTER_TAB_ICON_SIZE} />,
  },
  {
    id: "general",
    label: "General",
    icon: <MessageCircle size={FILTER_TAB_ICON_SIZE} />,
  },
];

/**
 * Thread section component - handles its own query
 */
interface ThreadSectionProps {
  title: string;
  icon: React.ReactNode;
  iconColor: string;
  filterType: "corpus" | "document" | "general";
  searchQuery: string;
}

const ThreadSection: React.FC<ThreadSectionProps> = ({
  title,
  icon,
  iconColor,
  filterType,
  searchQuery,
}) => {
  // Memoize variables to prevent unnecessary query restarts
  const variables = useMemo((): GetConversationsInputs => {
    const base: GetConversationsInputs = {
      conversationType: "THREAD",
      limit: 20,
      title_Contains: searchQuery || undefined,
    };

    switch (filterType) {
      case "corpus":
        return { ...base, hasCorpus: true, hasDocument: false };
      case "document":
        return { ...base, hasDocument: true };
      case "general":
        return { ...base, hasCorpus: false, hasDocument: false };
    }
  }, [filterType, searchQuery]);

  const { data, loading } = useQuery<
    GetConversationsOutputs,
    GetConversationsInputs
  >(GET_CONVERSATIONS, {
    variables,
    fetchPolicy: "cache-first",
    nextFetchPolicy: "cache-and-network",
  });

  const threads =
    data?.conversations?.edges
      ?.map((e) => e?.node)
      .filter((node): node is NonNullable<typeof node> => node != null)
      .filter((t) => !t?.deletedAt)
      .sort((a, b) => {
        // Pinned first, then by date
        if (a?.isPinned && !b?.isPinned) return -1;
        if (!a?.isPinned && b?.isPinned) return 1;
        return (
          new Date(b?.createdAt || 0).getTime() -
          new Date(a?.createdAt || 0).getTime()
        );
      }) || [];

  const totalCount = data?.conversations?.totalCount ?? threads.length;

  return (
    <SectionContainer
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
    >
      <DiscoverySectionHeader>
        <DiscoverySectionIcon $color={iconColor}>{icon}</DiscoverySectionIcon>
        <DiscoverySectionTitle>{title}</DiscoverySectionTitle>
        <DiscoverySectionCount>
          {loading
            ? "..."
            : `${totalCount} ${totalCount === 1 ? "thread" : "threads"}`}
        </DiscoverySectionCount>
      </DiscoverySectionHeader>

      {loading && !data ? (
        <LoadingContainer>
          <ModernLoadingDisplay message="Loading..." size="small" />
        </LoadingContainer>
      ) : (
        <ThreadGrid>
          {threads.length > 0 ? (
            threads.map((thread) => (
              <ThreadListItem key={thread.id} thread={thread} />
            ))
          ) : (
            <EmptyState>
              {searchQuery
                ? "No discussions match your search"
                : "No discussions yet"}
            </EmptyState>
          )}
        </ThreadGrid>
      )}
    </SectionContainer>
  );
};

/**
 * Global Discussions View
 * Shows all platform discussions with tabbed filtering
 * Uses server-side filtering for efficiency
 * Part of Issue #623
 */
export const GlobalDiscussions: React.FC = () => {
  const [searchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<FilterTab>("all");
  const [searchInput, setSearchInput] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);

  // Debounce the search input (300ms delay)
  const debouncedSearch = useDebouncedValue(searchInput, 300);

  // Initialize search input from URL parameter
  useEffect(() => {
    const urlSearch = searchParams.get("search");
    if (urlSearch) {
      setSearchInput(urlSearch);
    }
  }, [searchParams]);

  return (
    <DiscoveryContainer>
      <DiscoveryHeader>
        <TitleRow>
          <DiscoveryTitle>Discussions</DiscoveryTitle>
        </TitleRow>

        <DiscoveryFilterBar>
          <FilterTabs
            items={FILTER_ITEMS}
            value={activeTab}
            onChange={(id) => {
              if (VALID_FILTER_TABS.has(id as FilterTab)) {
                setActiveTab(id as FilterTab);
              }
            }}
          />

          <SearchContainer>
            <SearchBox
              placeholder="Search discussions..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              hideButton
            />
          </SearchContainer>
        </DiscoveryFilterBar>
      </DiscoveryHeader>

      {/* Corpus Discussions - show in "all" or "corpus" tabs */}
      {(activeTab === "all" || activeTab === "corpus") && (
        <ThreadSection
          title="Corpus Discussions"
          icon={<Database size={FILTER_TAB_ICON_SIZE} />}
          iconColor={`linear-gradient(135deg, ${CORPUS_COLORS.teal[600]} 0%, ${CORPUS_COLORS.teal[800]} 100%)`}
          filterType="corpus"
          searchQuery={debouncedSearch}
        />
      )}

      {/* Document Discussions - show in "all" or "document" tabs */}
      {(activeTab === "all" || activeTab === "document") && (
        <ThreadSection
          title="Document Discussions"
          icon={<FileText size={FILTER_TAB_ICON_SIZE} />}
          iconColor={`linear-gradient(135deg, ${OS_LEGAL_COLORS.primaryBlue} 0%, ${OS_LEGAL_COLORS.blueDark} 100%)`}
          filterType="document"
          searchQuery={debouncedSearch}
        />
      )}

      {/* General Discussions - show in "all" or "general" tabs */}
      {(activeTab === "all" || activeTab === "general") && (
        <ThreadSection
          title="General Discussions"
          icon={<MessageCircle size={FILTER_TAB_ICON_SIZE} />}
          iconColor={`linear-gradient(135deg, ${CORPUS_COLORS.slate[500]} 0%, ${CORPUS_COLORS.slate[700]} 100%)`}
          filterType="general"
          searchQuery={debouncedSearch}
        />
      )}

      <FAB
        onClick={() => setShowCreateModal(true)}
        whileHover={{ scale: 1.1 }}
        whileTap={{ scale: 0.9 }}
        aria-label="Create new discussion"
      >
        <Plus size={22} />
      </FAB>

      {/* Placeholder — CreateThread modal not yet implemented */}
      {showCreateModal && <div>Create thread modal placeholder</div>}
    </DiscoveryContainer>
  );
};
