import { useCallback, useEffect, useState } from "react";
import type { ApolloError } from "@apollo/client";

import { EnrichmentAnalysisRow } from "../../../graphql/mutations";
import { ACTIVE_STATUSES, useEnrichmentJobs } from "./useEnrichmentJobs";

export interface UseOptimisticRowsResult {
  /** Server-fetched analysis rows. */
  jobs: EnrichmentAnalysisRow[];
  /** Optimistic rows awaiting confirmation by a refetch. */
  optimistic: EnrichmentAnalysisRow[];
  /** True when any fetched or optimistic row is in an active status. */
  running: boolean;
  /**
   * Server-reported total number of matching analyses, before the `first: 50`
   * page cap (null until the first response). Lets the list surface a
   * "showing N of M" hint when older runs are truncated.
   */
  totalCount: number | null;
  loading: boolean;
  error: ApolloError | undefined;
  /** Prepend optimistic rows from a freshly-dispatched run and refetch. */
  handleRan: (rows: EnrichmentAnalysisRow[]) => void;
}

/**
 * Owns the single enrichment-jobs query plus the optimistic-row lifecycle
 * shared by AdminEnrichment's EnrichmentPanel and CorpusEnrichmentCard.
 *
 * Centralising it here means each component tree fires exactly one
 * `useEnrichmentJobs` query — one network request and one WebSocket listener —
 * rather than one per consumer, and the prune effect / ACTIVE_STATUSES guard
 * live in a single place instead of being copy-pasted onto every surface.
 */
export function useOptimisticRows(corpusId: string): UseOptimisticRowsResult {
  const { jobs, totalCount, loading, error, refetch } =
    useEnrichmentJobs(corpusId);
  const [optimistic, setOptimistic] = useState<EnrichmentAnalysisRow[]>([]);

  // Prune optimistic rows that have now been confirmed by a real refetch.
  // `optimistic` is intentionally excluded from the deps: this effect updates
  // `optimistic`, so including it would re-trigger the effect on every prune
  // and loop. We only want to re-evaluate when the server `jobs` change.
  useEffect(() => {
    if (!optimistic.length) return;
    const ids = new Set(jobs.map((j) => j.id));
    if (optimistic.some((o) => ids.has(o.id))) {
      setOptimistic((prev) => prev.filter((o) => !ids.has(o.id)));
    }
  }, [jobs]); // eslint-disable-line react-hooks/exhaustive-deps

  const running = [...jobs, ...optimistic].some((j) =>
    ACTIVE_STATUSES.includes(j.status ?? "")
  );

  // Prepend (don't replace) so firing a second run before the first optimistic
  // rows are confirmed by a refetch doesn't discard them.
  const handleRan = useCallback(
    (rows: EnrichmentAnalysisRow[]) => {
      setOptimistic((prev) => [...rows, ...prev]);
      refetch();
    },
    [refetch]
  );

  return { jobs, optimistic, running, totalCount, loading, error, handleRan };
}
