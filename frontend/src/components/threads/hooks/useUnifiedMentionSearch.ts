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
} from "../../../graphql/queries";

export interface UnifiedMentionResource {
  id: string;
  type: "user" | "corpus" | "document" | "annotation";
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
    };
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
  total: number;
}

/**
 * Unified hook for searching all mention types (@users, @corpuses, @documents, @annotations)
 *
 * PERFORMANCE OPTIMIZATIONS:
 * - Parallel query execution (all 4 types searched simultaneously)
 * - Debounced search (300ms default)
 * - Result limiting (3 per category = 12 total max)
 * - Context-aware (optional corpusId for annotation scoping)
 *
 * Part of Issue #623 - @ Mentions Feature (Extended)
 *
 * @param query - Search query string
 * @param corpusId - Optional corpus ID for context-aware annotation search
 * @param debounceMs - Debounce delay in milliseconds (default: 300)
 * @param minChars - Minimum characters before searching (default: 2)
 * @param limitPerCategory - Max results per category (default: 3)
 */
export function useUnifiedMentionSearch(
  query: string,
  corpusId?: string,
  debounceMs: number = 300,
  minChars: number = 2,
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

    // Fire all 4 queries simultaneously for maximum performance
    searchUsers({ variables: { textSearch: debouncedQuery } });
    searchCorpuses({ variables: { textSearch: debouncedQuery } });
    searchDocuments({ variables: { textSearch: debouncedQuery } });
    searchAnnotations({
      variables: {
        textSearch: debouncedQuery,
        corpusId: corpusId, // Context-aware scoping
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

    // Document results (ManyToMany relationship - take first corpus if available)
    const documents: UnifiedMentionResource[] =
      documentData?.searchDocumentsForMention?.edges
        ?.slice(0, limitPerCategory)
        .map((edge) => {
          // Documents can be in multiple corpuses - take first one for mention format
          const firstCorpus = edge.node.corpusSet?.edges?.[0]?.node;

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

    // Annotation results
    const annotations: UnifiedMentionResource[] =
      annotationData?.searchAnnotationsForMention?.edges
        ?.slice(0, limitPerCategory)
        .map((edge) => {
          // Create preview text from rawText or label
          const previewText =
            edge.node.rawText && edge.node.rawText.length > 60
              ? edge.node.rawText.substring(0, 60) + "..."
              : edge.node.rawText || `[${edge.node.annotationLabel.text}]`;

          return {
            id: edge.node.id,
            type: "annotation" as const,
            title: edge.node.annotationLabel.text,
            subtitle: previewText,
            metadata: `${edge.node.document.title} • page ${edge.node.page}`,
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
              },
              corpus: edge.node.corpus
                ? {
                    id: edge.node.corpus.id,
                    title: edge.node.corpus.title,
                  }
                : null,
            },
          };
        }) || [];

    const total =
      users.length + corpuses.length + documents.length + annotations.length;

    return {
      users,
      corpuses,
      documents,
      annotations,
      total,
    };
  }, [userData, corpusData, documentData, annotationData, limitPerCategory]);

  const loading =
    usersLoading || corpusesLoading || documentsLoading || annotationsLoading;

  // Flatten all results in category order for keyboard navigation
  const allResults = [
    ...categorizedResults.users,
    ...categorizedResults.corpuses,
    ...categorizedResults.documents,
    ...categorizedResults.annotations,
  ];

  return {
    categorizedResults,
    allResults, // Flattened for keyboard nav
    loading,
    hasResults: categorizedResults.total > 0,
  };
}
