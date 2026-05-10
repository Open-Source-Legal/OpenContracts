import { gql } from "@apollo/client";

export const GET_DOCUMENT_SUMMARY_VERSIONS = gql`
  query GetDocumentSummaryVersions($documentId: ID!, $corpusId: ID!) {
    document(id: $documentId) {
      id
      summaryContent(corpusId: $corpusId)
      currentSummaryVersion(corpusId: $corpusId)
      summaryRevisions(corpusId: $corpusId) {
        id
        version
        created
        snapshot
        diff
        author {
          id
          slug
        }
      }
    }
  }
`;

export const UPDATE_DOCUMENT_SUMMARY = gql`
  mutation UpdateDocumentSummary(
    $documentId: ID!
    $corpusId: ID!
    $newContent: String!
  ) {
    updateDocumentSummary(
      documentId: $documentId
      corpusId: $corpusId
      newContent: $newContent
    ) {
      ok
      message
      version
      obj {
        id
        summaryContent(corpusId: $corpusId)
        currentSummaryVersion(corpusId: $corpusId)
        summaryRevisions(corpusId: $corpusId) {
          id
          version
          created
          snapshot
          diff
          author {
            id
            slug
          }
        }
      }
    }
  }
`;

// Types for the GraphQL queries
//
// ``username``/``email`` are now self-only PII on the GraphQL surface
// (see ``config/graphql/user_types.py``) and resolve to ``null`` for any
// cross-user view, so we drop them and rely on ``slug`` — the public
// identifier ``getCreatorDisplay`` already prefers.
export interface SummaryAuthor {
  id: string;
  slug?: string | null;
}

export interface DocumentSummaryRevision {
  id: string;
  version: number;
  created: string;
  snapshot: string;
  diff: string;
  author: SummaryAuthor;
}

export interface DocumentSummaryData {
  id: string;
  summaryContent: string;
  currentSummaryVersion: number;
  summaryRevisions: DocumentSummaryRevision[];
}

export interface GetDocumentSummaryVersionsResponse {
  document: DocumentSummaryData;
}

export interface GetDocumentSummaryVersionsVariables {
  documentId: string;
  corpusId: string;
}

export interface UpdateDocumentSummaryResponse {
  updateDocumentSummary: {
    ok: boolean;
    message: string;
    version: number | null;
    obj: DocumentSummaryData | null;
  };
}

export interface UpdateDocumentSummaryVariables {
  documentId: string;
  corpusId: string;
  newContent: string;
}
