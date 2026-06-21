import { useQuery } from "@apollo/client";
import { useCallback, useMemo } from "react";
import {
  GET_CORPUS_ANALYSES,
  GetCorpusAnalysesInputs,
  GetCorpusAnalysesOutputs,
} from "../../../graphql/queries";
import { useNotificationWebSocket } from "../../../hooks/useNotificationWebSocket";
import type { NotificationUpdate } from "../../../hooks/useNotificationWebSocket";
import { getNumericIdFromGlobalId } from "../../../utils/idValidation";

export const ACTIVE_STATUSES = ["CREATED", "QUEUED", "RUNNING"];

export const ENRICHMENT_TASK_NAMES = [
  "opencontractserver.tasks.corpus_analysis_tasks.corpus_reference_enrichment",
  "opencontractserver.tasks.corpus_analysis_tasks.crawl_authorities",
];

const ANALYSIS_NOTIFICATION_TYPES = new Set([
  "ANALYSIS_RUNNING",
  "ANALYSIS_COMPLETE",
  "ANALYSIS_FAILED",
]);

export function useEnrichmentJobs(
  corpusId: string,
  statusExact?: string | null
) {
  const { data, loading, error, refetch } = useQuery<
    GetCorpusAnalysesOutputs,
    GetCorpusAnalysesInputs
  >(GET_CORPUS_ANALYSES, {
    variables: {
      corpusId,
      statusExact: statusExact ?? null,
      taskNames: ENRICHMENT_TASK_NAMES,
    },
    fetchPolicy: "network-only",
    skip: !corpusId,
  });

  // Decode the Relay global ID to a numeric pk once, memoized on corpusId.
  const corpusPk = useMemo(() => {
    if (!corpusId) return null;
    try {
      return getNumericIdFromGlobalId(corpusId);
    } catch {
      return null;
    }
  }, [corpusId]);

  const handleNotification = useCallback(
    (notification: NotificationUpdate) => {
      if (!ANALYSIS_NOTIFICATION_TYPES.has(notification.notificationType)) {
        return;
      }
      const notifCorpusId = notification.data?.corpus_id;
      // If corpus_id is absent, refetch as a safe fallback.
      // If present, only refetch when it matches this hook's corpus.
      if (notifCorpusId !== undefined && notifCorpusId !== corpusPk) {
        return;
      }
      refetch();
    },
    [corpusPk, refetch]
  );

  useNotificationWebSocket({
    onNotificationCreated: handleNotification,
    enabled: Boolean(corpusId),
  });

  const jobs = (data?.analyses?.edges ?? []).map((e) => e.node);
  // Total matching analyses server-side (before the `first: 50` page cap) so
  // the list can surface "showing N of M" when older runs are truncated.
  const totalCount = data?.analyses?.totalCount ?? null;
  return { jobs, totalCount, loading, error, refetch };
}
