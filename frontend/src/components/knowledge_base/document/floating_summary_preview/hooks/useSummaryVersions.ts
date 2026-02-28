import { useState, useCallback } from "react";
import { useQuery, useMutation } from "@apollo/client";
import { toast } from "react-toastify";
import {
  GET_DOCUMENT_SUMMARY_VERSIONS,
  UPDATE_DOCUMENT_SUMMARY,
  GetDocumentSummaryVersionsResponse,
  GetDocumentSummaryVersionsVariables,
  UpdateDocumentSummaryResponse,
  UpdateDocumentSummaryVariables,
  DocumentSummaryRevision,
} from "../graphql/documentSummaryQueries";

export interface UseSummaryVersionsResult {
  versions: DocumentSummaryRevision[];
  currentVersion: number | null;
  currentContent: string;
  loading: boolean;
  error: Error | undefined;
  updateSummary: (newContent: string) => Promise<void>;
  revertToVersion: (version: number) => Promise<void>;
  refetch: () => void;
}

export function useSummaryVersions(
  documentId: string,
  corpusId: string
): UseSummaryVersionsResult {
  const [updating, setUpdating] = useState(false);

  const { data, loading, error, refetch } = useQuery<
    GetDocumentSummaryVersionsResponse,
    GetDocumentSummaryVersionsVariables
  >(GET_DOCUMENT_SUMMARY_VERSIONS, {
    variables: { documentId, corpusId },
    skip: !documentId || !corpusId,
    fetchPolicy: "network-only",
    nextFetchPolicy: "cache-and-network",
  });

  const [updateSummaryMutation] = useMutation<
    UpdateDocumentSummaryResponse,
    UpdateDocumentSummaryVariables
  >(UPDATE_DOCUMENT_SUMMARY);

  const updateSummary = useCallback(
    async (newContent: string) => {
      if (updating) return;

      setUpdating(true);
      try {
        const result = await updateSummaryMutation({
          variables: { documentId, corpusId, newContent },
        });

        if (result.data?.updateDocumentSummary.ok) {
          toast.success("Summary updated successfully");
          await refetch();
        } else {
          throw new Error(
            result.data?.updateDocumentSummary.message ||
              "Failed to update summary"
          );
        }
      } catch (err) {
        console.error("Error updating summary:", err);
        toast.error(
          err instanceof Error ? err.message : "Failed to update summary"
        );
        throw err;
      } finally {
        setUpdating(false);
      }
    },
    [documentId, corpusId, updateSummaryMutation, updating, refetch]
  );

  const revertToVersion = useCallback(
    async (version: number) => {
      // Find the version to revert to
      const targetVersion = data?.document.summaryRevisions.find(
        (rev) => rev.version === version
      );

      if (!targetVersion) {
        toast.error("Version not found");
        return;
      }

      // NOTE(deferred): Reverting to a specific version requires either a
      // dedicated GraphQL query or storing full snapshots per revision. The
      // backend currently stores snapshots, but no "revert" mutation exists.
      toast.info("Reverting to previous versions will be implemented soon");
    },
    [data]
  );

  return {
    versions: data?.document.summaryRevisions
      ? [...data.document.summaryRevisions].sort(
          (a, b) => b.version - a.version
        )
      : [],
    currentVersion: data?.document.currentSummaryVersion || null,
    currentContent: data?.document.summaryContent || "",
    loading: loading || updating,
    error,
    updateSummary,
    revertToVersion,
    refetch,
  };
}
