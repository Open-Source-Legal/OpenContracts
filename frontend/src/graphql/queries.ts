import { gql } from "@apollo/client";
import { LabelSet } from "../components/types";
import {
  AnnotationLabelTypeEdge,
  ServerAnnotationType,
  CorpusType,
  CorpusTypeEdge,
  DocumentTypeEdge,
  LabelSetType,
  PageInfo,
  RelationshipType,
  AnalyzerType,
  AnalysisType,
  FieldsetType,
  ExtractType,
  CorpusActionType,
  DocumentType,
  AnalysisRowType,
  ConversationType,
  ConversationTypeConnection,
  ConversationTypeEnum,
  PipelineComponentType,
  ChatMessageType,
  UserType,
  RawCorpusType,
  RawDocumentType,
  JobStatus,
} from "../types/graphql-api";
import { ExportObject } from "../types/graphql-api";
import {
  ResearchReportType,
  ResearchReportListItem,
} from "../types/graphql-api";
import { WebSocketSources } from "../components/chat/types";

export interface RequestDocumentsInputs {
  textSearch?: string;
  corpusId?: string;
  inFolderId?: string; // "__root__" (or omit) = all corpus docs; a folder ID = that folder + sub-folders
  annotateDocLabels?: boolean;
  hasLabelWithId?: string;
}

export interface RequestDocumentsOutputs {
  documents: {
    edges: DocumentTypeEdge[];
    pageInfo: PageInfo;
    totalCount: number;
  };
}

// NOTE: The corpus document-card view requests ``docTypeLabels`` — a flat
// list field on DocumentType that returns the badge labels directly without
// the Relay connection / filterset wrapping the legacy ``docAnnotations``
// shape forced. The backend resolver (``DocumentType.resolve_doc_type_labels``,
// ``config/graphql/document_types.py``) consumes a focused prefetch loaded
// in one batch by ``_apply_document_prefetches``; the prefetch is opt-in via
// ``requests_doc_type_labels`` (``config/graphql/custom_resolvers.py``)
// which walks the AST for either ``docTypeLabels`` or the legacy
// ``docAnnotations(annotationLabel_LabelType: "DOC_TYPE_LABEL")``. Keep
// the field name spelled exactly ``docTypeLabels`` here (graphql-core
// preserves the underlying field name on ``FieldNode.name`` even through an
// alias, but a rename would silently disable the prefetch hook-up and
// re-introduce one ``SELECT`` per document) — and prefer adding optional
// fields over restructuring the document-edge shape.
export const GET_DOCUMENTS = gql`
  query (
    $inCorpusWithId: String
    $inFolderId: String
    $cursor: String
    $limit: Int
    $textSearch: String
    $hasLabelWithId: String
    $annotateDocLabels: Boolean!
    $hasAnnotationsWithIds: String
    $includeMetadata: Boolean!
    $includeCaml: Boolean
  ) {
    documents(
      inCorpusWithId: $inCorpusWithId
      inFolderId: $inFolderId
      textSearch: $textSearch
      hasLabelWithId: $hasLabelWithId
      hasAnnotationsWithIds: $hasAnnotationsWithIds
      includeCaml: $includeCaml
      first: $limit
      after: $cursor
    ) {
      edges {
        node {
          id
          slug
          title
          description
          backendLock
          processingStatus
          processingError
          canRetry
          fileType
          icon
          isPublic
          myPermissions
          creator {
            id
            slug
          }
          is_selected @client
          is_open @client
          hasVersionHistory
          versionCount
          isLatestVersion
          canViewHistory
          docRelationshipCount(corpusId: $inCorpusWithId)
          docTypeLabels @include(if: $annotateDocLabels) {
            labelType
            text
          }
        }
      }
      pageInfo {
        hasNextPage
        hasPreviousPage
        startCursor
        endCursor
      }
      totalCount
    }
  }
`;

/**
 * GET_CORPUS_DOCUMENT_IDS
 *
 * Returns the global IDs of EVERY document matching the corpus/folder/search
 * filters, ignoring pagination. Used by the document grid's "Select All" so a
 * bulk remove acts on every matching document — not just the page the
 * virtualized list happens to have loaded. The variables mirror the filter
 * subset of GET_DOCUMENTS so the id set always matches the visible list under
 * identical filters (the folder filter is descendant-aware).
 */
export interface CorpusDocumentIdsInputs {
  inCorpusWithId: string;
  inFolderId?: string;
  textSearch?: string;
  hasLabelWithId?: string;
  hasAnnotationsWithIds?: string;
  includeCaml?: boolean;
}

export interface CorpusDocumentIdsOutputs {
  corpusDocumentIds: string[];
}

export const GET_CORPUS_DOCUMENT_IDS = gql`
  query GetCorpusDocumentIds(
    $inCorpusWithId: String!
    $inFolderId: String
    $textSearch: String
    $hasLabelWithId: String
    $hasAnnotationsWithIds: String
    $includeCaml: Boolean
  ) {
    corpusDocumentIds(
      inCorpusWithId: $inCorpusWithId
      inFolderId: $inFolderId
      textSearch: $textSearch
      hasLabelWithId: $hasLabelWithId
      hasAnnotationsWithIds: $hasAnnotationsWithIds
      includeCaml: $includeCaml
    )
  }
`;

// Aggregate stats for the Documents view tile counters. Computed by a single
// backend ``aggregate()`` over ``Document.objects.visible_to_user`` so the
// numbers reflect the user's full permission scope rather than the paginated
// edges currently sitting in Apollo's cache.
export interface RequestDocumentStatsInputs {
  textSearch?: string;
  hasLabelWithId?: string;
  inCorpusWithId?: string;
  includeCaml?: boolean;
}

export interface RequestDocumentStatsOutputs {
  documentStats: {
    totalDocs: number;
    totalPages: number;
    processedCount: number;
    processingCount: number;
  };
}

export const GET_DOCUMENT_STATS = gql`
  query GetDocumentStats(
    $textSearch: String
    $hasLabelWithId: String
    $inCorpusWithId: String
    $includeCaml: Boolean
  ) {
    documentStats(
      textSearch: $textSearch
      hasLabelWithId: $hasLabelWithId
      inCorpusWithId: $inCorpusWithId
      includeCaml: $includeCaml
    ) {
      totalDocs
      totalPages
      processedCount
      processingCount
    }
  }
`;

// Slim list-view query for the top-level Documents view (frontend/src/views/Documents.tsx).
//
// GET_DOCUMENTS is shared by many surfaces (modals, corpus tabs, upload flow,
// metadata workflow tests) and selects a kitchen-sink of fields — including
// expensive per-row resolvers like ``versionCount`` (an N+1 ``.count()`` per
// document on the backend), ``canViewHistory`` / ``canRetry`` (per-row
// ``user_can`` checks), and signed file-URL fields (``pdfFile`` for the
// corpus card's download action, ``icon`` for the thumbnail). Each signed URL
// is a storage round trip on GCS — ``txtExtractFile`` / ``pawlsParseFile`` were
// dropped from this query because no list consumer reads them (the
// document-detail loader fetches them on open via its own query). The
// Documents view paints even less (id / title / fileType / backendLock /
// pageCount / icon / created / creator initials, with creator slugs for
// ``navigateToDocument``), so it uses the slim query below to skip the heavy
// fan-out without disturbing the other consumers of GET_DOCUMENTS.
export interface RequestDocumentsForListInputs {
  textSearch?: string;
  inCorpusWithId?: string;
  hasLabelWithId?: string;
  cursor?: string;
  limit?: number;
}

export interface RequestDocumentsForListOutputs {
  documents: {
    edges: DocumentTypeEdge[];
    pageInfo: PageInfo;
  };
}

export const GET_DOCUMENTS_FOR_LIST = gql`
  query GetDocumentsForList(
    $inCorpusWithId: String
    $textSearch: String
    $hasLabelWithId: String
    $cursor: String
    $limit: Int
  ) {
    documents(
      inCorpusWithId: $inCorpusWithId
      textSearch: $textSearch
      hasLabelWithId: $hasLabelWithId
      first: $limit
      after: $cursor
    ) {
      edges {
        node {
          id
          slug
          title
          fileType
          backendLock
          pageCount
          icon
          created
          creator {
            id
            slug
            email
          }
        }
      }
      pageInfo {
        hasNextPage
        hasPreviousPage
        startCursor
        endCursor
      }
    }
  }
`;

// Lazy fetch of a single document's signed PDF URL, resolved on download-click
// rather than for every card in the list. Signing a GCS URL is a network round
// trip, so fetching ``pdfFile`` for an N-document page (when only one might be
// downloaded) is wasteful — the list query omits it and ``useLazyPdfUrl``
// fetches it on demand. See frontend/src/components/documents/useLazyPdfUrl.ts.
export interface GetDocumentPdfUrlInputs {
  documentId: string;
}

export interface GetDocumentPdfUrlOutputs {
  document: {
    id: string;
    pdfFile: string | null;
  } | null;
}

export const GET_DOCUMENT_PDF_URL = gql`
  query GetDocumentPdfUrl($documentId: ID!) {
    document(id: $documentId) {
      id
      pdfFile
    }
  }
`;

// Lazy fetch of a single document's relationships (used by hover popups in the
// document list). Kept separate from GET_DOCUMENTS so the list view can
// resolve hundreds of documents without paying the per-doc relationship cost.
export interface GetDocRelationshipsForDocInputs {
  documentId: string;
  corpusId?: string | null;
}

export interface GetDocRelationshipsForDocOutputs {
  bulkDocRelationships: Array<{
    id: string;
    relationshipType: string;
    sourceDocument?: { id: string; title?: string };
    targetDocument?: { id: string; title?: string };
    annotationLabel?: { id: string; text?: string; color?: string };
  }>;
}

export const GET_DOC_RELATIONSHIPS_FOR_DOC = gql`
  query GetDocRelationshipsForDoc($documentId: ID!, $corpusId: ID) {
    bulkDocRelationships(documentId: $documentId, corpusId: $corpusId) {
      id
      relationshipType
      sourceDocument {
        id
        title
      }
      targetDocument {
        id
        title
      }
      annotationLabel {
        id
        text
        color
      }
    }
  }
`;

// ---------------- Slug resolution ----------------
export const DOCUMENT_IN_CORPUS_BY_SLUGS = gql`
  query (
    $userSlug: String!
    $corpusSlug: String!
    $documentSlug: String!
    $versionNumber: Int
  ) {
    documentInCorpusBySlugs(
      userSlug: $userSlug
      corpusSlug: $corpusSlug
      documentSlug: $documentSlug
      versionNumber: $versionNumber
    ) {
      id
      slug
      title
    }
  }
`;

// Enhanced queries that fetch full data in single request
export const RESOLVE_CORPUS_BY_SLUGS_FULL = gql`
  query ResolveCorpusFull($userSlug: String!, $corpusSlug: String!) {
    corpusBySlugs(userSlug: $userSlug, corpusSlug: $corpusSlug) {
      id
      slug
      title
      description
      icon
      isPublic
      isPersonal
      myPermissions
      allowComments
      preferredEmbedder
      created
      modified
      creator {
        id
        email
        username
        slug
      }
      labelSet {
        id
        title
      }
      documentCount
      annotationCount
      license
      licenseLink
    }
  }
`;

export const RESOLVE_DOCUMENT_BY_SLUGS_FULL = gql`
  query ResolveDocumentFull($userSlug: String!, $documentSlug: String!) {
    documentBySlugs(userSlug: $userSlug, documentSlug: $documentSlug) {
      id
      slug
      title
      description
      fileType
      isPublic
      pdfFile
      backendLock
      myPermissions
      creator {
        id
        username
        slug
      }
    }
  }
`;

export const RESOLVE_DOCUMENT_IN_CORPUS_BY_SLUGS_FULL = gql`
  query ResolveDocumentInCorpusFull(
    $userSlug: String!
    $corpusSlug: String!
    $documentSlug: String!
    $versionNumber: Int
  ) {
    corpusBySlugs(userSlug: $userSlug, corpusSlug: $corpusSlug) {
      id
      slug
      title
      description
      isPublic
      myPermissions
      creator {
        id
        username
        slug
      }
      labelSet {
        id
        title
      }
    }
    documentInCorpusBySlugs(
      userSlug: $userSlug
      corpusSlug: $corpusSlug
      documentSlug: $documentSlug
      versionNumber: $versionNumber
    ) {
      id
      slug
      title
      description
      fileType
      isPublic
      pdfFile
      backendLock
      myPermissions
      isLatestVersion
      creator {
        id
        username
        slug
      }
    }
  }
`;

export const GET_CORPUS_VERSIONS = gql`
  query GetCorpusVersions($documentId: ID!, $corpusId: ID!) {
    document(id: $documentId) {
      id
      corpusVersions(corpusId: $corpusId) {
        versionNumber
        documentId
        documentSlug
        created
        isCurrent
      }
    }
  }
`;

export interface ResolveExtractByIdInput {
  extractId: string;
}

export interface ResolveExtractByIdOutput {
  extract: ExtractType | null;
}

export const RESOLVE_EXTRACT_BY_ID = gql`
  query ResolveExtractById($extractId: ID!) {
    extract(id: $extractId) {
      id
      name
      created
      started
      finished
      error
      myPermissions
      creator {
        id
        username
        slug
      }
      corpus {
        id
        slug
        title
        creator {
          id
          slug
        }
      }
      fieldset {
        id
        name
        description
      }
    }
  }
`;

export const SEARCH_DOCUMENTS = gql`
  query (
    $inCorpusWithId: String
    $cursor: String
    $limit: Int
    $textSearch: String
    $hasLabelWithId: String
    $hasAnnotationsWithIds: String
  ) {
    documents(
      inCorpusWithId: $inCorpusWithId
      textSearch: $textSearch
      hasLabelWithId: $hasLabelWithId
      hasAnnotationsWithIds: $hasAnnotationsWithIds
      first: $limit
      after: $cursor
    ) {
      edges {
        node {
          id
          slug
          title
          description
          backendLock
          pdfFile
          txtExtractFile
          fileType
          pawlsParseFile
          icon
          isPublic
          myPermissions
          creator {
            id
            slug
          }
          is_selected @client
        }
      }
      pageInfo {
        hasNextPage
        hasPreviousPage
        startCursor
        endCursor
      }
    }
  }
`;

export interface GetCorpusMetadataInputs {
  metadataForCorpusId: string;
}

export interface GetCorpusMetadataOutputs {
  corpus: CorpusType;
}

export const GET_CORPUS_METADATA = gql`
  query ($metadataForCorpusId: ID!) {
    corpus(id: $metadataForCorpusId) {
      id
      slug
      title
      description
      myPermissions
      creator {
        id
        username
        slug
      }
    }
  }
`;

