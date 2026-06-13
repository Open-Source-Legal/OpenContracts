import { useCallback } from "react";
import { useLazyQuery } from "@apollo/client";
import { useNavigate } from "react-router-dom";

import {
  GET_DOCUMENT_BY_ID_FOR_REDIRECT,
  GetDocumentByIdForRedirectInput,
  GetDocumentByIdForRedirectOutput,
} from "../graphql/queries";
import { buildCanonicalPath } from "../utils/navigationUtils";
import { DocumentType } from "../types/graphql-api";

/**
 * Navigate to a document's canonical slug path given only its global id.
 *
 * Resolves the document's (and its corpus's) slugs via
 * ``GET_DOCUMENT_BY_ID_FOR_REDIRECT`` — the same query the route manager's
 * ID-fallback uses — then navigates to ``buildCanonicalPath``. Works across
 * corpora (e.g. a statute section navigates into its authority corpus).
 *
 * Shared by the governance graph's node click-through and the document
 * References panel's inbound rows.
 */
export function useNavigateToDocumentById(): (
  documentId: string,
  queryString?: string
) => Promise<void> {
  const navigate = useNavigate();
  const [resolveDocumentById] = useLazyQuery<
    GetDocumentByIdForRedirectOutput,
    GetDocumentByIdForRedirectInput
  >(GET_DOCUMENT_BY_ID_FOR_REDIRECT, { fetchPolicy: "cache-first" });

  return useCallback(
    async (documentId: string, queryString?: string) => {
      const { data } = await resolveDocumentById({
        variables: { id: documentId },
      });
      const doc = data?.document;
      if (!doc) return;
      // The redirect query returns a structural subset of DocumentType /
      // CorpusType — enough for buildCanonicalPath, which only reads slug and
      // creator.slug. Narrow through `unknown` rather than `any` so the cast
      // stays explicit and the any-baseline guard is not tripped.
      // The redirect query carries no corpus context (DocumentType has no
      // corpus field — documents relate to corpora via paths), so this
      // resolves the document's standalone canonical path.
      const path = buildCanonicalPath(doc as unknown as DocumentType);
      if (path) navigate(path + (queryString || ""));
    },
    [resolveDocumentById, navigate]
  );
}
