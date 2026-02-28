import { useState, useEffect, useMemo } from "react";
import { useLazyQuery } from "@apollo/client";
import {
  SEARCH_USERS_FOR_MENTION,
  SearchUsersForMentionInput,
  SearchUsersForMentionOutput,
  SEARCH_CORPUSES_FOR_MENTION,
  SearchCorpusesForMentionInput,
  SearchCorpusesForMentionOutput,
  SEARCH_DOCUMENTS_FOR_MENTION,
  SearchDocumentsForMentionInput,
  SearchDocumentsForMentionOutput,
  SEARCH_ANNOTATIONS_FOR_MENTION,
  SearchAnnotationsForMentionInput,
  SearchAnnotationsForMentionOutput,
  SEARCH_AGENTS_FOR_MENTION,
  SearchAgentsForMentionInput,
  SearchAgentsForMentionOutput,
} from "../../../graphql/queries";
import {
  MENTION_PREVIEW_LENGTH,
  MENTION_SEARCH_DEBOUNCE_MS,
  MENTION_SEARCH_MIN_CHARS,
} from "../../../assets/configurations/constants";
import { sanitizeForMention } from "../../../utils/textSanitization";

export interface UnifiedMentionResource {
  id: string;
  type: "user" | "corpus" | "document" | "annotation" | "agent";
  title: string; // Display name
  subtitle?: string; // Context info
  metadata?: string; // Additional info

  // Type-specific data
  user?: {
    id: string;
    username: string;
    email?: string;
    slug?: string | null;
  };
  corpus?: {
    slug: string;
    creator: { slug: string };
  };
  document?: {
    slug: string;
    creator: { slug: string };
    corpus?: {
      slug: string;
      title: string;
      creator: { slug: string };
    };
  };
  annotation?: {
    rawText: string | null;
    page: number;
    label: {
      text: string;
      color: string;
    };
    document: {
      id: string;
      title: string;
      slug: string;
      creator: { slug: string };
    };
    corpus: {
      id: string;
      title: string;
      slug: string;
      creator: { slug: string };
    } | null;
  };
  agent?: {
    id: string;
    name: string;
    slug: string;
    description: string;
    scope: "GLOBAL" | "CORPUS";
    mentionFormat: string | null;
    corpus: {
      id: string;
      title: string;
    } | null;
  };
}

export interface CategorizedResults {
  users: UnifiedMentionResource[];
  corpuses: UnifiedMentionResource[];
  documents: UnifiedMentionResource[];
  annotations: UnifiedMentionResource[];
  agents: UnifiedMentionResource[];
  total: number;
}

/**
 * Unified hook for searching all mention types (@users, @corpuses, @documents, @annotations, @agents)
 *
 * PERFORMANCE OPTIMIZATIONS:
 * - Parallel query execution (all 5 types searched simultaneously)
 * - Debounced search (300ms default)
 * - Result limiting (3 per category = 15 total max)
 * - Context-aware (optional corpusId for annotation and agent scoping)
 *
 * Part of Issue #623 - @ Mentions Feature (Extended)
 *
 * @param query - Search query string
 * @param corpusId - Optional corpus ID for context-aware annotation and agent search
 * @param debounceMs - Debounce delay in milliseconds (default: MENTION_SEARCH_DEBOUNCE_MS)
 * @param minChars - Minimum characters before searching (default: MENTION_SEARCH_MIN_CHARS)
 * @param limitPerCategory - Max results per category (default: 3)
 */