export const GET_CORPUS_WITH_HISTORY = gql`
  query GetCorpusWithHistory($id: ID!) {
    corpus(id: $id) {
      id
      slug
      title
      description
      descriptionPreview
      icon
      created
      modified
      isPublic
      isPersonal
      myPermissions
      documentCount
      license
      licenseLink
      creator {
        id
        slug
        __typename
      }
      labelSet {
        id
        title
        __typename
      }
      descriptionRevisions {
        id
        version
        author {
          id
          slug
          __typename
        }
        created
        snapshot
        __typename
      }
      __typename
    }
  }
`;

export interface GetCorpusWithHistoryQueryVariables {
  id: string;
}

export interface CorpusRevision {
  id: string;
  version: number;
  author: {
    id: string;
    email: string;
    __typename: string;
  };
  created: string;
  snapshot?: string;
  __typename: string;
}

export interface GetCorpusWithHistoryQuery {
  corpus: {
    id: string;
    slug?: string | null;
    title: string;
    description: string;
    descriptionPreview?: string | null;
    icon?: string | null;
    created: string;
    modified: string;
    isPublic: boolean;
    isPersonal?: boolean;
    myPermissions: string[];
    creator: {
      id: string;
      email: string;
      slug?: string | null;
      __typename: string;
    };
    labelSet?: {
      id: string;
      title: string;
      __typename: string;
    } | null;
    descriptionRevisions: CorpusRevision[];
    __typename: string;
  };
}

export interface GetCorpusStatsInputType {
  corpusId: string;
}

export interface CorpusStats {
  totalDocs: number;
  totalComments: number;
  totalAnalyses: number;
  totalExtracts: number;
  totalAnnotations: number;
  totalThreads?: number; // Optional for backward compatibility with backend
  totalChats?: number;
  totalRelationships?: number;
}

export interface GetCorpusStatsOutputType {
  corpusStats: CorpusStats;
}

export const GET_CORPUS_STATS = gql`
  query corpusStats($corpusId: ID!) {
    corpusStats(corpusId: $corpusId) {
      totalDocs
      totalComments
      totalAnalyses
      totalExtracts
      totalAnnotations
      totalThreads
      totalChats
      totalRelationships
    }
  }
`;

export interface GetCorpusLabelsetAndLabelsInputs {
  labelId?: string;
  corpusId?: string;
  text_Contains?: string;
  label_description_search_string?: string;
  label_title_search_string?: string;
  label_Type?: string;
}

export interface GetCorpusLabelsetAndLabelsOutputs {
  corpus: CorpusType;
}

export const GET_CORPUS_LABELSET_AND_LABELS = gql`
  query ($corpusId: ID!) {
    corpus(id: $corpusId) {
      id
      icon
      title
      description
      backendLock
      isPublic
      myPermissions
      labelSet {
        id
        icon
        title
        description
        isPublic
        myPermissions
        allAnnotationLabels {
          id
          icon
          labelType
          text
          description
          color
          isPublic
          myPermissions
          analyzer {
            id
          }
        }
      }
    }
  }
`;

export interface GetCorpusesInputs {
  textSearch?: string;
  usesLabelsetId?: string;
  cursor?: string;
  limit?: number;
  // Tab filters for the Corpuses view. Server applies these on top of the
  // user-visible queryset so pagination + badge counts stay correct.
  mine?: boolean;
  isPublic?: boolean;
  sharedWithMe?: boolean;
  // Sort order. Tuple-mapped on the backend; supported values:
  //   "top" / "-top"           — by vote score (ascending / descending)
  //   "created" / "-created"   — by creation timestamp
  //   "modified" / "-modified" — by last modified timestamp
  //   "title" / "-title"       — by title alphabetical
  // Default (unset) keeps the model's ``ordering = ("created",)`` default.
  orderBy?: string;
}

export interface GetCorpusesOutputs {
  corpuses: {
    edges: CorpusTypeEdge[];
    pageInfo: PageInfo;
  };
}

export const GET_CORPUSES = gql`
  query (
    $textSearch: String
    $usesLabelsetId: String
    $cursor: String
    $limit: Int
    $mine: Boolean
    $isPublic: Boolean
    $sharedWithMe: Boolean
    $orderBy: String
  ) {
    corpuses(
      textSearch: $textSearch
      usesLabelsetId: $usesLabelsetId
      mine: $mine
      isPublic: $isPublic
      sharedWithMe: $sharedWithMe
      orderBy: $orderBy
      first: $limit
      after: $cursor
    ) {
      pageInfo {
        hasNextPage
        hasPreviousPage
        startCursor
        endCursor
      }
      edges {
        node {
          id
          slug
          icon
          title
          creator {
            id
            email
            slug
          }
          description
          descriptionPreview
          isPublic
          isPersonal
          is_selected @client
          is_open @client
          myPermissions
          documentCount
          parent {
            id
            icon
            title
            description
          }
          labelSet {
            id
            title
            description
            docLabelCount
            spanLabelCount
            tokenLabelCount
          }
          categories {
            id
            name
          }
          license
          licenseLink
          upvoteCount
          downvoteCount
          score
          myVote
        }
      }
    }
  }
`;

export interface CorpusFilterCounts {
  all: number;
  mine: number;
  shared: number;
  public: number;
}

export interface GetCorpusFilterCountsInputs {
  textSearch?: string;
}

export interface GetCorpusFilterCountsOutputs {
  corpusFilterCounts: CorpusFilterCounts;
}

export const GET_CORPUS_FILTER_COUNTS = gql`
  query CorpusFilterCounts($textSearch: String) {
    corpusFilterCounts(textSearch: $textSearch) {
      all
      mine
      shared
      public
    }
  }
`;

export interface GetLabelsetInputs {
  description?: string;
  title?: string;
}

export interface GetLabelsetOutputs {
  labelsets: {
    pageInfo: PageInfo;
    edges: {
      node: LabelSetType;
    }[];
  };
}

export const GET_LABELSETS = gql`
  query (
    $description: String
    $title: String
    $labelsetId: String
    $cursor: String
    $limit: Int
  ) {
    labelsets(
      description_Contains: $description
      title_Contains: $title
      labelsetId: $labelsetId
      first: $limit
      after: $cursor
    ) {
      pageInfo {
        hasNextPage
        hasPreviousPage
        startCursor
        endCursor
      }
      edges {
        node {
          id
          icon
          title
          description
          created
          is_selected @client
          is_open @client
          isPublic
          myPermissions
        }
      }
    }
  }
`;

export interface GetLabelsetsWithLabelsInputs {
  textSearch?: string;
  title?: string;
}

export interface GetLabelsetsWithLabelsOutputs {
  labelsets: {
    pageInfo: PageInfo;
    totalCount?: number;
    edges: {
      node: LabelSetType;
    }[];
  };
}

export const REQUEST_LABELSETS_WITH_ALL_LABELS = gql`
  query ($textSearch: String, $title: String, $cursor: String, $limit: Int) {
    labelsets(
      textSearch: $textSearch
      title_Contains: $title
      first: $limit
      after: $cursor
    ) {
      pageInfo {
        hasNextPage
        hasPreviousPage
        startCursor
        endCursor
      }
      totalCount
      edges {
        node {
          id
          icon
          title
          description
          created
          isPublic
          myPermissions
          docLabelCount
          spanLabelCount
          tokenLabelCount
          corpusCount
          creator {
            id
            slug
            username
            email
          }
          allAnnotationLabels {
            id
            icon
            labelType
            text
            description
            color
          }
        }
      }
    }
  }
`;

export interface GetAnnotationsInputs {
  annotationLabelId?: string;
  corpusId?: string;
  usesLabelFromLabelsetId?: string;
  rawText_Contains?: string;
  analysis_Isnull?: boolean;
  corpusAction_Isnull?: boolean;
  agentCreated?: boolean;
  annotationLabel_description_search_string?: string;
  annotationLabel_title_search_string?: string;
  annotationLabel_Type?: string;
  createdWithAnalyzerId?: string;
  createdByAnalysisIds?: string;
  structural?: boolean;
  limit?: number;
  cursor?: string;
}

export interface GetAnnotationsOutputs {
  annotations: {
    pageInfo: PageInfo;
    totalCount?: number;
    edges: {
      node: ServerAnnotationType;
    }[];
  };
}

export const GET_ANNOTATIONS = gql`
  query (
    $annotationLabelId: ID
    $corpusId: ID
    $usesLabelFromLabelsetId: ID
    $rawText_Contains: String
    $annotationLabel_description_search_string: String
    $annotationLabel_title_search_string: String
    $annotationLabel_Type: String
    $createdWithAnalyzerId: String
    $createdByAnalysisIds: String
    $analysis_Isnull: Boolean
    $corpusAction_Isnull: Boolean
    $agentCreated: Boolean
    $structural: Boolean
    $cursor: String
    $limit: Int
  ) {
    annotations(
      corpusId: $corpusId
      annotationLabelId: $annotationLabelId
      usesLabelFromLabelsetId: $usesLabelFromLabelsetId
      rawTextContains: $rawText_Contains
      annotationLabel_TextContains: $annotationLabel_title_search_string
      annotationLabel_DescriptionContains: $annotationLabel_description_search_string
      annotationLabel_LabelType: $annotationLabel_Type
      createdWithAnalyzerId: $createdWithAnalyzerId
      createdByAnalysisIds: $createdByAnalysisIds
      analysisIsnull: $analysis_Isnull
      corpusActionIsnull: $corpusAction_Isnull
      agentCreated: $agentCreated
      structural: $structural
      first: $limit
      after: $cursor
    ) {
      totalCount
      edges {
        node {
          id
          json
          page
          created
          creator {
            id
            email
            username
            slug
            __typename
          }
          corpus {
            id
            slug
            icon
            title
            description
            preferredEmbedder
            creator {
              id
              slug
              __typename
            }
            __typename
          }
          document {
            id
            slug
            title
            description
            backendLock
            pdfFile
            txtExtractFile
            pawlsParseFile
            icon
            fileType
            creator {
              id
              slug
              __typename
            }
            __typename
          }
          analysis {
            id
            analyzer {
              analyzerId
              __typename
            }
            __typename
          }
          corpusAction {
            id
            __typename
          }
          annotationLabel {
            id
            text
            color
            icon
            description
            labelType
            __typename
          }
          annotationType
          structural
          rawText
          linkUrl
          isPublic
          myPermissions
          contentModalities
          __typename
        }
        __typename
      }
      pageInfo {
        hasNextPage
        hasPreviousPage
        startCursor
        endCursor
        __typename
      }
      __typename
    }
  }
`;

// ═══════════════════════════════════════════════════════════════════════════════
// LIGHTWEIGHT ANNOTATIONS QUERY FOR CARD DISPLAY
// ═══════════════════════════════════════════════════════════════════════════════
// This query fetches only the fields needed for ModernAnnotationCard display.
// It excludes heavy fields like json and unnecessary nested objects.
// Use this for annotation list/grid views where performance is critical.

export const GET_ANNOTATIONS_FOR_CARDS = gql`
  query GetAnnotationsForCards(
    $annotationLabelId: ID
    $corpusId: ID
    $usesLabelFromLabelsetId: ID
    $rawText_Contains: String
    $annotationLabel_description_search_string: String
    $annotationLabel_title_search_string: String
    $annotationLabel_Type: String
    $createdWithAnalyzerId: String
    $createdByAnalysisIds: String
    $analysis_Isnull: Boolean
    $corpusAction_Isnull: Boolean
    $agentCreated: Boolean
    $structural: Boolean
    $cursor: String
    $limit: Int
  ) {
    annotations(
      corpusId: $corpusId
      annotationLabelId: $annotationLabelId
      usesLabelFromLabelsetId: $usesLabelFromLabelsetId
      rawTextContains: $rawText_Contains
      annotationLabel_TextContains: $annotationLabel_title_search_string
      annotationLabel_DescriptionContains: $annotationLabel_description_search_string
      annotationLabel_LabelType: $annotationLabel_Type
      createdWithAnalyzerId: $createdWithAnalyzerId
      createdByAnalysisIds: $createdByAnalysisIds
      analysisIsnull: $analysis_Isnull
      corpusActionIsnull: $corpusAction_Isnull
      agentCreated: $agentCreated
      structural: $structural
      first: $limit
      after: $cursor
    ) {
      totalCount
      edges {
        node {
          id
          created
          creator {
            id
            slug
            __typename
          }
          corpus {
            id
            slug
            creator {
              id
              slug
            }
            labelSet {
              id
              title
              __typename
            }
            __typename
          }
          document {
            id
            slug
            creator {
              id
              slug
            }
            title
            __typename
          }
          analysis {
            id
            analyzer {
              analyzerId
              __typename
            }
            __typename
          }
          corpusAction {
            id
            __typename
          }
          annotationLabel {
            id
            text
            color
            __typename
          }
          annotationType
          structural
          rawText
          isPublic
          contentModalities
          __typename
        }
        __typename
      }
      pageInfo {
        hasNextPage
        hasPreviousPage
        startCursor
        endCursor
        __typename
      }
      __typename
    }
  }
`;

// ═══════════════════════════════════════════════════════════════════════════════
// SEMANTIC SEARCH QUERY
// ═══════════════════════════════════════════════════════════════════════════════

export interface SemanticSearchInput {
  query: string;
  corpusId?: string;
  documentId?: string;
  modalities?: string[];
  labelText?: string;
  rawTextContains?: string;
  limit?: number;
  offset?: number;
}

export interface BlockContextPayload {
  /**
   * Raw Django PK (not a Relay global ID) of the OC_SUBTREE_GROUP
   * relationship — used directly by the doc viewer's `rel=` deep-link
   * parameter so the resolver can short-circuit `from_global_id`.
   */
  relationshipId: string;
  sourceAnnotationId: string;
  sourceText: string;
  targetAnnotationIds: string[];
  blockText: string;
}

export interface SemanticSearchResult {
  annotation: ServerAnnotationType;
  similarityScore: number;
  document: DocumentType | null;
  corpus: RawCorpusType | null;
  blockContext: BlockContextPayload | null;
}

export interface SemanticSearchOutput {
  semanticSearch: SemanticSearchResult[];
}

// ═══════════════════════════════════════════════════════════════════════════════
// SEMANTIC SEARCH — RELATIONSHIP TARGET
// ═══════════════════════════════════════════════════════════════════════════════
//
// Companion to ``semanticSearch`` that returns hits against the polymorphic
// ``Embedding.relationship`` slot. Currently surfaces the materialised
// OC_SUBTREE_GROUP rows; the resolver is structured so a future relationship
// kind only needs a backend update.

export interface SemanticSearchRelationshipsInput {
  query: string;
  corpusId?: string;
  documentId?: string;
  limit?: number;
  offset?: number;
}

export interface SemanticSearchRelationshipResult {
  /** Raw Django PK (not Relay global ID); see BlockContextPayload note. */
  relationshipId: string;
  similarityScore: number;
  label: string | null;
  sourceAnnotationId: string | null;
  targetAnnotationIds: string[];
  blockText: string;
  documentId: string | null;
  corpusId: string | null;
}

