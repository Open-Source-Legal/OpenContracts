/**
 * Generic relay-connection list hook for the Authority Console tables.
 *
 * Encapsulates the query + cursor-based "load more" merge + refetch that every
 * console table needs, parameterised by the connection field name so one hook
 * serves the registry connection now and the absorbed frontier / mappings
 * connections in later phases. Replaces the per-panel hand-rolled ``fetchMore``
 * + ``updateQuery`` blocks that were duplicated across AuthorityMappings and
 * AuthoritySourcesMonitor.
 */
import { useMemo } from "react";
import { ApolloError, DocumentNode, useQuery } from "@apollo/client";

interface RelayConnection<TNode> {
  pageInfo: { hasNextPage: boolean; endCursor?: string | null };
  edges: { node: TNode }[];
}

interface UseFacetedRelayListArgs<TVars> {
  query: DocumentNode;
  variables: TVars;
  /** The connection field name in the query (e.g. "authorityNamespaces"). */
  connectionKey: string;
  skip?: boolean;
}

interface UseFacetedRelayListResult<TNode> {
  rows: TNode[];
  loading: boolean;
  error?: ApolloError;
  hasNextPage: boolean;
  loadMore: () => void;
  refetch: () => void;
}

export function useFacetedRelayList<
  TNode,
  TVars extends { after?: string | null }
>({
  query,
  variables,
  connectionKey,
  skip = false,
}: UseFacetedRelayListArgs<TVars>): UseFacetedRelayListResult<TNode> {
  const result = useQuery<Record<string, RelayConnection<TNode>>, TVars>(
    query,
    {
      variables,
      skip,
      fetchPolicy: "network-only",
      notifyOnNetworkStatusChange: true,
    }
  );

  const connection = result.data?.[connectionKey];
  const rows = useMemo(
    () => (connection?.edges ?? []).map((e) => e.node),
    [connection]
  );
  const pageInfo = connection?.pageInfo;

  const loadMore = () => {
    if (!pageInfo?.hasNextPage) return;
    result.fetchMore({
      variables: { ...variables, after: pageInfo.endCursor },
      updateQuery: (prev, { fetchMoreResult }) => {
        if (!fetchMoreResult) return prev;
        const prevConn = prev[connectionKey];
        const nextConn = fetchMoreResult[connectionKey];
        return {
          ...prev,
          [connectionKey]: {
            ...nextConn,
            edges: [...prevConn.edges, ...nextConn.edges],
          },
        };
      },
    });
  };

  return {
    rows,
    loading: result.loading,
    error: result.error,
    hasNextPage: pageInfo?.hasNextPage ?? false,
    loadMore,
    refetch: () => {
      result.refetch();
    },
  };
}
