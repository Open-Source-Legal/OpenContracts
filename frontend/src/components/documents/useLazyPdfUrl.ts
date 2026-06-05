import { useCallback } from "react";
import { useApolloClient } from "@apollo/client";

import {
  GET_DOCUMENT_PDF_URL,
  GetDocumentPdfUrlInputs,
  GetDocumentPdfUrlOutputs,
} from "../../graphql/queries";

/**
 * Resolve a document's signed PDF URL lazily (on download-click).
 *
 * Signing a GCS URL is a network round trip, so the document-list query omits
 * ``pdfFile`` and we fetch it only when a user actually downloads — instead of
 * signing one per card up front. Backward-compatible: when the caller already
 * has a ``pdfFile`` (e.g. an extract/detail query that still selects it), that
 * value is returned without a fetch.
 *
 * @returns a function ``(documentId, existing?) => Promise<string | null>``.
 */
export function useLazyPdfUrl(): (
  documentId: string,
  existing?: string | null
) => Promise<string | null> {
  const client = useApolloClient();

  return useCallback(
    async (documentId: string, existing?: string | null) => {
      if (existing) return existing;
      const { data } = await client.query<
        GetDocumentPdfUrlOutputs,
        GetDocumentPdfUrlInputs
      >({
        query: GET_DOCUMENT_PDF_URL,
        variables: { documentId },
        // Signed GCS URLs expire, so a cached value can be stale/invalid by
        // the time the user clicks download — always re-sign on demand.
        fetchPolicy: "network-only",
      });
      return data?.document?.pdfFile ?? null;
    },
    [client]
  );
}