export interface SemanticSearchRelationshipsOutput {
  semanticSearchRelationships: SemanticSearchRelationshipResult[];
}

export const SEMANTIC_SEARCH_RELATIONSHIPS = gql`
  query SemanticSearchRelationships(
    $query: String!
    $corpusId: ID
    $documentId: ID
    $limit: Int
    $offset: Int
  ) {
    semanticSearchRelationships(
      query: $query
      corpusId: $corpusId
      documentId: $documentId
      limit: $limit
      offset: $offset
    ) {
      relationshipId
      similarityScore
      label
      sourceAnnotationId
      targetAnnotationIds
      blockText
      documentId
      corpusId
    }
  }
`;

export const SEMANTIC_SEARCH_ANNOTATIONS = gql`
  query SemanticSearchAnnotations(
    $query: String!
    $corpusId: ID
    $documentId: ID
    $modalities: [String]
    $labelText: String
    $rawTextContains: String
    $limit: Int
    $offset: Int
  ) {
    semanticSearch(
      query: $query
      corpusId: $corpusId
      documentId: $documentId
      modalities: $modalities
      labelText: $labelText
      rawTextContains: $rawTextContains
      limit: $limit
      offset: $offset
    ) {
      annotation {
        id
        json
        page
        created
        creator {
          id
          email
          username
          slug
          __typename
        }
        corpus {
          id
          slug
          icon
          title
          description
          preferredEmbedder
          creator {
            id
            slug
            __typename
          }
          labelSet {
            id
            title
            __typename
          }
          __typename
        }
        document {
          id
          slug
          title
          description
          backendLock
          pdfFile
          txtExtractFile
          pawlsParseFile
          icon
          fileType
          creator {
            id
            slug
            __typename
          }
          __typename
        }
        analysis {
          id
          analyzer {
            analyzerId
            __typename
          }
          __typename
        }
        annotationLabel {
          id
          text
          color
          icon
          description
          labelType
          __typename
        }
        annotationType
        structural
        rawText
        linkUrl
        isPublic
        myPermissions
        contentModalities
        __typename
      }
      similarityScore
      document {
        id
        slug
        title
        __typename
      }
      corpus {
        id
        slug
        title
        __typename
      }
      blockContext {
        relationshipId
        sourceAnnotationId
        sourceText
        targetAnnotationIds
        blockText
      }
    }
  }
`;

export interface GetAnnotationLabelsInput {
  corpusId?: string;
  labelsetId?: string;
  labelType?: string;
}

export interface GetAnnotationLabelsOutput {
  annotationLabels: {
    pageInfo: PageInfo;
    edges: AnnotationLabelTypeEdge[];
  };
}

export const GET_ANNOTATION_LABELS = gql`
  query getAnnotationLabels(
    $corpusId: String
    $labelsetId: String
    $labelType: AnnotationsAnnotationLabelLabelTypeChoices
    $cursor: String
    $limit: Int
  ) {
    annotationLabels(
      usedInLabelsetForCorpusId: $corpusId
      usedInLabelsetId: $labelsetId
      labelType: $labelType
      first: $limit
      after: $cursor
    ) {
      pageInfo {
        hasNextPage
        hasPreviousPage
        endCursor
        startCursor
      }
      edges {
        node {
          id
          icon
          text
          description
          labelType
          readOnly
          isPublic
          myPermissions
          analyzer {
            id
          }
        }
      }
    }
  }
`;

export interface GetLabelsetWithLabelsInputs {
  id: string;
}

export interface GetLabelsetWithLabelsOutputs {
  labelset: LabelSetType;
}

export const GET_LABELSET_WITH_ALL_LABELS = gql`
  query ($id: ID!) {
    labelset(id: $id) {
      id
      icon
      title
      description
      created
      modified
      isPublic
      myPermissions
      docLabelCount
      spanLabelCount
      tokenLabelCount
      corpusCount
      creator {
        id
        slug
        username
        email
      }
      allAnnotationLabels {
        id
        icon
        labelType
        readOnly
        text
        description
        color
        myPermissions
        isPublic
        analyzer {
          id
        }
      }
    }
  }
`;

export interface GetAnalyzersInputs {
  description_contains?: string;
  analyzer_id_contains?: string;
  usedInAnalysisIds?: string; // should be comma separated list of graphql id values
}

export interface GetAnalyzersOutputs {
  analyzers: {
    pageInfo: PageInfo;
    edges: {
      node: AnalyzerType;
    }[];
  };
}

export const GET_ANALYZERS = gql`
  query ($description_contains: String, $analyzer_id_contains: ID) {
    analyzers(
      description_Contains: $description_contains
      id_Contains: $analyzer_id_contains
    ) {
      pageInfo {
        hasNextPage
        hasPreviousPage
        endCursor
        startCursor
      }
      edges {
        node {
          id
          analyzerId
          description
          hostGremlin {
            id
          }
          disabled
          isPublic
          manifest
          inputSchema
        }
      }
    }
  }
`;

export interface GetAnalysesInputs {
  corpusId?: string;
  docId?: string;
  searchText?: string;
  analyzedCorpus_Isnull?: boolean;
}

export interface GetAnalysesOutputs {
  analyses: {
    pageInfo: PageInfo;
    edges: {
      node: AnalysisType;
    }[];
  };
}

export const GET_ANALYSES = gql`
  query (
    $corpusId: String
    $docId: String
    $searchText: String
    $analyzedCorpus_Isnull: Boolean
  ) {
    analyses(
      analyzedCorpusId: $corpusId
      analyzedDocumentId: $docId
      searchText: $searchText
      analyzedCorpus_Isnull: $analyzedCorpus_Isnull
    ) {
      pageInfo {
        hasNextPage
        hasPreviousPage
        startCursor
        endCursor
      }
      edges {
        node {
          id
          creator {
            id
            slug
            email
          }
          isPublic
          myPermissions
          analysisStarted
          analysisCompleted
          analyzedDocuments {
            edges {
              node {
                id
              }
            }
          }
          receivedCallbackFile
          annotations {
            totalCount
          }
          corpusAction {
            id
            name
            trigger
          }
          analyzer {
            id
            analyzerId
            description
            manifest
            inputSchema
            fullLabelList {
              id
              text
            }
            hostGremlin {
              id
            }
          }
        }
      }
    }
  }
`;

export interface GetExportsInputs {
  name_Contains?: string;
  orderByCreated?: string;
  orderByStarted?: string;
  orderByFinished?: string;
}

export interface GetExportsOutputs {
  userexports: {
    pageInfo: PageInfo;
    edges: {
      node: ExportObject;
    }[];
  };
}

export const GET_EXPORTS = gql`
  query (
    $name_Contains: String
    $orderByCreated: String
    $orderByStarted: String
    $orderByFinished: String
    $cursor: String
    $limit: Int
  ) {
    userexports(
      first: $limit
      after: $cursor
      name_Contains: $name_Contains
      orderByCreated: $orderByCreated
      orderByStarted: $orderByStarted
      orderByFinished: $orderByFinished
    ) {
      pageInfo {
        hasNextPage
        hasPreviousPage
        endCursor
        startCursor
      }
      edges {
        node {
          id
          name
          finished
          started
          created
          errors
          backendLock
          file
        }
      }
    }
  }
`;

export interface GetFieldsetsInputs {
  searchText?: string;
}

export interface GetFieldsetsOutputs {
  fieldsets: {
    pageInfo: PageInfo;
    edges: {
      node: FieldsetType;
    }[];
  };
}

export const GET_FIELDSETS = gql`
  query GetFieldsets($searchText: String) {
    fieldsets(name_Contains: $searchText) {
      pageInfo {
        hasNextPage
        hasPreviousPage
        startCursor
        endCursor
      }
      edges {
        node {
          id
          creator {
            id
            slug
            username
          }
          name
          description
          inUse
          columns {
            edges {
              node {
                id
                name
                query
                matchText
                outputType
                limitToLabel
                instructions
                extractIsList
                taskName
              }
            }
          }
        }
      }
    }
  }
`;

export interface GetFieldsetInput {
  id: string;
}

export interface GetFieldsetOutput {
  fieldset: FieldsetType;
}

export const REQUEST_GET_FIELDSET = gql`
  query GetFieldset($id: ID!) {
    fieldset(id: $id) {
      id
      name
      description
      inUse
      creator {
        id
        slug
        username
      }
      fullColumnList {
        id
        name
        query
        matchText
        mustContainText
        outputType
        limitToLabel
        instructions
        extractIsList
        taskName
      }
    }
  }
`;

export interface RequestGetExtractInput {
  id: string;
}

export interface RequestGetExtractOutput {
  extract: ExtractType;
}

export const REQUEST_GET_EXTRACT = gql`
  query GetExtract($id: ID!) {
    extract(id: $id) {
      id
      corpus {
        id
        title
      }
      name
      fieldset {
        id
        name
        inUse
        fullColumnList {
          id
          name
          query
          instructions
          matchText
          limitToLabel
          taskName
          outputType
          extractIsList
        }
      }
      creator {
        id
        slug
        username
      }
      created
      started
      finished
      error
      modelConfig
      iterationAxis
      parentExtract {
        id
        name
      }
      fullIterationList {
        id
        name
        started
        finished
        error
        modelConfig
        iterationAxis
        creator {
          id
          slug
          username
        }
      }
      fullDocumentList {
        id
        title
        description
        pageCount
        fileType
      }
      fullDatacellList {
        id
        column {
          id
          name
        }
        document {
          id
          title
          fileType
        }
        fullSourceList {
          id
          isPublic
          myPermissions
          annotationLabel {
            id
            text
            color
            icon
            labelType
            description
          }
          document {
            id
            fileType
            pdfFile
            txtExtractFile
            pawlsParseFile
          }

          page
          rawText

          json
          annotationType
          sourceNodeInRelationships {
            edges {
              node {
                id
              }
            }
          }
          targetNodeInRelationships {
            edges {
              node {
                id
              }
            }
          }
          creator {
            id
            slug
            email
          }
          isPublic
          myPermissions
        }
        data
        dataDefinition
        started
        completed
        failed
        correctedData
        stacktrace
        rejectedBy {
          email
        }
        approvedBy {
          email
        }
      }
    }
  }
`;

export interface GetExtractsInput {
  searchText?: string;
  corpusId?: string;
  corpusAction_Isnull?: boolean;
}

export interface GetExtractsOutput {
  extracts: {
    pageInfo: PageInfo;
    edges: {
      node: ExtractType;
    }[];
  };
}

export const GET_EXTRACTS = gql`
  query GetExtracts(
    $searchText: String
    $corpusId: ID
    $corpusAction_Isnull: Boolean
  ) {
    extracts(
      name_Contains: $searchText
      corpus: $corpusId
      corpusAction_Isnull: $corpusAction_Isnull
    ) {
      edges {
        node {
          id
          corpus {
            id
            title
          }
          name
          fieldset {
            id
            name
            inUse
            fullColumnList {
              id
            }
          }
          fullDocumentList {
            id
          }
          creator {
            id
            username
            slug
          }
          created
          started
          finished
          error
          myPermissions
        }
      }
      pageInfo {
        hasNextPage
        hasPreviousPage
        startCursor
        endCursor
      }
    }
  }
`;

// Slim list-view query for the top-level Extracts view (frontend/src/views/Extracts.tsx).
//
// GET_EXTRACTS is shared by ExtractItem, CorpusExtractCards, CamlArticleEditor
// and CreateExtractModal — all of which select fullDocumentList / fullColumnList
// because they actually walk the lists. The Extracts view only renders counts,
// so paying for ``fullDocumentList { id }`` (which triggers an N+1 per-doc
// permission filter on the backend's resolve_full_document_list) and
// ``fieldset.fullColumnList { id }`` is wasted work. The slim query swaps both
// for the new ``documentCount`` / ``fieldset.columnCount`` fields and also
// drops creator.username / creator.slug and fieldset.name / fieldset.inUse
// (none of which the list card or stats tiles read). It additionally wires
// ``first`` / ``after`` into the connection so infinite scroll actually
// paginates — the legacy GET_EXTRACTS sent the cursor as a variable but never
// passed it to the connection arguments.
export interface GetExtractsForListInput {
  searchText?: string;
  corpusId?: string;
  corpusAction_Isnull?: boolean;
  cursor?: string;
  limit?: number;
}

/**
 * Slim per-extract node returned by ``GET_EXTRACTS_FOR_LIST``. Exported
 * separately from ``GetExtractsForListOutput`` so call sites that need to
 * type the materialised list (Extracts view, ExtractListCard) can do so
 * without ``as unknown as ExtractType`` casts that erase compile-time
 * field guarantees.
 */
export interface ExtractListItem {
  id: string;
  name: string;
  created: string;
  started?: string | null;
  finished?: string | null;
  error?: string | null;
  myPermissions?: string[];
  documentCount?: number | null;
  corpus?: {
    id: string;
    title?: string;
  } | null;
  fieldset?: {
    id: string;
    columnCount?: number | null;
  } | null;
}

export interface GetExtractsForListOutput {
  extracts: {
    pageInfo: PageInfo;
    edges: {
      node: ExtractListItem;
    }[];
  };
}

export const GET_EXTRACTS_FOR_LIST = gql`
  query GetExtractsForList(
    $searchText: String
    $corpusId: ID
    $corpusAction_Isnull: Boolean
    $cursor: String
    $limit: Int
  ) {
    extracts(
      name_Contains: $searchText
      corpus: $corpusId
      corpusAction_Isnull: $corpusAction_Isnull
      first: $limit
      after: $cursor
    ) {
      edges {
        node {
          id
          name
          created
          started
          finished
          error
          myPermissions
          documentCount
          corpus {
            id
            title
          }
          fieldset {
            id
            columnCount
          }
        }
      }
      pageInfo {
        hasNextPage
        hasPreviousPage
        startCursor
        endCursor
      }
    }
  }
`;

export interface GetRegisteredExtractTasksOutput {
  registeredExtractTasks: Record<string, string>;
}

export const GET_REGISTERED_EXTRACT_TASKS = gql`
  query {
    registeredExtractTasks
  }
`;

export interface GetDocumentAnalysesAndExtractsInput {
  documentId: string;
  corpusId?: string;
}

export interface GetDocumentAnalysesAndExtractsOutput {
  documentCorpusActions?: {
    corpusActions: Array<
      CorpusActionType & {
        extracts: {
          pageInfo: PageInfo;
          edges: Array<{
            node: ExtractType;
          }>;
        };
        analyses: {
          pageInfo: PageInfo;
          edges: Array<{
            node: AnalysisType;
          }>;
        };
      }
    >;
    extracts: Array<ExtractType>;
    analysisRows: Array<AnalysisRowType>;
  };
}

