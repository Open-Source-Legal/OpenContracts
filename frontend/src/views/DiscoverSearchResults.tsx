// Cross-content Discover search: one page that fans out across discussions, annotations, corpuses, and notes.

import React, { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import styled from "styled-components";
import { useQuery } from "@apollo/client";
import {
  MessageSquare,
  Bookmark,
  Database,
  StickyNote,
  Layers,
} from "lucide-react";
import { FilterTabs, SearchBox } from "@os-legal/ui";
import type { FilterTabItem } from "@os-legal/ui";
import { OS_LEGAL_COLORS } from "../assets/configurations/osLegalStyles";
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

import {
  GET_CONVERSATIONS,
  GetConversationsInputs,
  GetConversationsOutputs,
  GET_CORPUSES,
  GetCorpusesInputs,
  GetCorpusesOutputs,
  SEARCH_ANNOTATIONS_FOR_MENTION,
  SearchAnnotationsForMentionInput,
  SearchAnnotationsForMentionOutput,
  SEARCH_NOTES_FOR_MENTION,
  SearchNotesForMentionInput,
  SearchNotesForMentionOutput,
} from "../graphql/queries";
import { ThreadListItem } from "../components/threads/ThreadListItem";
import { ModernLoadingDisplay } from "../components/widgets/ModernLoadingDisplay";
import {
  CORPUS_COLORS,
  CORPUS_FONTS,
} from "../components/threads/styles/discussionStyles";
import { getCorpusUrl, getDocumentUrl } from "../utils/navigationUtils";
import { stripMarkdown } from "../utils/formatters";
import { useDebouncedValue } from "../utils/hooks";
import {
  DISCOVER_SEARCH_ALL_TAB_PREVIEW,
  DISCOVER_SEARCH_DEBOUNCE_MS,
  DISCOVER_SEARCH_ENTITY_TAB_LIMIT,
  FILTER_TAB_ICON_SIZE,
} from "../assets/configurations/constants";
import { ConversationType } from "../types/graphql-api";

// ---------------------------------------------------------------------------
// Styled primitives
// ---------------------------------------------------------------------------

const SubTitle = styled.p`
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.95rem;
  color: ${CORPUS_COLORS.slate[500]};
  margin: 0 0 1.25rem 0;
`;

const SearchContainer = styled.div`
  flex: 1;
  min-width: 16rem;
  max-width: 28rem;
`;

const SectionContainer = styled.section`
  margin-bottom: 2rem;
`;

const ResultGrid = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
`;

const EmptyState = styled.div`
  text-align: center;
  padding: 1.25rem 1rem;
  color: ${CORPUS_COLORS.slate[400]};
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.875rem;
`;

const LoadingContainer = styled.div`
  padding: 1.25rem;
  display: flex;
  justify-content: center;
`;

// ---------------------------------------------------------------------------
// Result row primitives
// ---------------------------------------------------------------------------

const ResultCard = styled.button`
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  padding: 1rem 1.25rem;
  cursor: pointer;
  transition: border-color 0.15s ease, box-shadow 0.15s ease,
    transform 0.15s ease;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  text-align: left;
  font: inherit;
  color: inherit;
  width: 100%;

  &:hover:not(:disabled) {
    border-color: ${OS_LEGAL_COLORS.borderHover};
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
    transform: translateY(-1px);
  }

  &:focus-visible {
    outline: 2px solid ${OS_LEGAL_COLORS.primaryBlue};
    outline-offset: 2px;
  }

  &:disabled {
    cursor: not-allowed;
    opacity: 0.55;
  }
`;

const ResultTitle = styled.div`
  font-family: ${CORPUS_FONTS.sans};
  font-size: 1rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  line-height: 1.35;
`;

const ResultSnippet = styled.div`
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
`;

const ResultMeta = styled.div`
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  display: flex;
  gap: 0.5rem;
  align-items: center;
  flex-wrap: wrap;
`;

const LabelDot = styled.span<{ $color?: string | null }>`
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: ${(p) => p.$color || OS_LEGAL_COLORS.borderHover};
  display: inline-block;
`;

interface ResultRowBaseProps {
  title: string;
  snippet?: string | null;
  meta?: React.ReactNode;
  onClick: () => void;
  leadingDot?: { color?: string | null };
  /**
   * Disable the click handler and visually mute the row when the
   * resolved navigation target is unreachable (e.g., missing slugs
   * caused getCorpusUrl/getDocumentUrl to return "#").
   */
  disabled?: boolean;
  disabledReason?: string;
}

const ResultRow: React.FC<ResultRowBaseProps> = ({
  title,
  snippet,
  meta,
  onClick,
  leadingDot,
  disabled,
  disabledReason,
}) => (
  <ResultCard
    type="button"
    onClick={onClick}
    disabled={disabled}
    aria-disabled={disabled || undefined}
    title={disabled ? disabledReason : undefined}
  >
    <ResultTitle>
      {leadingDot ? (
        <LabelDot
          $color={leadingDot.color}
          style={{ marginRight: "0.5rem", verticalAlign: "middle" }}
        />
      ) : null}
      {title}
    </ResultTitle>
    {snippet ? <ResultSnippet>{snippet}</ResultSnippet> : null}
    {meta ? <ResultMeta>{meta}</ResultMeta> : null}
  </ResultCard>
);

type EntityTab = "all" | "discussions" | "annotations" | "corpuses" | "notes";

const VALID_TABS = new Set<EntityTab>([
  "all",
  "discussions",
  "annotations",
  "corpuses",
  "notes",
]);

const TAB_ITEMS: FilterTabItem[] = [
  {
    id: "all",
    label: "All",
    icon: <Layers size={FILTER_TAB_ICON_SIZE} />,
  },
  {
    id: "discussions",
    label: "Discussions",
    icon: <MessageSquare size={FILTER_TAB_ICON_SIZE} />,
  },
  {
    id: "annotations",
    label: "Annotations",
    icon: <Bookmark size={FILTER_TAB_ICON_SIZE} />,
  },
  {
    id: "corpuses",
    label: "Collections",
    icon: <Database size={FILTER_TAB_ICON_SIZE} />,
  },
  {
    id: "notes",
    label: "Notes",
    icon: <StickyNote size={FILTER_TAB_ICON_SIZE} />,
  },
];

// ---------------------------------------------------------------------------
// Sections
// ---------------------------------------------------------------------------

interface SectionWrapperProps {
  title: string;
  icon: React.ReactNode;
  iconColor: string;
  countLabel: string;
  loading: boolean;
  empty: boolean;
  emptyMessage: string;
  errorMessage?: string;
  children: React.ReactNode;
}

const Section: React.FC<SectionWrapperProps> = ({
  title,
  icon,
  iconColor,
  countLabel,
  loading,
  empty,
  emptyMessage,
  errorMessage,
  children,
}) => (
  <SectionContainer>
    <DiscoverySectionHeader>
      <DiscoverySectionIcon $color={iconColor}>{icon}</DiscoverySectionIcon>
      <DiscoverySectionTitle>{title}</DiscoverySectionTitle>
      <DiscoverySectionCount>
        {loading ? "…" : errorMessage ? "error" : countLabel}
      </DiscoverySectionCount>
    </DiscoverySectionHeader>
    {loading ? (
      <LoadingContainer>
        <ModernLoadingDisplay message="Searching…" size="small" />
      </LoadingContainer>
    ) : errorMessage ? (
      <EmptyState role="alert">{errorMessage}</EmptyState>
    ) : empty ? (
      <EmptyState>{emptyMessage}</EmptyState>
    ) : (
      <ResultGrid>{children}</ResultGrid>
    )}
  </SectionContainer>
);

const SECTION_ERROR_FALLBACK =
  "We couldn't load these results. Please try again.";

// Shown via the native title tooltip on rows whose target URL is "#"
// (missing slugs in the data — clicking would silently no-op otherwise).
const UNROUTEABLE_ROW_TOOLTIP =
  "This result is missing the data needed to open it.";

const DISCUSSION_GRADIENT = `linear-gradient(135deg, ${CORPUS_COLORS.teal[600]} 0%, ${CORPUS_COLORS.teal[800]} 100%)`;
const ANNOTATION_GRADIENT = `linear-gradient(135deg, ${OS_LEGAL_COLORS.primaryBlue} 0%, ${OS_LEGAL_COLORS.primaryBlueHover} 100%)`;
const CORPUS_GRADIENT = `linear-gradient(135deg, ${CORPUS_COLORS.slate[600]} 0%, ${CORPUS_COLORS.slate[800]} 100%)`;
const NOTE_GRADIENT = `linear-gradient(135deg, ${OS_LEGAL_COLORS.folderIcon} 0%, ${OS_LEGAL_COLORS.folderIconDark} 100%)`;

// --- Discussions ----------------------------------------------------------

interface DiscussionsSectionProps {
  query: string;
  limit: number;
}

const DiscussionsSection: React.FC<DiscussionsSectionProps> = ({
  query,
  limit,
}) => {
  const { data, loading, error } = useQuery<
    GetConversationsOutputs,
    GetConversationsInputs
  >(GET_CONVERSATIONS, {
    variables: {
      conversationType: "THREAD",
      title_Contains: query || undefined,
      limit,
    },
    fetchPolicy: "cache-and-network",
    nextFetchPolicy: "cache-first",
    skip: !query,
  });

  const threads = (data?.conversations.edges ?? [])
    .map((e) => e?.node)
    .filter((n): n is NonNullable<typeof n> => Boolean(n) && !n?.deletedAt);
  // Count what we render — server `totalCount` includes soft-deleted
  // threads, so it would diverge from the visible row count.
  const total = threads.length;

  return (
    <Section
      title="Discussions"
      icon={<MessageSquare size={FILTER_TAB_ICON_SIZE} />}
      iconColor={DISCUSSION_GRADIENT}
      countLabel={`${total} ${total === 1 ? "thread" : "threads"}`}
      loading={loading && !data}
      empty={!loading && threads.length === 0}
      emptyMessage="No matching discussions"
      errorMessage={error && !data ? SECTION_ERROR_FALLBACK : undefined}
    >
      {threads.map((thread) => (
        <ThreadListItem key={thread.id} thread={thread as ConversationType} />
      ))}
    </Section>
  );
};

// --- Annotations ----------------------------------------------------------

interface AnnotationsSectionProps {
  query: string;
  limit: number;
}

const AnnotationsSection: React.FC<AnnotationsSectionProps> = ({
  query,
  limit,
}) => {
  const navigate = useNavigate();
  const { data, loading, error } = useQuery<
    SearchAnnotationsForMentionOutput,
    SearchAnnotationsForMentionInput
  >(SEARCH_ANNOTATIONS_FOR_MENTION, {
    variables: { textSearch: query, first: limit },
    fetchPolicy: "cache-and-network",
    nextFetchPolicy: "cache-first",
    skip: !query,
  });

  // Drop edges whose annotation lost its parent document — without a
  // document we can't build a URL or render the meta row, and the
  // backend can null it out for visibility/soft-delete reasons.
  const rows = (data?.searchAnnotationsForMention.edges ?? []).filter(
    (e): e is NonNullable<typeof e> => Boolean(e?.node && e.node.document)
  );

  return (
    <Section
      title="Annotations"
      icon={<Bookmark size={FILTER_TAB_ICON_SIZE} />}
      iconColor={ANNOTATION_GRADIENT}
      countLabel={`${rows.length} ${
        rows.length === 1 ? "annotation" : "annotations"
      }`}
      loading={loading && !data}
      empty={!loading && rows.length === 0}
      emptyMessage="No matching annotations"
      errorMessage={error && !data ? SECTION_ERROR_FALLBACK : undefined}
    >
      {rows.map(({ node }) => {
        const docUrl = getDocumentUrl(node.document, node.corpus, {
          annotationIds: [node.id],
        });
        const unrouteable = docUrl === "#";
        const label = node.annotationLabel?.text;
        const title = node.rawText
          ? node.rawText.length > 140
            ? `${node.rawText.slice(0, 140)}…`
            : node.rawText
          : label || "Annotation";
        return (
          <ResultRow
            key={node.id}
            leadingDot={{ color: node.annotationLabel?.color }}
            title={title}
            snippet={label && node.rawText ? `Label: ${label}` : undefined}
            meta={
              <>
                <span>{node.document.title}</span>
                {node.corpus ? <span>· {node.corpus.title}</span> : null}
                {node.page != null ? <span>· p. {node.page + 1}</span> : null}
              </>
            }
            disabled={unrouteable}
            disabledReason={UNROUTEABLE_ROW_TOOLTIP}
            onClick={() => navigate(docUrl)}
          />
        );
      })}
    </Section>
  );
};

// --- Corpuses -------------------------------------------------------------

interface CorpusesSectionProps {
  query: string;
  limit: number;
}

const CorpusesSection: React.FC<CorpusesSectionProps> = ({ query, limit }) => {
  const navigate = useNavigate();
  const { data, loading, error } = useQuery<
    GetCorpusesOutputs,
    GetCorpusesInputs
  >(GET_CORPUSES, {
    variables: { textSearch: query, limit },
    fetchPolicy: "cache-and-network",
    nextFetchPolicy: "cache-first",
    skip: !query,
  });

  const rows = (data?.corpuses.edges ?? [])
    .map((e) => e.node)
    .filter((n): n is NonNullable<typeof n> => Boolean(n));

  return (
    <Section
      title="Collections"
      icon={<Database size={FILTER_TAB_ICON_SIZE} />}
      iconColor={CORPUS_GRADIENT}
      countLabel={`${rows.length} ${
        rows.length === 1 ? "collection" : "collections"
      }`}
      loading={loading && !data}
      empty={!loading && rows.length === 0}
      emptyMessage="No matching collections"
      errorMessage={error && !data ? SECTION_ERROR_FALLBACK : undefined}
    >
      {rows.map((corpus) => {
        const url = getCorpusUrl(corpus);
        const unrouteable = url === "#";
        return (
          <ResultRow
            key={corpus.id}
            title={corpus.title || "Untitled collection"}
            snippet={corpus.description || undefined}
            meta={
              <>
                {corpus.creator?.slug ? (
                  <span>by {corpus.creator.slug}</span>
                ) : null}
                {typeof corpus.documentCount === "number" ? (
                  <span>· {corpus.documentCount} docs</span>
                ) : null}
                {corpus.isPublic ? <span>· public</span> : null}
              </>
            }
            disabled={unrouteable}
            disabledReason={UNROUTEABLE_ROW_TOOLTIP}
            onClick={() => navigate(url)}
          />
        );
      })}
    </Section>
  );
};

// --- Notes ----------------------------------------------------------------

interface NotesSectionProps {
  query: string;
  limit: number;
}

const NotesSection: React.FC<NotesSectionProps> = ({ query, limit }) => {
  const navigate = useNavigate();
  const { data, loading, error } = useQuery<
    SearchNotesForMentionOutput,
    SearchNotesForMentionInput
  >(SEARCH_NOTES_FOR_MENTION, {
    variables: { textSearch: query, first: limit },
    fetchPolicy: "cache-and-network",
    nextFetchPolicy: "cache-first",
    skip: !query,
  });

  // Drop edges whose note has lost its parent document — without it
  // there's no routeable target and the meta row would crash on null.
  const rows = (data?.searchNotesForMention.edges ?? []).filter(
    (e): e is NonNullable<typeof e> => Boolean(e?.node && e.node.document)
  );

  return (
    <Section
      title="Notes"
      icon={<StickyNote size={FILTER_TAB_ICON_SIZE} />}
      iconColor={NOTE_GRADIENT}
      countLabel={`${rows.length} ${rows.length === 1 ? "note" : "notes"}`}
      loading={loading && !data}
      empty={!loading && rows.length === 0}
      emptyMessage="No matching notes"
      errorMessage={error && !data ? SECTION_ERROR_FALLBACK : undefined}
    >
      {rows.map(({ node }) => {
        const url = getDocumentUrl(node.document, node.corpus, {
          noteId: node.id,
        });
        const unrouteable = url === "#";
        const cleaned = stripMarkdown(node.contentPreview ?? "");
        const snippet = cleaned ? cleaned.slice(0, 220) : undefined;
        return (
          <ResultRow
            key={node.id}
            title={node.title}
            snippet={snippet}
            meta={
              <>
                <span>{node.document.title}</span>
                {node.corpus ? <span>· {node.corpus.title}</span> : null}
                {node.creator?.username ? (
                  <span>· by {node.creator.username}</span>
                ) : null}
              </>
            }
            disabled={unrouteable}
            disabledReason={UNROUTEABLE_ROW_TOOLTIP}
            onClick={() => navigate(url)}
          />
        );
      })}
    </Section>
  );
};

// ---------------------------------------------------------------------------
// View
// ---------------------------------------------------------------------------

export const DiscoverSearchResults: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialQuery = searchParams.get("q") ?? "";
  const initialTab = (searchParams.get("type") ?? "all") as EntityTab;

  const [searchInput, setSearchInput] = useState(initialQuery);
  const [activeTab, setActiveTab] = useState<EntityTab>(
    VALID_TABS.has(initialTab) ? initialTab : "all"
  );
  const debouncedQuery = useDebouncedValue(
    searchInput.trim(),
    DISCOVER_SEARCH_DEBOUNCE_MS
  );

  // URL sync: keep ?q= and ?type= in step with local state (replace, not push).
  // The functional setSearchParams form lets us read the latest params without
  // adding `searchParams` to the deps array (which would cause an infinite loop).
  useEffect(() => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (debouncedQuery) next.set("q", debouncedQuery);
        else next.delete("q");
        if (activeTab !== "all") next.set("type", activeTab);
        else next.delete("type");
        return next;
      },
      { replace: true }
    );
  }, [debouncedQuery, activeTab, setSearchParams]);

  const showAll = activeTab === "all";
  const trimmed = debouncedQuery;
  const showEmptyPrompt = !trimmed;

  return (
    <DiscoveryContainer>
      <DiscoveryHeader>
        <DiscoveryTitle $marginBottom="0.25rem">Search</DiscoveryTitle>
        <SubTitle>
          Find discussions, annotations, collections, and notes you can access.
        </SubTitle>
        <DiscoveryFilterBar>
          <SearchContainer>
            <SearchBox
              placeholder="Search across legal knowledge…"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              hideButton
            />
          </SearchContainer>
          <FilterTabs
            items={TAB_ITEMS}
            value={activeTab}
            onChange={(id) => {
              if (VALID_TABS.has(id as EntityTab)) {
                setActiveTab(id as EntityTab);
              }
            }}
          />
        </DiscoveryFilterBar>
      </DiscoveryHeader>

      {showEmptyPrompt ? (
        <EmptyState>Type to search across content you can access.</EmptyState>
      ) : (
        <>
          {(showAll || activeTab === "discussions") && (
            <DiscussionsSection
              query={trimmed}
              limit={
                showAll
                  ? DISCOVER_SEARCH_ALL_TAB_PREVIEW
                  : DISCOVER_SEARCH_ENTITY_TAB_LIMIT
              }
            />
          )}
          {(showAll || activeTab === "annotations") && (
            <AnnotationsSection
              query={trimmed}
              limit={
                showAll
                  ? DISCOVER_SEARCH_ALL_TAB_PREVIEW
                  : DISCOVER_SEARCH_ENTITY_TAB_LIMIT
              }
            />
          )}
          {(showAll || activeTab === "corpuses") && (
            <CorpusesSection
              query={trimmed}
              limit={
                showAll
                  ? DISCOVER_SEARCH_ALL_TAB_PREVIEW
                  : DISCOVER_SEARCH_ENTITY_TAB_LIMIT
              }
            />
          )}
          {(showAll || activeTab === "notes") && (
            <NotesSection
              query={trimmed}
              limit={
                showAll
                  ? DISCOVER_SEARCH_ALL_TAB_PREVIEW
                  : DISCOVER_SEARCH_ENTITY_TAB_LIMIT
              }
            />
          )}
        </>
      )}
    </DiscoveryContainer>
  );
};

export default DiscoverSearchResults;