export function useUnifiedMentionSearch(
  query: string,
  corpusId?: string,
  debounceMs: number = MENTION_SEARCH_DEBOUNCE_MS,
  minChars: number = MENTION_SEARCH_MIN_CHARS,
  limitPerCategory: number = 3
) {
  const [debouncedQuery, setDebouncedQuery] = useState(query);

  // Lazy queries for all 4 resource types
  const [
    searchUsers,
    { data: userData, loading: usersLoading, error: usersError },
  ] = useLazyQuery<SearchUsersForMentionOutput, SearchUsersForMentionInput>(
    SEARCH_USERS_FOR_MENTION,
    {
      fetchPolicy: "network-only",
    }
  );

  const [
    searchCorpuses,
    { data: corpusData, loading: corpusesLoading, error: corpusesError },
  ] = useLazyQuery<
    SearchCorpusesForMentionOutput,
    SearchCorpusesForMentionInput
  >(SEARCH_CORPUSES_FOR_MENTION, {
    fetchPolicy: "network-only",
  });

  const [
    searchDocuments,
    { data: documentData, loading: documentsLoading, error: documentsError },
  ] = useLazyQuery<
    SearchDocumentsForMentionOutput,
    SearchDocumentsForMentionInput
  >(SEARCH_DOCUMENTS_FOR_MENTION, {
    fetchPolicy: "network-only",
  });

  const [
    searchAnnotations,
    {
      data: annotationData,
      loading: annotationsLoading,
      error: annotationsError,
    },
  ] = useLazyQuery<
    SearchAnnotationsForMentionOutput,
    SearchAnnotationsForMentionInput
  >(SEARCH_ANNOTATIONS_FOR_MENTION, {
    fetchPolicy: "network-only",
  });

  const [
    searchAgents,
    { data: agentData, loading: agentsLoading, error: agentsError },
  ] = useLazyQuery<SearchAgentsForMentionOutput, SearchAgentsForMentionInput>(
    SEARCH_AGENTS_FOR_MENTION,
    {
      fetchPolicy: "network-only",
    }
  );

  // Debounce the query
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(query);
    }, debounceMs);

    return () => clearTimeout(timer);
  }, [query, debounceMs]);

  // Execute all searches in parallel when debounced query changes
  useEffect(() => {
    if (debouncedQuery.length < minChars) {
      return;
    }

    // Fire all 5 queries simultaneously for maximum performance
    searchUsers({ variables: { textSearch: debouncedQuery } });
    searchCorpuses({ variables: { textSearch: debouncedQuery } });
    searchDocuments({
      variables: {
        textSearch: debouncedQuery,
        corpusId, // Context-aware scoping (Issue #741)
      },
    });
    searchAnnotations({
      variables: {
        textSearch: debouncedQuery,
        corpusId, // Context-aware scoping
      },
    });
    searchAgents({
      variables: {
        textSearch: debouncedQuery,
        corpusId, // Context-aware scoping for corpus agents
      },
    });
  }, [
    debouncedQuery,
    minChars,
    corpusId,
    searchUsers,
    searchCorpuses,
    searchDocuments,
    searchAnnotations,
    searchAgents,
  ]);

  // Combine and categorize results
  const categorizedResults: CategorizedResults = useMemo(() => {
    // User results
    const users: UnifiedMentionResource[] =
      userData?.searchUsersForMention?.edges
        ?.slice(0, limitPerCategory)
        .map((edge) => ({
          id: edge.node.id,
          type: "user" as const,
          title: edge.node.username,
          subtitle: edge.node.email || undefined,
          user: {
            id: edge.node.id,
            username: edge.node.username,
            email: edge.node.email || undefined,
            slug: edge.node.slug || undefined,
          },
        })) || [];

    // Corpus results
    const corpuses: UnifiedMentionResource[] =
      corpusData?.searchCorpusesForMention?.edges
        ?.slice(0, limitPerCategory)
        .map((edge) => ({
          id: edge.node.id,
          type: "corpus" as const,
          title: edge.node.title,
          subtitle: `@corpus:${edge.node.slug}`,
          metadata: `by @${edge.node.creator.slug}`,
          corpus: {
            slug: edge.node.slug,
            creator: {
              slug: edge.node.creator.slug,
            },
          },
        })) || [];

    // Document results (via DocumentPath - take first corpus if available)
    const documents: UnifiedMentionResource[] =
      documentData?.searchDocumentsForMention?.edges
        ?.slice(0, limitPerCategory)
        .map((edge) => {
          // Documents link to corpuses via DocumentPath - take first one for mention format
          const firstCorpus = edge.node.pathRecords?.edges?.[0]?.node?.corpus;

          return {
            id: edge.node.id,
            type: "document" as const,
            title: edge.node.title,
            subtitle: firstCorpus
              ? `@corpus:${firstCorpus.slug}/document:${edge.node.slug}`
              : `@document:${edge.node.slug}`,
            metadata: firstCorpus
              ? `in "${firstCorpus.title}" by @${edge.node.creator.slug}`
              : `by @${edge.node.creator.slug}`,
            document: {
              slug: edge.node.slug,
              creator: {
                slug: edge.node.creator.slug,
              },
              corpus: firstCorpus
                ? {
                    slug: firstCorpus.slug,
                    title: firstCorpus.title,
                    creator: {
                      slug: firstCorpus.creator.slug,
                    },
                  }
                : undefined,
            },
          };
        }) || [];

    // Annotation results (filter out annotations with null documents)
    const annotations: UnifiedMentionResource[] =
      annotationData?.searchAnnotationsForMention?.edges
        ?.filter((edge) => edge.node.document != null)
        ?.slice(0, limitPerCategory)
        .map((edge) => {
          // Create short preview text from rawText for primary display
          // This makes the picker more user-friendly by showing actual content
          // Fixes Issue #689 - Inline reference cards show cryptic information
          // Sanitize user-generated content to prevent XSS (per CLAUDE.md)
          const sanitizedRawText = edge.node.rawText
            ? sanitizeForMention(edge.node.rawText)
            : null;
          const shortPreviewText = sanitizedRawText
            ? sanitizedRawText.length > MENTION_PREVIEW_LENGTH
              ? sanitizedRawText.substring(0, MENTION_PREVIEW_LENGTH) + "…"
              : sanitizedRawText
            : `[${edge.node.annotationLabel.text}]`;

          return {
            id: edge.node.id,
            type: "annotation" as const,
            // Show actual text content as primary title for clarity
            title: shortPreviewText,
            // Show label and page info as secondary context
            subtitle: `${edge.node.annotationLabel.text} • Page ${edge.node.page}`,
            // Show document title as metadata
            metadata: `in "${edge.node.document.title}"`,
            annotation: {
              rawText: edge.node.rawText,
              page: edge.node.page,
              label: {
                text: edge.node.annotationLabel.text,
                color: edge.node.annotationLabel.color,
              },
              document: {
                id: edge.node.document.id,
                title: edge.node.document.title,
                slug: edge.node.document.slug,
                creator: { slug: edge.node.document.creator.slug },
              },
              corpus: edge.node.corpus
                ? {
                    id: edge.node.corpus.id,
                    title: edge.node.corpus.title,
                    slug: edge.node.corpus.slug,
                    creator: { slug: edge.node.corpus.creator.slug },
                  }
                : null,
            },
          };
        }) || [];

    // Agent results
    const agents: UnifiedMentionResource[] =
      agentData?.searchAgentsForMention?.edges
        ?.slice(0, limitPerCategory)
        .map((edge) => ({
          id: edge.node.id,
          type: "agent" as const,
          title: edge.node.name,
          subtitle: edge.node.mentionFormat || `@agent:${edge.node.slug}`,
          metadata:
            edge.node.scope === "GLOBAL"
              ? "Global Agent"
              : edge.node.corpus
              ? `Corpus: ${edge.node.corpus.title}`
              : "Corpus Agent",
          agent: {
            id: edge.node.id,
            name: edge.node.name,
            slug: edge.node.slug,
            description: edge.node.description,
            scope: edge.node.scope,
            mentionFormat: edge.node.mentionFormat,
            corpus: edge.node.corpus,
          },
        })) || [];

    const total =
      users.length +
      corpuses.length +
      documents.length +
      annotations.length +
      agents.length;

    return {
      users,
      corpuses,
      documents,
      annotations,
      agents,
      total,
    };
  }, [
    userData,
    corpusData,
    documentData,
    annotationData,
    agentData,
    limitPerCategory,
  ]);

  // When query is below minChars we haven't fired a search, so any
  // lingering loading state from a previous in-flight query is stale.
  const belowMinChars = debouncedQuery.length < minChars;
  const loading = belowMinChars
    ? false
    : usersLoading ||
      corpusesLoading ||
      documentsLoading ||
      annotationsLoading ||
      agentsLoading;

  // Flatten all results in category order for keyboard navigation
  const allResults = belowMinChars
    ? []
    : [
        ...categorizedResults.users,
        ...categorizedResults.corpuses,
        ...categorizedResults.documents,
        ...categorizedResults.annotations,
        ...categorizedResults.agents,
      ];

  // Hint shown in the picker when no results and below minChars threshold
  const hint = belowMinChars
    ? `Type ${minChars}+ characters to search`
    : undefined;

  return {
    categorizedResults,
    allResults, // Flattened for keyboard nav
    loading,
    hasResults: categorizedResults.total > 0,
    hint,
  };
}