export const GET_DOCUMENT_ANALYSES_AND_EXTRACTS = gql`
  query DocumentData($documentId: ID!, $corpusId: ID) {
    documentCorpusActions(documentId: $documentId, corpusId: $corpusId) {
      corpusActions {
        id
        name
        trigger
        extracts {
          pageInfo {
            hasNextPage
            hasPreviousPage
            startCursor
            endCursor
          }
          edges {
            node {
              id
              name
              created
              started
              finished
            }
          }
        }
        analyses {
          pageInfo {
            hasNextPage
            hasPreviousPage
            startCursor
            endCursor
          }
          edges {
            node {
              id
              analyzer {
                id
                description
              }
              analysisStarted
              analysisCompleted
              status
            }
          }
        }
      }
      extracts {
        id
        name
        corpusAction {
          id
          name
          trigger
        }
        created
        started
        finished
      }
      analysisRows {
        id
        analysis {
          id
          analyzer {
            id
            description
          }
          annotations {
            totalCount
          }
          corpusAction {
            id
            name
            trigger
          }
          analysisStarted
          analysisCompleted
          status
        }
        data {
          edges {
            node {
              id
              data
            }
          }
        }
      }
    }
  }
`;

// Input type for the query
export interface GetDatacellsForExtractInput {
  extractId: string;
}

// Output types for the query
export interface GetDatacellsForExtractOutput {
  extract: ExtractType;
}

export const GET_DATACELLS_FOR_EXTRACT = gql`
  query GetDatacellsForExtract($extractId: ID!) {
    extract(id: $extractId) {
      id
      name
      fieldset {
        id
        name
        inUse
        fullColumnList {
          id
          name
          query
          outputType
          limitToLabel
          instructions
          extractIsList
          taskName
        }
      }
      fullDatacellList {
        id
        column {
          id
          name
        }
        document {
          id
          title
        }
        data
        dataDefinition
        started
        completed
        failed
        correctedData
        stacktrace
        approvedBy {
          email
        }
        rejectedBy {
          email
        }
        fullSourceList {
          id
          annotationLabel {
            id
            text
            color
            icon
            labelType
            description
          }

          page
          rawText

          json
        }
      }
    }
  }
`;

// ---------------------------------------------------------------------------
// Extract grid embed — lightweight query for CAML article embedding
// ---------------------------------------------------------------------------

export interface GetExtractGridEmbedInput {
  extractId: string;
  /**
   * Server-side cap on the number of datacells fetched. The server also
   * reports `datacellCount` (total visible cells) so the client can display
   * a "showing N of M" indicator when the payload is bounded. Resolves #1204.
   */
  limit?: number;
}

export interface ExtractGridEmbedColumn {
  id: string;
  name: string;
}

export interface ExtractGridEmbedSource {
  id: string;
  page: number;
}

export interface ExtractGridEmbedCell {
  id: string;
  column: ExtractGridEmbedColumn;
  document: {
    id: string;
    title: string;
    slug: string;
    creator: { slug: string };
  };
  data: string | number | boolean | Record<string, unknown> | null;
  correctedData: string | number | boolean | Record<string, unknown> | null;
  completed: string | null;
  failed: string | null;
  fullSourceList: ExtractGridEmbedSource[];
}

export interface GetExtractGridEmbedOutput {
  extract: {
    id: string;
    name: string;
    corpus: {
      id: string;
      slug: string;
      creator: { slug: string };
    };
    fieldset: {
      id: string;
      fullColumnList: ExtractGridEmbedColumn[];
    };
    fullDatacellList: ExtractGridEmbedCell[];
    /** Total cells visible to the user, ignoring the `limit` applied above. */
    datacellCount?: number | null;
  } | null;
}

export const GET_EXTRACT_GRID_EMBED = gql`
  query GetExtractGridEmbed($extractId: ID!, $limit: Int) {
    extract(id: $extractId) {
      id
      name
      corpus {
        id
        slug
        creator {
          id
          slug
        }
      }
      fieldset {
        id
        fullColumnList {
          id
          name
        }
      }
      # Bounded payload: the server applies the limit arg to cap datacells
      # returned, and datacellCount reports the total visible cells so the
      # client can show a "showing N of M" indicator. Resolves #1204.
      # Note: the server also accepts an offset argument for client-driven
      # pagination, but the embed currently fetches only the first page.
      datacellCount
      fullDatacellList(limit: $limit) {
        id
        column {
          id
          name
        }
        document {
          id
          title
          slug
          creator {
            id
            slug
          }
        }
        data
        correctedData
        completed
        failed
        fullSourceList {
          id
          page
        }
      }
    }
  }
`;

// ----- Extract iteration comparison ---------------------------------------

export type ExtractDiffStatus =
  | "UNCHANGED"
  | "CHANGED"
  | "ONLY_IN_A"
  | "ONLY_IN_B";

export interface ExtractCellDiff {
  rowKey: string;
  columnKey: string;
  document: { id: string; title: string } | null;
  documentA: { id: string; title: string } | null;
  documentB: { id: string; title: string } | null;
  cellA: {
    id: string;
    data: any;
    correctedData: any;
    completed: string | null;
    failed: string | null;
  } | null;
  cellB: {
    id: string;
    data: any;
    correctedData: any;
    completed: string | null;
    failed: string | null;
  } | null;
  status: ExtractDiffStatus;
  columnConfigChanged: boolean;
}

export interface ExtractDiffSummary {
  unchanged: number;
  changed: number;
  onlyInA: number;
  onlyInB: number;
  total: number;
}

export interface CompareExtractsInput {
  extractAId: string;
  extractBId: string;
}

export interface CompareExtractsOutput {
  compareExtracts: {
    extractA: { id: string; name: string; modelConfig: any };
    extractB: { id: string; name: string; modelConfig: any };
    cells: ExtractCellDiff[];
    summary: ExtractDiffSummary;
  } | null;
}

export const COMPARE_EXTRACTS = gql`
  query CompareExtracts($extractAId: ID!, $extractBId: ID!) {
    compareExtracts(extractAId: $extractAId, extractBId: $extractBId) {
      extractA {
        id
        name
        modelConfig
      }
      extractB {
        id
        name
        modelConfig
      }
      cells {
        rowKey
        columnKey
        document {
          id
          title
        }
        documentA {
          id
          title
        }
        documentB {
          id
          title
        }
        cellA {
          id
          data
          correctedData
          completed
          failed
        }
        cellB {
          id
          data
          correctedData
          completed
          failed
        }
        status
        columnConfigChanged
      }
      summary {
        unchanged
        changed
        onlyInA
        onlyInB
        total
      }
    }
  }
`;

export interface GetAnnotationsForAnalysisInput {
  analysisId: string;
  documentId?: string;
}

export interface GetAnnotationsForAnalysisOutput {
  analysis: AnalysisType;
}

export const GET_ANNOTATIONS_FOR_ANALYSIS = gql`
  query GetAnnotationsForAnalysis($analysisId: ID!, $documentId: ID) {
    analysis(id: $analysisId) {
      id
      analyzer {
        id
        analyzerId
        description
        fullLabelList {
          id
          text
          color
          icon
          description
          labelType
        }
      }
      fullAnnotationList(documentId: $documentId) {
        id
        annotationLabel {
          id
          text
          color
          icon
          description
          labelType
        }
        annotationType

        page
        rawText
        linkUrl

        json
        userFeedback {
          edges {
            node {
              id
              approved
              rejected
            }
          }
          totalCount
        }
        allSourceNodeInRelationship {
          id
          annotationLabel {
            id
            text
            color
            icon
            description
          }
          targetAnnotations {
            edges {
              node {
                id
              }
            }
          }
        }
        allTargetNodeInRelationship {
          id
          annotationLabel {
            id
            text
            color
            icon
            description
          }
          sourceAnnotations {
            edges {
              node {
                id
              }
            }
          }
        }
      }
    }
  }
`;

export interface GetConversationsInputs {
  documentId?: string;
  corpusId?: string;
  conversationType?: string;
  limit?: number;
  cursor?: string;
  title_Contains?: string;
  createdAt_Gte?: string;
  createdAt_Lte?: string;
  hasCorpus?: boolean;
  hasDocument?: boolean;
}

/**
 * Returns a connection of conversations.
 */
export interface GetConversationsOutputs {
  conversations: ConversationTypeConnection;
}

/**
 * Updated to query the new "conversations" field instead of "conversation".
 * The shape is now a connection with edges of ConversationType.
 */
export const GET_CONVERSATIONS = gql`
  query GetConversations(
    $documentId: String
    $corpusId: String
    $limit: Int
    $cursor: String
    $title_Contains: String
    $createdAt_Gte: DateTime
    $createdAt_Lte: DateTime
    $conversationType: ConversationTypeEnum
    $hasCorpus: Boolean
    $hasDocument: Boolean
  ) {
    conversations(
      documentId: $documentId
      corpusId: $corpusId
      first: $limit
      after: $cursor
      title_Contains: $title_Contains
      createdAt_Gte: $createdAt_Gte
      createdAt_Lte: $createdAt_Lte
      conversationType: $conversationType
      hasCorpus: $hasCorpus
      hasDocument: $hasDocument
    ) {
      edges {
        node {
          id
          conversationType
          title
          description
          createdAt
          updatedAt
          creator {
            id
            slug
            username
            email
          }
          chatWithCorpus {
            id
            title
            slug
            creator {
              id
              slug
              username
            }
          }
          chatWithDocument {
            id
            title
          }
          chatMessages {
            totalCount
          }
          isPublic
          myPermissions

          # Voting fields
          upvoteCount
          downvoteCount
          userVote

          # Moderation fields
          isLocked
          lockedBy {
            id
            username
          }
          lockedAt
          isPinned
          pinnedBy {
            id
            username
          }
          pinnedAt
          deletedAt
        }
      }
      pageInfo {
        hasNextPage
        hasPreviousPage
        startCursor
        endCursor
      }
      totalCount
    }
  }
`;

/**
 * Get detailed thread with all messages including threading and voting info
 */
export interface GetThreadDetailInput {
  conversationId: string;
}

export interface GetThreadDetailOutput {
  conversation: ConversationType & {
    allMessages: ChatMessageType[];
  };
}

export const GET_THREAD_DETAIL = gql`
  query GetThreadDetail($conversationId: ID!) {
    conversation(id: $conversationId) {
      id
      conversationType
      title
      description
      createdAt
      updatedAt
      creator {
        id
        slug
        username
        email
      }
      chatWithCorpus {
        id
        title
        slug
        creator {
          id
          slug
          username
        }
      }
      chatWithDocument {
        id
        title
      }
      isPublic
      myPermissions

      # Voting fields
      upvoteCount
      downvoteCount
      userVote

      # Moderation fields
      isLocked
      lockedBy {
        id
        username
      }
      lockedAt
      isPinned
      pinnedBy {
        id
        username
      }
      pinnedAt
      deletedAt

      # All messages with full details
      allMessages {
        id
        msgType
        agentType
        agentConfiguration {
          id
          name
          description
          badgeConfig
          avatarUrl
        }
        content
        state
        data
        createdAt
        created
        modified
        creator {
          id
          slug
          username
          email
        }

        # Threading
        parentMessage {
          id
        }

        # Voting
        upvoteCount
        downvoteCount
        # userVote — backend field not yet exposed in the schema

        # Soft delete
        deletedAt

        # Permissions (for edit/delete UI - Issue #686)
        myPermissions

        # Mentioned resources (Issue #623, #689)
        mentionedResources {
          type
          id
          slug
          title
          url
          corpus {
            slug
            title
          }
          # Annotation-specific fields (Issue #689)
          rawText
          annotationLabel
          document {
            id
            slug
            title
          }
        }
      }
    }
  }
`;

/**
 * Search users for @ mention autocomplete
 * Backend filters results to active users only
 * Part of Issue #623 - @ Mentions Feature (Extended)
 */
export interface SearchUsersForMentionInput {
  textSearch: string;
}

export interface SearchUsersForMentionOutput {
  searchUsersForMention: {
    edges: Array<{
      node: {
        id: string;
        slug: string | null;
      };
    }>;
  };
}

// ``username``/``email`` are now redacted for cross-user views (see
// ``config/graphql/user_types.py``), so the only stable identifier we can
// surface in a public mention dropdown is ``slug``. Selecting them here
// would have returned ``null`` for every other user and rendered as
// "null" in the menu.
export const SEARCH_USERS_FOR_MENTION = gql`
  query SearchUsersForMention($textSearch: String!) {
    searchUsersForMention(textSearch: $textSearch, first: 10) {
      edges {
        node {
          id
          slug
        }
      }
    }
  }
`;

/**
 * Search corpuses for @ mention autocomplete
 * Backend filters results to only corpuses visible to the user via .visible_to_user()
 * Part of Issue #623 - @ Mentions Feature
 */
export interface SearchCorpusesForMentionInput {
  textSearch: string;
}

export interface SearchCorpusesForMentionOutput {
  searchCorpusesForMention: {
    edges: Array<{
      node: {
        id: string;
        slug: string;
        title: string;
        creator: {
          slug: string;
        };
      };
    }>;
  };
}

export const SEARCH_CORPUSES_FOR_MENTION = gql`
  query SearchCorpusesForMention($textSearch: String!) {
    searchCorpusesForMention(textSearch: $textSearch, first: 10) {
      edges {
        node {
          id
          slug
          title
          creator {
            id
            slug
          }
        }
      }
    }
  }
`;

/**
 * Search documents for @ mention autocomplete
 * Backend filters results to only documents visible to the user via .visible_to_user()
 * Part of Issue #623 - @ Mentions Feature
 * Issue #741 - Added corpusId for corpus-scoped document search
 */
export interface SearchDocumentsForMentionInput {
  textSearch: string;
  corpusId?: string; // Optional corpus ID to scope search to specific corpus
}

export interface SearchDocumentsForMentionOutput {
  searchDocumentsForMention: {
    edges: Array<{
      node: {
        id: string;
        slug: string;
        title: string;
        creator: {
          slug: string;
        };
        pathRecords: {
          edges: Array<{
            node: {
              corpus: {
                id: string;
                slug: string;
                title: string;
                creator: {
                  slug: string;
                };
              };
            };
          }>;
        };
      };
    }>;
  };
}

export const SEARCH_DOCUMENTS_FOR_MENTION = gql`
  query SearchDocumentsForMention($textSearch: String!, $corpusId: ID) {
    searchDocumentsForMention(
      textSearch: $textSearch
      corpusId: $corpusId
      first: 10
    ) {
      edges {
        node {
          id
          slug
          title
          creator {
            id
            slug
          }
          pathRecords(first: 1) {
            edges {
              node {
                corpus {
                  id
                  slug
                  title
                  creator {
                    id
                    slug
                  }
                }
              }
            }
          }
        }
      }
    }
  }
`;

/**
 * Search annotations for @ mention autocomplete
 * Backend filters results to only annotations visible to the user via .visible_to_user()
 * Part of Issue #623 - @ Mentions Feature (Extended)
 */
export interface SearchAnnotationsForMentionInput {
  textSearch: string;
  corpusId?: string;
  first?: number;
}

export interface SearchAnnotationsForMentionOutput {
  searchAnnotationsForMention: {
    edges: Array<{
      node: {
        id: string;
        rawText: string | null;
        page: number;
        annotationLabel: {
          id: string;
          text: string;
          color: string;
        };
        document: {
          id: string;
          title: string;
          slug: string;
          creator: {
            id: string;
            slug: string;
          };
        };
        corpus: {
          id: string;
          title: string;
          slug: string;
          creator: {
            id: string;
            slug: string;
          };
        } | null;
      };
    }>;
  };
}

/**
 * Search notes for cross-content discovery.
 * Backend filters results to notes the user can read (Note.objects.visible_to_user).
 */
export interface SearchNotesForMentionInput {
  textSearch: string;
  corpusId?: string;
  documentId?: string;
  first?: number;
}

export interface SearchNotesForMentionOutput {
  searchNotesForMention: {
    edges: Array<{
      node: {
        id: string;
        title: string;
        contentPreview: string | null;
        modified: string;
        creator: {
          id: string;
          username: string;
          slug: string;
        };
        document: {
          id: string;
          title: string;
          slug: string;
          creator: {
            id: string;
            slug: string;
          };
        };
        corpus: {
          id: string;
          title: string;
          slug: string;
          creator: {
            id: string;
            slug: string;
          };
        } | null;
      };
    }>;
  };
}

export const SEARCH_NOTES_FOR_MENTION = gql`
  query SearchNotesForMention(
    $textSearch: String!
    $corpusId: ID
    $documentId: ID
    $first: Int
  ) {
    searchNotesForMention(
      textSearch: $textSearch
      corpusId: $corpusId
      documentId: $documentId
      first: $first
    ) {
      edges {
        node {
          id
          title
          contentPreview
          modified
          creator {
            id
            username
            slug
          }
          document {
            id
            title
            slug
            creator {
              id
              slug
            }
          }
          corpus {
            id
            title
            slug
            creator {
              id
              slug
            }
          }
        }
      }
    }
  }
`;

export const SEARCH_ANNOTATIONS_FOR_MENTION = gql`
  query SearchAnnotationsForMention(
    $textSearch: String!
    $corpusId: ID
    $first: Int = 10
  ) {
    searchAnnotationsForMention(
      textSearch: $textSearch
      corpusId: $corpusId
      first: $first
    ) {
      edges {
        node {
          id
          rawText
          page
          annotationLabel {
            id
            text
            color
          }
          document {
            id
            title
            slug
            creator {
              id
              slug
            }
          }
          corpus {
            id
            title
            slug
            creator {
              id
              slug
            }
          }
        }
      }
    }
  }
`;

// ---------------------------------------------------------------------------
// Discover cross-content search
//
// These power the Discover view (frontend/src/views/DiscoverSearchResults.tsx).
// Unlike the *ForMention queries above, each Discover query is hybrid on the
// server: it fuses substring + full-text + semantic (vector) matching and
// returns a single relevance-ranked list (NOT a Relay connection), so the
// client just renders the array in order.
// ---------------------------------------------------------------------------

export interface DiscoverSearchInput {
  textSearch: string;
  limit?: number;
}

interface DiscoverCreatorRef {
  id: string;
  slug: string;
}

export interface DiscoverAnnotationNode {
  id: string;
  rawText: string | null;
  page: number | null;
  annotationLabel: {
    id: string;
    text: string;
    color: string;
  } | null;
  document: {
    id: string;
    title: string;
    slug: string;
    creator: DiscoverCreatorRef;
  } | null;
  corpus: {
    id: string;
    title: string;
    slug: string;
    creator: DiscoverCreatorRef;
  } | null;
}

export interface DiscoverAnnotationsOutput {
  discoverAnnotations: DiscoverAnnotationNode[];
}

export const DISCOVER_ANNOTATIONS = gql`
  query DiscoverAnnotations($textSearch: String!, $limit: Int) {
    discoverAnnotations(textSearch: $textSearch, limit: $limit) {
      id
      rawText
      page
      annotationLabel {
        id
        text
        color
      }
      document {
        id
        title
        slug
        creator {
          id
          slug
        }
      }
      corpus {
        id
        title
        slug
        creator {
          id
          slug
        }
      }
    }
  }
`;

export interface DiscoverDocumentNode {
  id: string;
  title: string;
  slug: string;
  description: string | null;
  fileType: string | null;
  creator: DiscoverCreatorRef;
}

export interface DiscoverDocumentsOutput {
  discoverDocuments: DiscoverDocumentNode[];
}

export const DISCOVER_DOCUMENTS = gql`
  query DiscoverDocuments($textSearch: String!, $limit: Int) {
    discoverDocuments(textSearch: $textSearch, limit: $limit) {
      id
      title
      slug
      description
      fileType
      creator {
        id
        slug
      }
    }
  }
`;

export interface DiscoverNoteNode {
  id: string;
  title: string;
  contentPreview: string | null;
  modified: string;
  creator: {
    id: string;
    username: string;
    slug: string;
  } | null;
  document: {
    id: string;
    title: string;
    slug: string;
    creator: DiscoverCreatorRef;
  } | null;
  corpus: {
    id: string;
    title: string;
    slug: string;
    creator: DiscoverCreatorRef;
  } | null;
}

export interface DiscoverNotesOutput {
  discoverNotes: DiscoverNoteNode[];
}

export const DISCOVER_NOTES = gql`
  query DiscoverNotes($textSearch: String!, $limit: Int) {
    discoverNotes(textSearch: $textSearch, limit: $limit) {
      id
      title
      contentPreview
      modified
      creator {
        id
        username
        slug
      }
      document {
        id
        title
        slug
        creator {
          id
          slug
        }
      }
      corpus {
        id
        title
        slug
        creator {
          id
          slug
        }
      }
    }
  }
`;

export interface DiscoverCorpusNode {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  isPublic: boolean;
  documentCount: number | null;
  creator: DiscoverCreatorRef;
}

export interface DiscoverCorpusesOutput {
  discoverCorpuses: DiscoverCorpusNode[];
}

export const DISCOVER_CORPUSES = gql`
  query DiscoverCorpuses($textSearch: String!, $limit: Int) {
    discoverCorpuses(textSearch: $textSearch, limit: $limit) {
      id
      slug
      title
      description
      isPublic
      documentCount
      creator {
        id
        slug
      }
    }
  }
`;

export interface DiscoverDiscussionsOutput {
  discoverDiscussions: ConversationType[];
}

export const DISCOVER_DISCUSSIONS = gql`
  query DiscoverDiscussions($textSearch: String!, $limit: Int) {
    discoverDiscussions(textSearch: $textSearch, limit: $limit) {
      id
      conversationType
      title
      description
      createdAt
      updatedAt
      creator {
        id
        slug
        username
        email
      }
      chatWithCorpus {
        id
        title
        slug
        creator {
          id
          slug
          username
        }
      }
      chatWithDocument {
        id
        title
      }
      chatMessages {
        totalCount
      }
      isPublic
      myPermissions
      upvoteCount
      downvoteCount
      userVote
      isLocked
      lockedBy {
        id
        username
      }
      lockedAt
      isPinned
      pinnedBy {
        id
        username
      }
      pinnedAt
      deletedAt
    }
  }
`;

/**
 * Fetches all the data needed for the DocumentKnowledgeBase component:
 * - Basic document info (title, fileType, creator, created)
 * - All non-structural annotations for this document in the specified corpus
 * - All direct document-document relationships (e.g., references, related)
 * - All notes associated with this document
 */

/** Input type for the getPostprocessors query. */
export interface GetPostprocessorsInput {}
/** Output type for the getPostprocessors query. */
export interface GetPostprocessorsOutput {
  pipelineComponents: {
    /** List of available post-processors. */
    postProcessors: Array<PipelineComponentType>;
  };
}
export const GET_POST_PROCESSORS = gql`
  query {
    pipelineComponents {
      postProcessors {
        name
        moduleName
        title
        description
        author
        componentType
        inputSchema
      }
    }
  }
`;

/** Input type for the getPostprocessors query. */
export interface GetEmbeddersInput {}
/** Output type for the getPostprocessors query. */
export interface GetEmbeddersOutput {
  pipelineComponents: {
    /** List of available post-processors. */
    embedders: Array<PipelineComponentType>;
  };
}
export const GET_EMBEDDERS = gql`
  query {
    pipelineComponents {
      embedders {
        name
        moduleName
        title
        description
        author
        componentType
        inputSchema
        vectorSize
        className
        enabled
      }
    }
  }
`;

/**
 * Defaults consumed by the new-corpus modal so the form opens with sensible
 * pre-selections (default embedder from PipelineSettings, the install-wide
 * default labelset). License defaults are kept frontend-side for now.
 */
export interface GetCorpusCreateDefaultsOutput {
  pipelineSettings: {
    defaultEmbedder?: string | null;
  };
  defaultLabelset?: {
    id: string;
    title: string;
    description?: string | null;
    icon?: string | null;
    isPublic: boolean;
    isDefault?: boolean | null;
  } | null;
}
export const GET_CORPUS_CREATE_DEFAULTS = gql`
  query GetCorpusCreateDefaults {
    pipelineSettings {
      defaultEmbedder
    }
    defaultLabelset {
      id
      title
      description
      icon
      isPublic
      isDefault
    }
  }
`;

export interface GetDocumentKnowledgeAndAnnotationsInput {
  documentId: string;
  corpusId: string;
  analysisId?: string;
}

export interface GetDocumentKnowledgeAndAnnotationsOutput {
  document: RawDocumentType;
  corpus: RawCorpusType;
}

export const GET_DOCUMENT_KNOWLEDGE_AND_ANNOTATIONS = gql`
  query GetDocumentKnowledgeAndAnnotations(
    $documentId: ID!
    $corpusId: ID!
    $analysisId: ID
  ) {
    document(id: $documentId) {
      # Knowledge base fields
      id
      title
      fileType
      creator {
        id
        slug
        email
      }
      created
      mdSummaryFile
      pdfFile
      pdfFileHash
      txtExtractFile
      pawlsParseFile
      myPermissions
      allNotes(corpusId: $corpusId) {
        id
        title
        content
        created
        creator {
          id
          slug
          email
        }
      }
      allDocRelationships {
        id
        relationshipType
        sourceDocument {
          id
          title
          fileType
        }
        targetDocument {
          id
          title
          fileType
        }
        created
      }

      # Annotation fields — structural annotations and structural relationships
      # are excluded here and loaded on demand via
      # GET_DOCUMENT_STRUCTURAL_ANNOTATIONS when the user toggles the
      # corresponding visibility flag. Documents can have thousands of
      # structural annotations, so eagerly serialising them on every open
      # was the dominant cost of this query.
      allAnnotations(
        corpusId: $corpusId
        analysisId: $analysisId
        isStructural: false
      ) {
        id
        page
        analysis {
          id
        }
        annotationLabel {
          id
          text
          color
          icon
          description
          labelType
        }
        userFeedback {
          edges {
            node {
              id
              approved
              rejected
            }
          }
          totalCount
        }
        annotationType
        rawText
        json
        linkUrl
        myPermissions
        structural
        contentModalities
      }
      allRelationships(
        corpusId: $corpusId
        analysisId: $analysisId
        isStructural: false
      ) {
        id
        structural
        relationshipLabel {
          id
          text
          color
          icon
          description
        }
        sourceAnnotations {
          edges {
            node {
              id
            }
          }
        }
        targetAnnotations {
          edges {
            node {
              id
            }
          }
        }
      }
    }
    corpus(id: $corpusId) {
      id
      title
      description
      myPermissions
      labelSet {
        id
        allAnnotationLabels {
          id
          text
          color
          icon
          description
          labelType
        }
      }
    }
  }
`;

/**
 * Lightweight query to get only annotations and relationships
 * Used when switching between analyses to avoid refetching entire document
 */
export interface GetDocumentAnnotationsOnlyInput {
  documentId: string;
  corpusId: string;
  analysisId?: string | null;
}

export interface GetDocumentAnnotationsOnlyOutput {
  document: {
    id: string;
    allAnnotations: ServerAnnotationType[];
    allRelationships: RelationshipType[];
  };
}

export const GET_DOCUMENT_ANNOTATIONS_ONLY = gql`
  query GetDocumentAnnotationsOnly(
    $documentId: ID!
    $corpusId: ID!
    $analysisId: ID
  ) {
    document(id: $documentId) {
      id
      allAnnotations(
        corpusId: $corpusId
        analysisId: $analysisId
        isStructural: false
      ) {
        id
        page
        analysis {
          id
        }
        annotationLabel {
          id
          text
          color
          icon
          description
          labelType
        }
        userFeedback {
          edges {
            node {
              id
              approved
              rejected
            }
          }
          totalCount
        }
        annotationType
        rawText
        json
        linkUrl
        myPermissions
        structural
        contentModalities
      }
      allRelationships(
        corpusId: $corpusId
        analysisId: $analysisId
        isStructural: false
      ) {
        id
        structural
        relationshipLabel {
          id
          text
          color
          icon
          description
        }
        sourceAnnotations {
          edges {
            node {
              id
            }
          }
        }
        targetAnnotations {
          edges {
            node {
              id
            }
          }
        }
      }
    }
  }
`;

/**
 * Standalone query to fetch structural annotations for a document.
 * Loaded lazily when the user toggles structural annotation visibility,
 * rather than included in the initial document load (for performance).
 * Structural annotations are analysis-independent and only need to be
 * fetched once per document.
 *
 * Also returns the document's structural relationships in the same
 * round-trip — they connect structural annotations and are toggled by
 * the same UI control, so loading them together avoids a second fetch
 * when the user enables structural visibility.
 *
 * Supports optional `annotationIds` filter to fetch only specific
 * structural annotations (used for deep-link navigation). Structural
 * relationships are returned in full regardless of `annotationIds`
 * because they're tiny compared to the annotation set and the deep-link
 * path only needs them when navigating into structural data.
 */
export interface GetDocumentStructuralAnnotationsInput {
  documentId: string;
  annotationIds?: string[];
}

export interface GetDocumentStructuralAnnotationsOutput {
  document: {
    id: string;
    allStructuralAnnotations: ServerAnnotationType[];
    allStructuralRelationships: RelationshipType[];
  };
}

export const GET_DOCUMENT_STRUCTURAL_ANNOTATIONS = gql`
  query GetDocumentStructuralAnnotations(
    $documentId: ID!
    $annotationIds: [ID!]
  ) {
    document(id: $documentId) {
      id
      allStructuralAnnotations(annotationIds: $annotationIds) {
        id
        page
        parent {
          id
        }
        annotationLabel {
          id
          text
          color
          icon
          description
          labelType
        }
        annotationType
        rawText
        json
        linkUrl
        myPermissions
        structural
        contentModalities
      }
      allStructuralRelationships {
        id
        structural
        relationshipLabel {
          id
          text
          color
          icon
          description
        }
        sourceAnnotations {
          edges {
            node {
              id
            }
          }
        }
        targetAnnotations {
          edges {
            node {
              id
            }
          }
        }
      }
    }
  }
`;

/**
 * Query to get document data with structural annotations but without corpus context
 * Used when viewing documents that haven't been assigned to a corpus
 * Includes structural annotations which are inherent to the document (headers, sections, etc.)
 */
export interface GetDocumentWithStructureInput {
  documentId: string;
}

export interface GetDocumentWithStructureOutput {
  document: RawDocumentType & {
    allRelationships?: RelationshipType[];
    allNotesWithoutCorpus?: Array<{
      id: string;
      title: string;
      content: string;
      creator: {
        email: string;
      };
      created: string;
    }>;
    pathRecords?: {
      edges: Array<{
        node: {
          corpus: {
            id: string;
            title: string;
          };
        };
      }>;
    };
  };
}

export const GET_DOCUMENT_WITH_STRUCTURE = gql`
  query GetDocumentWithStructure($documentId: ID!) {
    document(id: $documentId) {
      id
      title
      fileType
      creator {
        id
        slug
        email
      }
      created
      pdfFile
      pdfFileHash
      txtExtractFile
      pawlsParseFile
      myPermissions
      # Structural annotations loaded lazily via GET_DOCUMENT_STRUCTURAL_ANNOTATIONS
      # for performance (can be thousands for large documents)
      # Structural relationships (few in number, safe to load eagerly)
      allRelationships {
        id
        structural
        relationshipLabel {
          id
          text
          color
          icon
          description
        }
        sourceAnnotations {
          edges {
            node {
              id
            }
          }
        }
        targetAnnotations {
          edges {
            node {
              id
            }
          }
        }
      }
      # Document-level notes (no corpus required)
      allNotes {
        id
        title
        content
        creator {
          id
          slug
          email
        }
        created
      }
      # Check if document is in any corpus (for UI hints)
      pathRecords {
        edges {
          node {
            corpus {
              id
              title
            }
          }
        }
      }
    }
  }
`;

// Backward compatibility aliases
export const GET_DOCUMENT_ONLY = GET_DOCUMENT_WITH_STRUCTURE;
export type GetDocumentOnlyInput = GetDocumentWithStructureInput;
export type GetDocumentOnlyOutput = GetDocumentWithStructureOutput;

/**
 * Mutation to add a document to a corpus
 */
export interface AddDocumentToCorpusInput {
  documentId: string;
  corpusId: string;
}

export interface AddDocumentToCorpusOutput {
  addDocumentToCorpus: {
    success: boolean;
    message: string;
    corpus: {
      id: string;
      title: string;
    };
  };
}

export const ADD_DOCUMENT_TO_CORPUS = gql`
  mutation AddDocumentToCorpus($documentId: ID!, $corpusId: ID!) {
    addDocumentToCorpus(documentId: $documentId, corpusId: $corpusId) {
      success
      message
      corpus {
        id
        title
      }
    }
  }
`;

/**
 * Query to get user's corpuses for the Add to Corpus modal
 */
export interface GetMyCorpusesOutput {
  myCorpuses: {
    edges: Array<{
      node: {
        id: string;
        title: string;
        documentCount: number;
        myPermissions: string[];
      };
    }>;
  };
}

export const GET_MY_CORPUSES = gql`
  query GetMyCorpuses {
    corpuses(isPublic: false, myPermissions: ["UPDATE"]) {
      edges {
        node {
          id
          title
          documentCount
          myPermissions
        }
      }
    }
  }
`;

/**
 * Interfaces and query for GET_CHAT_MESSAGES
 * to fetch messages once a conversation is selected.
 */
export interface GetChatMessagesInputs {
  conversationId: string;
  orderBy?: string; // e.g. "created_at"
  limit?: number;
  cursor?: string;
}

export interface ChatMessageNode {
  id: string;
  msgType: string;
  content: string;
  state?: string;
  createdAt?: string;
}

export interface ChatMessageEdge {
  node: ChatMessageNode;
}

export interface ChatMessageConnection {
  edges: ChatMessageEdge[];
  pageInfo?: PageInfo;
}

export interface GetChatMessagesOutputs {
  chatMessages: ChatMessageType[];
}

/**
 * New query to fetch messages for a specific conversation, optionally ordering
 * or using pagination (limit/cursor).
 */
export const GET_CHAT_MESSAGES = gql`
  query GetChatMessages($conversationId: ID!, $orderBy: String) {
    chatMessages(conversationId: $conversationId, orderBy: $orderBy) {
      id
      msgType
      agentType
      agentConfiguration {
        id
        slug
        name
        description
        scope
        badgeConfig
        avatarUrl
        corpus {
          id
          slug
          title
        }
      }
      content
      state
      data
      createdAt
      creator {
        id
        slug
        username
        email
      }

      # Mentioned resources (Issue #623, #689) — rich-mention agent delegation
      mentionedResources {
        type
        id
        slug
        title
        url
        corpus {
          type
          id
          slug
          title
          url
        }
        # Annotation-specific fields (Issue #689)
        rawText
        annotationLabel
        document {
          type
          id
          slug
          title
          url
        }
      }
    }
  }
`;

export const GET_CORPUS_ACTIONS = gql`
  query GetCorpusActions($corpusId: ID!) {
    corpusActions(corpusId: $corpusId) {
      edges {
        node {
          id
          name
          trigger
          disabled
          runOnAllCorpuses
          creator {
            id
            slug
            username
          }
          fieldset {
            id
            name
          }
          analyzer {
            id
            analyzerId
          }
          agentConfig {
            id
            name
            description
          }
          taskInstructions
          preAuthorizedTools
          sourceTemplate {
            id
            name
          }
          created
          modified
        }
      }
    }
  }
`;

export interface GetCorpusActionsInput {
  corpusId: string;
}

export interface GetCorpusActionsOutput {
  corpusActions: {
    edges: Array<{
      node: {
        id: string;
        name: string;
        trigger: string;
        disabled: boolean;
        runOnAllCorpuses: boolean;
        creator: {
          id: string;
          username: string;
        };
        fieldset?: {
          id: string;
          name: string;
        };
        analyzer?: {
          id: string;
          name: string;
        };
        agentConfig?: {
          id: string;
          name: string;
          description: string;
        };
        taskInstructions?: string;
        preAuthorizedTools?: string[];
        sourceTemplate?: { id: string; name: string } | null;
        created: string;
        modified: string;
      };
    }>;
  };
}

export const GET_CORPUS_CONVERSATIONS = gql`
  query GetCorpusConversations(
    $corpusId: String!
    $title_Contains: String
    $createdAt_Gte: DateTime
    $createdAt_Lte: DateTime
    $cursor: String
    $limit: Int
    $conversationType: ConversationTypeEnum
  ) {
    conversations(
      corpusId: $corpusId
      title_Contains: $title_Contains
      createdAt_Gte: $createdAt_Gte
      createdAt_Lte: $createdAt_Lte
      first: $limit
      after: $cursor
      conversationType: $conversationType
    ) {
      pageInfo {
        hasNextPage
        endCursor
      }
      edges {
        node {
          id
          title
          createdAt
          updatedAt
          chatMessages {
            totalCount
          }
          creator {
            id
            slug
            email
          }
        }
      }
    }
  }
`;

export const GET_CORPUS_CHAT_MESSAGES = gql`
  query GetCorpusChatMessages(
    $conversationId: ID!
    $cursor: String
    $limit: Int
  ) {
    chatMessages(
      conversation_Id: $conversationId
      first: $limit
      after: $cursor
    ) {
      edges {
        node {
          id
          content
          msgType
          createdAt
          data
          creator {
            id
            slug
            email
          }
        }
      }
    }
  }
`;

export interface GetCorpusConversationsInputs {
  corpusId: string;
  title_Contains?: string;
  createdAt_Gte?: string;
  createdAt_Lte?: string;
  cursor?: string;
  limit?: number;
  conversationType?: ConversationTypeEnum;
}

export interface GetCorpusConversationsOutputs {
  conversations: {
    pageInfo: {
      hasNextPage: boolean;
      endCursor: string;
    };
    edges: Array<{
      node: {
        id: string;
        title: string;
        createdAt: string;
        updatedAt: string;
        chatMessages: {
          totalCount: number;
        };
        creator: {
          email: string;
        };
      };
    }>;
  };
}

export interface GetCorpusChatMessagesInputs {
  conversationId: string;
  cursor?: string;
  limit?: number;
}

export interface GetCorpusChatMessagesOutputs {
  chatMessages: {
    edges: Array<{
      node: {
        id: string;
        content: string;
        msgType: string;
        createdAt: string;
        data: {
          sources?: WebSocketSources[];
          message_id?: string;
        };
        creator: {
          email: string;
        };
      };
    }>;
  };
}

export const GET_ME = gql`
  query GetMe {
    me {
      id
      email
      username
      slug
      name
      firstName
      lastName
      phone
      isSuperuser
      isUsageCapped # Crucially, fetch this field
      canImportCorpus # Server-side gate for corpus-import UI
      isProfilePublic # Issue #611
      profileHeadline
      profileAboutMarkdown
      profileLinksMarkdown
    }
  }
`;

// Define interfaces for the query output
export interface GetMeOutputs {
  me: UserType | null; // It can be null if not logged in
}

// No inputs needed for this query
export interface GetMeInputs {}

// Issue #611 - User Profile Page
export const GET_USER = gql`
  query GetUser($slug: String!) {
    userBySlug(slug: $slug) {
      id
      username
      slug
      name
      firstName
      lastName
      email
      isProfilePublic
      profileHeadline
      profileAboutMarkdown
      profileLinksMarkdown
      reputationGlobal
      totalMessages
      totalThreadsCreated
      totalAnnotationsCreated
      totalDocumentsUploaded
    }
  }
`;

export interface GetUserInput {
  slug: string;
}

export interface GetUserOutput {
  // The privacy contract redacts ``username``, ``name``, ``firstName``,
  // ``lastName`` and ``email`` to ``null`` for non-self viewers. Only
  // ``id`` and ``slug`` are guaranteed non-null cross-user.
  userBySlug: {
    id: string;
    username: string | null;
    slug: string;
    name: string | null;
    firstName: string | null;
    lastName: string | null;
    email: string | null;
    isProfilePublic: boolean;
    profileHeadline: string | null;
    profileAboutMarkdown: string | null;
    profileLinksMarkdown: string | null;
    reputationGlobal: number;
    totalMessages: number;
    totalThreadsCreated: number;
    totalAnnotationsCreated: number;
    totalDocumentsUploaded: number;
  } | null;
}

// ID-based resolution queries for navigation fallback
export const GET_CORPUS_BY_ID_FOR_REDIRECT = gql`
  query GetCorpusByIdForRedirect($id: ID!) {
    corpus(id: $id) {
      id
      slug
      title
      creator {
        id
        slug
        username
        email
      }
    }
  }
`;

export interface GetCorpusByIdForRedirectInput {
  id: string;
}

export interface GetCorpusByIdForRedirectOutput {
  corpus: {
    id: string;
    slug: string;
    title: string;
    creator: {
      id: string;
      slug: string;
      username: string;
      email: string;
    };
  } | null;
}

export const GET_DOCUMENT_BY_ID_FOR_REDIRECT = gql`
  query GetDocumentByIdForRedirect($id: ID!) {
    document(id: $id) {
      id
      slug
      title
      creator {
        id
        slug
        username
        email
      }
      corpus {
        id
        slug
        title
        creator {
          id
          slug
          username
          email
        }
      }
    }
  }
`;

export interface GetDocumentByIdForRedirectInput {
  id: string;
}

export interface GetDocumentByIdForRedirectOutput {
  document: {
    id: string;
    slug: string;
    title: string;
    creator: {
      id: string;
      slug: string;
      username: string;
      email: string;
    };
    corpus: {
      id: string;
      slug: string;
      title: string;
      creator: {
        id: string;
        slug: string;
        username: string;
        email: string;
      };
    } | null;
  } | null;
}

///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
/// BADGE-RELATED QUERIES
///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

export const GET_BADGES = gql`
  query GetBadges(
    $badgeType: BadgesBadgeBadgeTypeChoices
    $corpusId: String
    $isAutoAwarded: Boolean
    $limit: Int
    $cursor: String
  ) {
    badges(
      badgeType: $badgeType
      corpusId: $corpusId
      isAutoAwarded: $isAutoAwarded
      first: $limit
      after: $cursor
    ) {
      edges {
        node {
          id
          name
          description
          icon
          badgeType
          color
          isAutoAwarded
          criteriaConfig
          corpus {
            id
            title
          }
          creator {
            id
            slug
            username
          }
          created
        }
      }
      pageInfo {
        hasNextPage
        hasPreviousPage
        startCursor
        endCursor
      }
    }
  }
`;

export interface GetBadgesInput {
  badgeType?: "GLOBAL" | "CORPUS";
  corpusId?: string;
  isAutoAwarded?: boolean;
  limit?: number;
  cursor?: string;
}

export interface BadgeNode {
  id: string;
  name: string;
  description: string;
  icon: string;
  badgeType: string;
  color: string;
  isAutoAwarded: boolean;
  criteriaConfig: any;
  corpus?: {
    id: string;
    title: string;
  };
  creator: {
    id: string;
    username: string;
  };
  created: string;
}

export interface GetBadgesOutput {
  badges: {
    edges: Array<{
      node: BadgeNode;
    }>;
    pageInfo: {
      hasNextPage: boolean;
      hasPreviousPage: boolean;
      startCursor: string;
      endCursor: string;
    };
  };
}

export const GET_USER_BADGES = gql`
  query GetUserBadges(
    $userId: String
    $badgeId: String
    $corpusId: String
    $limit: Int
    $cursor: String
  ) {
    userBadges(
      userId: $userId
      badgeId: $badgeId
      corpusId: $corpusId
      first: $limit
      after: $cursor
    ) {
      edges {
        node {
          id
          awardedAt
          user {
            id
            username
            email
          }
          badge {
            id
            name
            description
            icon
            color
            badgeType
          }
          awardedBy {
            id
            username
          }
          corpus {
            id
            title
          }
        }
      }
      pageInfo {
        hasNextPage
        hasPreviousPage
        startCursor
        endCursor
      }
    }
  }
`;

export interface GetUserBadgesInput {
  userId?: string;
  badgeId?: string;
  corpusId?: string;
  limit?: number;
  cursor?: string;
}

export interface UserBadgeNode {
  id: string;
  awardedAt: string;
  user: {
    id: string;
    username: string;
    email: string;
  };
  badge: {
    id: string;
    name: string;
    description: string;
    icon: string;
    color: string;
    badgeType: string;
  };
  awardedBy?: {
    id: string;
    username: string;
  };
  corpus?: {
    id: string;
    title: string;
  };
}

export interface GetUserBadgesOutput {
  userBadges: {
    edges: Array<{
      node: UserBadgeNode;
    }>;
    pageInfo: {
      hasNextPage: boolean;
      hasPreviousPage: boolean;
      startCursor: string;
      endCursor: string;
    };
  };
}

export const GET_BADGE_CRITERIA_TYPES = gql`
  query GetBadgeCriteriaTypes($scope: String) {
    badgeCriteriaTypes(scope: $scope) {
      typeId
      name
      description
      scope
      fields {
        name
        label
        fieldType
        required
        description
        minValue
        maxValue
        allowedValues
      }
      implemented
    }
  }
`;

export interface GetBadgeCriteriaTypesInput {
  scope?: string;
}

export interface CriteriaField {
  name: string;
  label: string;
  fieldType: string;
  required: boolean;
  description?: string;
  minValue?: number;
  maxValue?: number;
  allowedValues?: string[];
}

export interface CriteriaTypeDefinition {
  typeId: string;
  name: string;
  description: string;
  scope: string;
  fields: CriteriaField[];
  implemented: boolean;
}

export interface GetBadgeCriteriaTypesOutput {
  badgeCriteriaTypes: CriteriaTypeDefinition[];
}

/**
 * ============================================================================
 * NOTIFICATION QUERIES
 * ============================================================================
 */

export const GET_NOTIFICATIONS = gql`
  query GetNotifications(
    $isRead: Boolean
    $notificationType: NotificationsNotificationNotificationTypeChoices
    $limit: Int
    $cursor: String
  ) {
    notifications(
      isRead: $isRead
      notificationType: $notificationType
      first: $limit
      after: $cursor
    ) {
      edges {
        node {
          id
          notificationType
          isRead
          createdAt
          modified
          data
          actor {
            id
            username
            email
          }
          message {
            id
            content
          }
          conversation {
            id
            title
            conversationType
            chatWithCorpus {
              id
              slug
              creator {
                id
                slug
              }
            }
          }
        }
      }
      pageInfo {
        hasNextPage
        hasPreviousPage
        startCursor
        endCursor
      }
      totalCount
    }
  }
`;

export interface GetNotificationsInput {
  isRead?: boolean;
  notificationType?: string;
  limit?: number;
  cursor?: string;
}

export interface NotificationNode {
  id: string;
  notificationType: string;
  isRead: boolean;
  createdAt: string;
  modified: string;
  data?: Record<string, any>;
  actor?: {
    id: string;
    username: string;
    email: string;
  };
  message?: {
    id: string;
    content: string;
  };
  conversation?: {
    id: string;
    title: string;
    conversationType: string;
  };
}

export interface GetNotificationsOutput {
  notifications: {
    edges: Array<{
      node: NotificationNode;
    }>;
    pageInfo: {
      hasNextPage: boolean;
      hasPreviousPage: boolean;
      startCursor: string;
      endCursor: string;
    };
    totalCount: number;
  };
}

// ============================================================================
// Corpus Engagement Metrics Queries (Issue #579)
// ============================================================================

export interface CorpusEngagementMetrics {
  totalThreads: number;
  activeThreads: number;
  totalMessages: number;
  messagesLast7Days: number;
  messagesLast30Days: number;
  uniqueContributors: number;
  activeContributors30Days: number;
  totalUpvotes: number;
  avgMessagesPerThread: number;
  lastUpdated: string;
}

export interface GetCorpusEngagementMetricsInput {
  corpusId: string;
}

export interface GetCorpusEngagementMetricsOutput {
  corpus: {
    id: string;
    title: string;
    engagementMetrics: CorpusEngagementMetrics | null;
  };
}

export const GET_CORPUS_ENGAGEMENT_METRICS = gql`
  query GetCorpusEngagementMetrics($corpusId: ID!) {
    corpus(id: $corpusId) {
      id
      title
      engagementMetrics {
        totalThreads
        activeThreads
        totalMessages
        messagesLast7Days
        messagesLast30Days
        uniqueContributors
        activeContributors30Days
        totalUpvotes
        avgMessagesPerThread
        lastUpdated
      }
    }
  }
`;

// ============================================================================
// Conversation Search Queries (Issue #580)
// ============================================================================

export interface SearchConversationsInput {
  query: string;
  corpusId?: string;
  documentId?: string;
  conversationType?: string;
  topK?: number;
  first?: number;
  after?: string;
  last?: number;
  before?: string;
}

export interface ConversationSearchResult {
  id: string;
  title: string;
  description: string;
  conversationType?: ConversationTypeEnum;
  createdAt: string;
  updatedAt: string;
  created: string; // Alias for compatibility with ConversationType
  modified: string; // Alias for compatibility with ConversationType
  creator: {
    id: string;
    username: string;
  };
  chatMessages: {
    totalCount: number;
  };
  isPinned: boolean;
  isLocked: boolean;
  deletedAt: string | null;
  chatWithCorpus?: {
    id: string;
    title: string;
    slug: string;
    creator: {
      slug: string;
    };
  };
  chatWithDocument?: {
    id: string;
    title: string;
    slug: string;
    creator: {
      slug: string;
    };
  };
}

export interface SearchConversationsOutput {
  searchConversations: {
    edges: Array<{
      node: ConversationSearchResult;
      cursor: string;
    }>;
    pageInfo: {
      hasNextPage: boolean;
      hasPreviousPage: boolean;
      startCursor: string | null;
      endCursor: string | null;
    };
    totalCount: number;
  };
}

export const SEARCH_CONVERSATIONS = gql`
  query SearchConversations(
    $query: String!
    $corpusId: ID
    $documentId: ID
    $conversationType: String
    $topK: Int
    $first: Int
    $after: String
    $last: Int
    $before: String
  ) {
    searchConversations(
      query: $query
      corpusId: $corpusId
      documentId: $documentId
      conversationType: $conversationType
      topK: $topK
      first: $first
      after: $after
      last: $last
      before: $before
    ) {
      edges {
        node {
          id
          title
          description
          conversationType
          createdAt
          updatedAt
          created
          modified
          creator {
            id
            slug
            username
          }
          chatMessages {
            totalCount
          }
          isPinned
          isLocked
          deletedAt
          chatWithCorpus {
            id
            title
            slug
            creator {
              id
              slug
            }
          }
          chatWithDocument {
            id
            title
            slug
            creator {
              id
              slug
            }
          }
        }
        cursor
      }
      pageInfo {
        hasNextPage
        hasPreviousPage
        startCursor
        endCursor
      }
      totalCount
    }
  }
`;

/**
 * Search agents for @ mention autocomplete
 * Backend filters results to active agents visible to the user
 * (global agents + corpus-scoped agents for the given corpus)
 * Part of Issue #623 - @ Mentions Feature (Extended) - Agent Mentions
 */
export interface SearchAgentsForMentionInput {
  textSearch?: string;
  corpusId?: string;
}

export interface SearchAgentsForMentionOutput {
  searchAgentsForMention: {
    edges: Array<{
      node: {
        id: string;
        name: string;
        slug: string;
        description: string;
        scope: "GLOBAL" | "CORPUS";
        mentionFormat: string | null;
        corpus: {
          id: string;
          slug: string;
          title: string;
        } | null;
      };
    }>;
  };
}

export const SEARCH_AGENTS_FOR_MENTION = gql`
  query SearchAgentsForMention($textSearch: String, $corpusId: ID) {
    searchAgentsForMention(
      textSearch: $textSearch
      corpusId: $corpusId
      first: 10
    ) {
      edges {
        node {
          id
          name
          slug
          description
          scope
          mentionFormat
          corpus {
            id
            slug
            title
          }
        }
      }
    }
  }
`;

/**
 * GET_AGENT_CONFIGURATIONS - Get available agent configurations for corpus actions
 * Used in CreateCorpusActionModal to allow selecting an agent for automated actions
 *
 * Supports server-side search via name_Contains and pagination via first parameter.
 */
export interface GetAgentConfigurationsInput {
  corpusId?: string;
  isActive?: boolean;
  name_Contains?: string;
  first?: number;
}

export interface GetAgentConfigurationsOutput {
  agentConfigurations: {
    edges: Array<{
      node: {
        id: string;
        name: string;
        slug: string;
        description: string;
        systemInstructions: string;
        availableTools: string[];
        scope: "GLOBAL" | "CORPUS";
        isActive: boolean;
        corpus?: {
          id: string;
          title: string;
        };
      };
    }>;
  };
}

export const GET_AGENT_CONFIGURATIONS = gql`
  query GetAgentConfigurations(
    $corpusId: String
    $isActive: Boolean
    $name_Contains: String
    $first: Int
  ) {
    agentConfigurations(
      corpusId: $corpusId
      isActive: $isActive
      name_Contains: $name_Contains
      first: $first
    ) {
      edges {
        node {
          id
          name
          slug
          description
          systemInstructions
          availableTools
          scope
          isActive
          corpus {
            id
            title
          }
        }
      }
    }
  }
`;

/**
 * GET_CORPUS_AGENTS - Corpus Agent Management view listing (full agent shape).
 * Requires a corpusId (the detail view is corpus-scoped). Returns every field
 * the row/edit UI needs, including moderation/badge metadata that the lighter
 * GET_AGENT_CONFIGURATIONS query intentionally omits.
 */
export const GET_CORPUS_AGENTS = gql`
  query GetCorpusAgents($corpusId: String!) {
    agentConfigurations(corpusId: $corpusId) {
      edges {
        node {
          id
          name
          slug
          description
          systemInstructions
          availableTools
          permissionRequiredTools
          badgeConfig
          avatarUrl
          scope
          isActive
          isPublic
          creator {
            id
            slug
            username
          }
          created
          modified
        }
      }
    }
  }
`;

/**
 * GET_AVAILABLE_TOOLS - All registered tools plus the category list.
 * Used by the agent management modal to populate the tool-picker UI.
 */
export const GET_AVAILABLE_TOOLS = gql`
  query GetAvailableTools {
    availableTools {
      name
      description
      category
      requiresCorpus
      requiresApproval
    }
    availableToolCategories
  }
`;

/**
 * GET_AVAILABLE_MODERATION_TOOLS - Get available moderation tools from backend
 * Used in CreateCorpusActionModal for inline agent creation with pre-selected tools
 */
export interface AvailableTool {
  name: string;
  description: string;
  category: string;
  requiresApproval: boolean;
}

export interface GetAvailableModerationToolsOutput {
  availableTools: AvailableTool[];
}

export const GET_AVAILABLE_MODERATION_TOOLS = gql`
  query GetAvailableModerationTools {
    availableTools(category: "moderation") {
      name
      description
      category
      requiresApproval
    }
  }
`;

/**
 * GET_AVAILABLE_DOCUMENT_TOOLS - Get available document-category tools from backend
 * Used in CreateCorpusActionModal for inline agent creation on document triggers
 */
export interface GetAvailableDocumentToolsOutput {
  availableTools: AvailableTool[];
}

export const GET_AVAILABLE_DOCUMENT_TOOLS = gql`
  query GetAvailableDocumentTools {
    availableTools(category: "document") {
      name
      description
      category
      requiresApproval
    }
  }
`;

// ============================================================
// CORPUS ACTION EXECUTION QUERIES
// ============================================================

/**
 * Query to fetch corpus action executions (action trail/audit log).
 * Shows all executions of corpus actions with status, timing, and affected objects.
 * Permission-gated: only visible to users with CAN_UPDATE or CAN_PERMISSION.
 */
export const GET_CORPUS_ACTION_EXECUTIONS = gql`
  query GetCorpusActionExecutions(
    $corpusId: ID!
    $corpusActionId: ID
    $status: String
    $actionType: String
    $since: DateTime
    $first: Int
    $after: String
  ) {
    corpusActionExecutions(
      corpusId: $corpusId
      corpusActionId: $corpusActionId
      status: $status
      actionType: $actionType
      since: $since
      first: $first
      after: $after
    ) {
      edges {
        node {
          id
          status
          actionType
          trigger
          queuedAt
          startedAt
          completedAt
          durationSeconds
          waitTimeSeconds
          errorMessage
          affectedObjects
          executionMetadata
          corpusAction {
            id
            name
            fieldset {
              id
              name
            }
            analyzer {
              id
              analyzerId
            }
            agentConfig {
              id
              name
            }
          }
          document {
            id
            title
            slug
            creator {
              id
              slug
            }
          }
          conversation {
            id
            title
          }
          corpus {
            id
            slug
            creator {
              id
              slug
            }
          }
          extract {
            id
            name
          }
          analysis {
            id
          }
          agentResult {
            id
          }
          creator {
            id
            slug
            username
          }
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
      totalCount
    }
  }
`;

export interface AffectedObjectEntry {
  type: string;
  id: number;
  column_name?: string;
  label?: string;
  field?: string;
  old_value?: string;
  new_value?: string;
  revision_id?: number;
}

export interface CorpusActionExecutionNode {
  id: string;
  status: "queued" | "running" | "completed" | "failed" | "skipped";
  actionType: "fieldset" | "analyzer" | "agent";
  trigger: string;
  queuedAt: string;
  startedAt: string | null;
  completedAt: string | null;
  durationSeconds: number | null;
  waitTimeSeconds: number | null;
  errorMessage: string;
  affectedObjects: AffectedObjectEntry[];
  executionMetadata: Record<string, unknown>;
  corpusAction: {
    id: string;
    name: string;
    fieldset?: { id: string; name: string } | null;
    analyzer?: { id: string; analyzerId: string } | null;
    agentConfig?: { id: string; name: string } | null;
  };
  document: {
    id: string;
    title: string;
    slug: string;
    creator: { id: string; slug: string };
  } | null;
  conversation: {
    id: string;
    title: string;
  } | null;
  corpus: {
    id: string;
    slug: string;
    creator: { id: string; slug: string };
  };
  extract?: { id: string; name: string } | null;
  analysis?: { id: string } | null;
  agentResult?: { id: string } | null;
  creator: { id: string; username: string };
}

export interface GetCorpusActionExecutionsInput {
  corpusId: string;
  corpusActionId?: string;
  status?: string;
  actionType?: string;
  since?: string;
  first?: number;
  after?: string;
}

export interface GetCorpusActionExecutionsOutput {
  corpusActionExecutions: {
    edges: Array<{ node: CorpusActionExecutionNode }>;
    pageInfo: {
      hasNextPage: boolean;
      endCursor: string | null;
    };
    totalCount: number;
  };
}

/**
 * Query to fetch aggregated statistics for corpus action executions.
 * Used for the stats summary at the top of the action trail.
 */
export const GET_CORPUS_ACTION_TRAIL_STATS = gql`
  query GetCorpusActionTrailStats($corpusId: ID!, $since: DateTime) {
    corpusActionTrailStats(corpusId: $corpusId, since: $since) {
      totalExecutions
      completed
      failed
      running
      queued
      skipped
      avgDurationSeconds
      fieldsetCount
      analyzerCount
      agentCount
    }
  }
`;

export interface CorpusActionTrailStats {
  totalExecutions: number;
  completed: number;
  failed: number;
  running: number;
  queued: number;
  skipped: number;
  avgDurationSeconds: number | null;
  fieldsetCount: number;
  analyzerCount: number;
  agentCount: number;
}

export interface GetCorpusActionTrailStatsInput {
  corpusId: string;
  since?: string;
}

export interface GetCorpusActionTrailStatsOutput {
  corpusActionTrailStats: CorpusActionTrailStats;
}

// ============================================================================
// MODERATION QUERIES
// ============================================================================

export const GET_MODERATION_ACTIONS = gql`
  query GetModerationActions(
    $corpusId: ID
    $threadId: ID
    $moderatorId: ID
    $actionTypes: [String]
    $automatedOnly: Boolean
    $first: Int
    $after: String
  ) {
    moderationActions(
      corpusId: $corpusId
      threadId: $threadId
      moderatorId: $moderatorId
      actionTypes: $actionTypes
      automatedOnly: $automatedOnly
      first: $first
      after: $after
    ) {
      pageInfo {
        hasNextPage
        hasPreviousPage
        startCursor
        endCursor
      }
      edges {
        cursor
        node {
          id
          actionType
          reason
          created
          canRollback
          isAutomated
          corpusId
          conversation {
            id
            title
          }
          message {
            id
            content
          }
          moderator {
            id
            slug
          }
        }
      }
    }
  }
`;

export interface GetModerationActionsInput {
  corpusId?: string;
  threadId?: string;
  moderatorId?: string;
  actionTypes?: string[];
  automatedOnly?: boolean;
  first?: number;
  after?: string;
}

export interface ModerationActionNode {
  id: string;
  actionType: string;
  reason: string | null;
  created: string;
  canRollback: boolean;
  isAutomated: boolean;
  corpusId: string | null;
  conversation: {
    id: string;
    title: string;
  } | null;
  message: {
    id: string;
    content: string;
  } | null;
  moderator: {
    id: string;
    slug: string | null;
  } | null;
}

export interface GetModerationActionsOutput {
  moderationActions: {
    pageInfo: {
      hasNextPage: boolean;
      hasPreviousPage: boolean;
      startCursor: string | null;
      endCursor: string | null;
    };
    edges: Array<{
      cursor: string;
      node: ModerationActionNode;
    }>;
  };
}

export const GET_MODERATION_METRICS = gql`
  query GetModerationMetrics($corpusId: ID!, $timeRangeHours: Int) {
    moderationMetrics(corpusId: $corpusId, timeRangeHours: $timeRangeHours) {
      totalActions
      automatedActions
      manualActions
      actionsByType
      hourlyActionRate
      isAboveThreshold
      thresholdExceededTypes
      timeRangeHours
      startTime
      endTime
    }
  }
`;

export interface GetModerationMetricsInput {
  corpusId: string;
  timeRangeHours?: number;
}

export interface ModerationMetrics {
  totalActions: number;
  automatedActions: number;
  manualActions: number;
  actionsByType: Record<string, number>;
  hourlyActionRate: number;
  isAboveThreshold: boolean;
  thresholdExceededTypes: string[];
  timeRangeHours: number;
  startTime: string;
  endTime: string;
}

export interface GetModerationMetricsOutput {
  moderationMetrics: ModerationMetrics | null;
}

// ============================================================================
// DOCUMENT RELATIONSHIP QUERIES
// ============================================================================

export interface GetDocumentRelationshipsInput {
  corpusId?: string;
  documentId?: string;
  first?: number;
  after?: string;
}

export interface DocumentRelationshipNode {
  id: string;
  relationshipType: string;
  data?: Record<string, any>;
  sourceDocument: {
    id: string;
    title: string;
    description?: string;
    fileType?: string;
    icon?: string;
    slug?: string;
    creator?: {
      slug?: string;
    };
  };
  targetDocument: {
    id: string;
    title: string;
    description?: string;
    fileType?: string;
    icon?: string;
    slug?: string;
    creator?: {
      slug?: string;
    };
  };
  annotationLabel?: {
    id: string;
    text: string;
    color: string;
    icon?: string;
  };
  corpus: {
    id: string;
    slug?: string;
    creator?: {
      slug?: string;
    };
  };
  creator: {
    id: string;
    username: string;
  };
  created: string;
  modified: string;
  myPermissions?: string[];
}

export interface GetDocumentRelationshipsOutput {
  documentRelationships: {
    edges: Array<{
      node: DocumentRelationshipNode;
      cursor: string;
    }>;
    pageInfo: PageInfo;
    totalCount: number;
  };
}

export const GET_DOCUMENT_RELATIONSHIPS = gql`
  query GetDocumentRelationships(
    $corpusId: ID
    $documentId: ID
    $first: Int
    $after: String
  ) {
    documentRelationships(
      corpusId: $corpusId
      documentId: $documentId
      first: $first
      after: $after
    ) {
      edges {
        node {
          id
          relationshipType
          data
          sourceDocument {
            id
            title
            description
            fileType
            icon
            slug
            creator {
              id
              slug
            }
          }
          targetDocument {
            id
            title
            description
            fileType
            icon
            slug
            creator {
              id
              slug
            }
          }
          annotationLabel {
            id
            text
            color
            icon
          }
          corpus {
            id
            slug
            creator {
              id
              slug
            }
          }
          creator {
            id
            slug
            username
          }
          created
          modified
          myPermissions
        }
        cursor
      }
      pageInfo {
        hasNextPage
        hasPreviousPage
        startCursor
        endCursor
      }
      totalCount
    }
  }
`;

// Lightweight query for TOC - gets all documents in a corpus with minimal fields.
// Intentionally omits `icon` (the TOC renders an icon derived from `fileType`
// on the frontend) and `creator` (unused). Dropping these avoids one file-URL
// resolver call per document plus an extra join on every page load.
export interface GetCorpusDocumentsForTocInput {
  corpusId: string;
  first?: number;
}

export interface CorpusDocumentForToc {
  id: string;
  title: string;
  description: string | null;
  slug: string;
  fileType: string | null;
}

export interface GetCorpusDocumentsForTocOutput {
  documents: {
    edges: Array<{
      node: CorpusDocumentForToc;
    }>;
    totalCount: number;
    pageInfo: {
      hasNextPage: boolean;
      hasPreviousPage: boolean;
      startCursor: string | null;
      endCursor: string | null;
    };
  };
}

export const GET_CORPUS_DOCUMENTS_FOR_TOC = gql`
  query GetCorpusDocumentsForToc($corpusId: String!, $first: Int) {
    documents(inCorpusWithId: $corpusId, first: $first) {
      edges {
        node {
          id
          title
          description
          slug
          fileType
        }
      }
      totalCount
      pageInfo {
        hasNextPage
        hasPreviousPage
        startCursor
        endCursor
      }
    }
  }
`;

// Ultra-lean relationships query for the corpus TOC tree.
// Only source/target IDs and the relationship identity are needed to compute
// parent/child edges; document metadata is supplied by GET_CORPUS_DOCUMENTS_FOR_TOC.
// Server-side filtering on `relationshipType` and `annotationLabelText` keeps
// the result set restricted to "parent"-labeled RELATIONSHIP rows.
export interface GetCorpusDocumentTocEdgesInput {
  corpusId: string;
  first?: number;
  relationshipType?: string;
  annotationLabelText?: string;
}

export interface CorpusDocumentTocEdge {
  id: string;
  // `sourceDocument` and `targetDocument` are typed nullable because the
  // GraphQL schema marks every relation field as nullable by default. At the
  // database level the underlying FKs on `DocumentRelationship` are non-null,
  // so in practice these are always present — but consumers must still null-
  // guard on the unwrapped value to keep TypeScript happy (and to remain
  // safe against any future permission-scoped scrubs of the related rows).
  sourceDocument: { id: string } | null;
  targetDocument: { id: string } | null;
}

export interface GetCorpusDocumentTocEdgesOutput {
  documentRelationships: {
    edges: Array<{
      node: CorpusDocumentTocEdge;
    }>;
    totalCount: number;
    pageInfo: {
      hasNextPage: boolean;
    };
  };
}

export const GET_CORPUS_DOCUMENT_TOC_EDGES = gql`
  query GetCorpusDocumentTocEdges(
    $corpusId: ID
    $first: Int
    $relationshipType: String
    $annotationLabelText: String
  ) {
    documentRelationships(
      corpusId: $corpusId
      first: $first
      relationshipType: $relationshipType
      annotationLabelText: $annotationLabelText
    ) {
      edges {
        node {
          id
          sourceDocument {
            id
          }
          targetDocument {
            id
          }
        }
      }
      totalCount
      pageInfo {
        hasNextPage
      }
    }
  }
`;

// ============================================================================
// CAML ARTICLE (Readme.CAML document)
// ============================================================================

export const GET_CORPUS_ARTICLE = gql`
  query GetCorpusArticle($corpusId: String!, $title: String!) {
    documents(
      inCorpusWithId: $corpusId
      title: $title
      includeCaml: true
      first: 1
    ) {
      edges {
        node {
          id
          title
          txtExtractFile
          modified
          creator {
            id
            slug
            email
          }
        }
      }
    }
  }
`;

export interface GetCorpusArticleInput {
  corpusId: string;
  title: string;
}

export interface GetCorpusArticleOutput {
  documents: {
    edges: Array<{
      node: {
        id: string;
        title: string;
        txtExtractFile: string | null;
        modified: string;
        creator: {
          id: string;
          email: string;
        };
      };
    }>;
  };
}

// ============================================================================
// CORPUS ACTION TEMPLATES
// ============================================================================

export const GET_CORPUS_ACTION_TEMPLATES = gql`
  query GetCorpusActionTemplates($isActive: Boolean) {
    corpusActionTemplates(isActive: $isActive) {
      edges {
        node {
          id
          name
          description
          trigger
          sortOrder
          isActive
        }
      }
    }
  }
`;

export interface CorpusActionTemplateNode {
  id: string;
  name: string;
  description: string;
  trigger: string;
  sortOrder: number;
  isActive: boolean;
}

export interface GetCorpusActionTemplatesInput {
  isActive?: boolean;
}

export interface GetCorpusActionTemplatesOutput {
  corpusActionTemplates: {
    edges: Array<{
      node: CorpusActionTemplateNode;
    }>;
  };
}

// ============================================================================
// DOCUMENT ANNOTATION INDEX (within-document TOC)
// ============================================================================

export const GET_DOCUMENT_ANNOTATION_INDEX = gql`
  query GetDocumentAnnotationIndex(
    $documentId: ID!
    $corpusId: ID
    $labelText: String
    $first: Int
  ) {
    annotations(
      documentId: $documentId
      corpusId: $corpusId
      annotationLabel_Text: $labelText
      structural: false
      first: $first
    ) {
      totalCount
      edges {
        node {
          id
          rawText
          longDescription
          page
          parent {
            id
          }
        }
      }
    }
  }
`;

export interface AnnotationIndexNode {
  id: string;
  rawText: string | null;
  longDescription: string | null;
  page: number;
  parent: { id: string } | null;
}

export interface GetDocumentAnnotationIndexInput {
  documentId: string;
  corpusId?: string;
  labelText?: string;
  first?: number;
}

export interface GetDocumentAnnotationIndexOutput {
  annotations: {
    totalCount: number;
    edges: Array<{
      node: AnnotationIndexNode;
    }>;
  };
}

/* ------------------------------------------------------------------ *
 * Deep-research reports (opencontractserver/research)
 *
 * Selections are inlined (matching this file's convention — no gql
 * fragments are used here). The detail selection is duplicated across the
 * id- and slug-resolving queries the same way RESOLVE_EXTRACT_BY_ID /
 * REQUEST_GET_EXTRACT duplicate theirs.
 * ------------------------------------------------------------------ */

export interface GetResearchReportInput {
  id: string;
}
export interface GetResearchReportOutput {
  researchReport: ResearchReportType | null;
}
export const GET_RESEARCH_REPORT = gql`
  query GetResearchReport($id: ID!) {
    researchReport(id: $id) {
      id
      status
      prompt
      title
      slug
      content
      findings
      citations
      toolCallLog
      modelUsage
      warnings
      durationSeconds
      stepCount
      maxSteps
      cancelRequested
      errorMessage
      created
      modified
      startedAt
      completedAt
      lastProgressAt
      myPermissions
      corpus {
        id
        slug
        title
        creator {
          id
          slug
        }
      }
      fullSourceAnnotationList {
        id
        page
        rawText
      }
      fullSourceDocumentList {
        id
        slug
        title
        creator {
          id
          slug
        }
        corpus {
          id
          slug
          creator {
            id
            slug
          }
        }
      }
    }
  }
`;

export interface ResolveResearchReportBySlugInput {
  slug: string;
}
export interface ResolveResearchReportBySlugOutput {
  researchReportBySlug: ResearchReportType | null;
}
export const RESOLVE_RESEARCH_REPORT_BY_SLUG = gql`
  query ResolveResearchReportBySlug($slug: String!) {
    researchReportBySlug(slug: $slug) {
      id
      status
      prompt
      title
      slug
      content
      findings
      citations
      toolCallLog
      modelUsage
      warnings
      durationSeconds
      stepCount
      maxSteps
      cancelRequested
      errorMessage
      created
      modified
      startedAt
      completedAt
      lastProgressAt
      myPermissions
      corpus {
        id
        slug
        title
        creator {
          id
          slug
        }
      }
      fullSourceAnnotationList {
        id
        page
        rawText
      }
      fullSourceDocumentList {
        id
        slug
        title
        creator {
          id
          slug
        }
        corpus {
          id
          slug
          creator {
            id
            slug
          }
        }
      }
    }
  }
`;

export interface GetResearchReportsInput {
  corpusId?: string;
  status?: JobStatus;
  cursor?: string;
  limit?: number;
}
export interface GetResearchReportsOutput {
  researchReports: {
    pageInfo: PageInfo;
    edges: { node: ResearchReportListItem }[];
  };
}
export const GET_RESEARCH_REPORTS = gql`
  query GetResearchReports(
    $corpusId: ID
    $status: String
    $cursor: String
    $limit: Int
  ) {
    researchReports(
      corpusId: $corpusId
      status: $status
      first: $limit
      after: $cursor
    ) {
      edges {
        node {
          id
          slug
          title
          status
          stepCount
          maxSteps
          created
          startedAt
          completedAt
          durationSeconds
          corpus {
            id
            title
          }
        }
      }
      pageInfo {
        hasNextPage
        hasPreviousPage
        startCursor
        endCursor
      }
    }
  }
`;
