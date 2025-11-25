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
  CorpusQueryType,
  CorpusQueryTypeConnection,
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
} from "../types/graphql-api";
import { ExportObject } from "../types/graphql-api";
import { WebSocketSources } from "../components/knowledge_base/document/right_tray/ChatTray";

export interface RequestDocumentsInputs {
  textSearch?: string;
  corpusId?: string;
  inFolderId?: string; // Use "__root__" for root documents, folder ID, or omit for all
  annotateDocLabels?: boolean;
  hasLabelWithId?: string;
}

export interface RequestDocumentsOutputs {
  documents: {
    edges: DocumentTypeEdge[];
    pageInfo: PageInfo;
  };
}

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
  ) {
    documents(
      inCorpusWithId: $inCorpusWithId
      inFolderId: $inFolderId
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
            slug
          }
          is_selected @client
          is_open @client
          hasVersionHistory
          versionCount
          isLatestVersion
          canViewHistory
          doc_label_annotations: docAnnotations(
            annotationLabel_LabelType: DOC_TYPE_LABEL
          ) @include(if: $annotateDocLabels) {
            edges {
              node {
                id
                annotationLabel {
                  labelType
                  text
                }
                corpus {
                  title
                  icon
                  preferredEmbedder
                }
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
    }
  }
`;

// ---------------- Slug resolution ----------------
export const USER_BY_SLUG = gql`
  query ($slug: String!) {
    userBySlug(slug: $slug) {
      id
      slug
      username
    }
  }
`;

export const CORPUS_BY_SLUGS = gql`
  query ($userSlug: String!, $corpusSlug: String!) {
    corpusBySlugs(userSlug: $userSlug, corpusSlug: $corpusSlug) {
      id
      slug
      title
    }
  }
`;

export const DOCUMENT_BY_SLUGS = gql`
  query ($userSlug: String!, $documentSlug: String!) {
    documentBySlugs(userSlug: $userSlug, documentSlug: $documentSlug) {
      id
      slug
      title
    }
  }
`;

export const DOCUMENT_IN_CORPUS_BY_SLUGS = gql`
  query ($userSlug: String!, $corpusSlug: String!, $documentSlug: String!) {
    documentInCorpusBySlugs(
      userSlug: $userSlug
      corpusSlug: $corpusSlug
      documentSlug: $documentSlug
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
      mdDescription
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
      documents {
        totalCount
      }
      analyses {
        totalCount
      }
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
  ) {
    corpusBySlugs(userSlug: $userSlug, corpusSlug: $corpusSlug) {
      id
      slug
      title
      description
      mdDescription
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
      creator {
        id
        username
        slug
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
      mdDescription
      myPermissions
      creator {
        id
        username
        slug
      }
      descriptionRevisions {
        id
        version
        author {
          id
          email
        }
        created
        diff
        snapshot
      }
      allAnnotationSummaries {
        id
        rawText
        json
        annotationLabel {
          id
          text
        }
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
      mdDescription
      created
      modified
      isPublic
      myPermissions
      creator {
        id
        email
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
          email
          __typename
        }
        created
        diff
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
  diff: string;
  snapshot?: string;
  __typename: string;
}

export interface GetCorpusWithHistoryQuery {
  corpus: {
    id: string;
    slug?: string | null;
    title: string;
    description: string;
    mdDescription?: string | null;
    created: string;
    modified: string;
    isPublic: boolean;
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

export interface GetCorpusQueryDetailsInputType {
  corpusId: string;
}

export interface GetCorpusQueryDetailsOutputType {
  corpusQuery: CorpusQueryType;
}

export const GET_CORPUS_QUERY_DETAILS = gql`
  query CorpusQuery($corpusId: ID!) {
    corpusQuery(id: $corpusId) {
      id
      response
      query
      started
      failed
      completed
      stacktrace
      fullSourceList {
        id
        annotationLabel {
          id
          icon
          color
          description
          text
          labelType
          readOnly
        }
        annotationType
        rawText
        json
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
        tokensJsons
        document {
          id
          title
          is_selected @client
          is_open @client
          description
          backendLock
          fileType
          pdfFile
          txtExtractFile
          pawlsParseFile
          icon
        }
      }
    }
  }
`;

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
    }
  }
`;

export interface GetCorpusQueriesInput {
  corpusId: string;
}

export interface GetCorpusQueriesOutput {
  corpusQueries: CorpusQueryTypeConnection;
}

export const GET_CORPUS_QUERIES = gql`
  query CorpusQueries($corpusId: ID!) {
    corpusQueries(corpusId: $corpusId) {
      edges {
        node {
          id
          query
          response
          started
          completed
          failed
        }
      }
      pageInfo {
        hasNextPage
        hasPreviousPage
        endCursor
        startCursor
      }
    }
  }
`;

export interface GetCorpusQueryInputType {
  corpusId: string;
}

export interface GetCorpusQueryOutputType {
  corpusQuery: CorpusQueryType;
}

export const GET_CORPUS_QUERY = gql`
  query FullCorpusQuery($corpusId: ID!) {
    corpusQuery(id: $corpusId) {
      id
      query
      response
      fullSourceList {
        id
        isPublic
        myPermissions
        annotationLabel {
          id
          icon
          color
          description
          text
          labelType
          readOnly
        }
        boundingBox
        page
        rawText
        tokensJsons
        json
        creator {
          id
          email
        }
        isPublic
        myPermissions
      }
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

// TODO - revise this query to permit filtering described above in its inputs.
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
  ) {
    corpuses(
      textSearch: $textSearch
      usesLabelsetId: $usesLabelsetId
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
            email
            slug
          }
          description
          preferredEmbedder
          appliedAnalyzerIds
          isPublic
          is_selected @client
          is_open @client
          myPermissions
          parent {
            id
            icon
            title
            description
          }
          annotations {
            totalCount
          }
          documents {
            totalCount
            edges {
              node {
                id
                fileType
                backendLock
                description
              }
            }
          }
          labelSet {
            id
            title
            description
            docLabelCount
            spanLabelCount
            tokenLabelCount
          }
        }
      }
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
      edges {
        node {
          id
          icon
          title
          description
          created
          isPublic
          myPermissions
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
  rawText_Contains?: string;
  analysis_Isnull?: boolean;
  annotationLabel_description_search_string?: string;
  annotationLabel_title_search_string?: string;
  annotationLabel_Type?: string;
  createdWithAnalyzerId?: string;
  createdByAnalysisIds?: string;
  structural?: boolean;
}

export interface GetAnnotationsOutputs {
  annotations: {
    pageInfo: PageInfo;
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
      structural: $structural
      first: $limit
      after: $cursor
    ) {
      edges {
        node {
          id
          tokensJsons
          json
          page
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
          isPublic
          myPermissions
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
      isPublic
      myPermissions
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

export interface RequestPageAnnotationDataInputs {
  selectedDocumentId: string;
}

export interface RequestPageAnnotationDataOutputs {
  existingTextAnnotations: ServerAnnotationType[];
  existingDocLabelAnnotations: ServerAnnotationType[];
  existingRelationships: RelationshipType[];
  selectedAnalyzersWithLabels: {
    edges: {
      node: AnalyzerType;
    }[];
  };
  corpus: {
    id: string;
    labelSet: LabelSet;
  };
}

export const REQUEST_PAGE_ANNOTATION_DATA = gql`
  query ($selectedDocumentId: ID!) {
    selectedAnalyzersSpanAnnotations: pageAnnotations(
      documentId: $selectedDocumentId
      labelType: TOKEN_LABEL
    ) {
      pdfPageInfo {
        pageCount
        currentPage
        hasNextPage
        corpusId
        documentId
        labelType
        forAnalysisIds
      }
      pageAnnotations {
        id
        isPublic
        myPermissions
        annotationLabel {
          id
          text
          color
          icon
          description
          labelType
        }
        annotationType
        boundingBox
        page
        rawText
        tokensJsons
        json
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
          email
        }
        isPublic
        myPermissions
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

export interface GetExportInputType {
  id: string;
}

export interface GetExportOutputType {
  extract: ExtractType;
}

export const GET_EXPORT = gql`
  query getExtract($id: ID!) {
    extract(id: $id) {
      id
      name
      fullDatacellList {
        id
        isPublic
      }
      fieldset {
        inUse
        fullColumnList {
          id
          instructions
          extractIsList
          limitToLabel
          taskName
          matchText
          query
          outputType
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

export interface GetFieldsetOutputs {
  fieldset: FieldsetType;
}

export const GET_FIELDSET = gql`
  query GetFieldset($id: ID!) {
    fieldset(id: $id) {
      id
      creator {
        id
        username
      }
      name
      description
      inUse
      columns {
        id
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
        username
      }
      created
      started
      finished
      error
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
          boundingBox
          page
          rawText
          tokensJsons
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
            columns {
              edges {
                node {
                  id
                  query
                }
              }
            }
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
          boundingBox
          page
          rawText
          tokensJsons
          json
        }
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
        boundingBox
        page
        rawText
        tokensJsons
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
          relationshipLabel {
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
        }
      }
    }
  }
`;

export interface GetDocumentAnnotationsAndRelationshipsInput {
  documentId: string;
  corpusId: string;
  analysisId?: string;
}

export interface GetDocumentAnnotationsAndRelationshipsOutput {
  document: DocumentType;
  corpus: CorpusType;
}

/**
 * If analysisId is set to __none__ you will get annotations and relationships with NO linked analysis
 */
export const GET_DOCUMENT_ANNOTATIONS_AND_RELATIONSHIPS = gql`
  query GetDocumentAnnotationsAndRelationships(
    $documentId: String!
    $corpusId: ID!
    $analysisId: ID
  ) {
    document(id: $documentId) {
      id
      allStructuralAnnotations {
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
        myPermissions
        structural
      }
      allAnnotations(corpusId: $corpusId, analysisId: $analysisId) {
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
        myPermissions
        structural
      }
      allRelationships(corpusId: $corpusId, analysisId: $analysisId) {
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

export const getAnnotationsByDocumentId = /* GraphQL */ `
  query GetAnnotationsByDocumentId($documentId: ID!) {
    getAnnotationsByDocumentId(documentId: $documentId) {
      items {
        id
        documentId
        start
        end
        selectedText
        comment
        annotationType
        createdAt
        updatedAt
        owner
      }
    }
  }
`;

export const listAnnotations = /* GraphQL */ `
  query ListAnnotations(
    $filter: ModelAnnotationFilterInput
    $limit: Int
    $nextToken: String
  ) {
    listAnnotations(filter: $filter, limit: $limit, nextToken: $nextToken) {
      items {
        id
        documentId
        start
        end
        selectedText
        comment
        annotationType
        createdAt
        updatedAt
        owner
      }
      nextToken
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
        # userVote  # TODO: Backend field not implemented yet

        # Soft delete
        deletedAt

        # Mentioned resources (Issue #623)
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
        username: string;
        email: string | null;
        slug: string | null;
      };
    }>;
  };
}

export const SEARCH_USERS_FOR_MENTION = gql`
  query SearchUsersForMention($textSearch: String!) {
    searchUsersForMention(textSearch: $textSearch, first: 10) {
      edges {
        node {
          id
          username
          email
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
 */
export interface SearchDocumentsForMentionInput {
  textSearch: string;
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
        corpusSet: {
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
      };
    }>;
  };
}

export const SEARCH_DOCUMENTS_FOR_MENTION = gql`
  query SearchDocumentsForMention($textSearch: String!) {
    searchDocumentsForMention(textSearch: $textSearch, first: 10) {
      edges {
        node {
          id
          slug
          title
          creator {
            slug
          }
          corpusSet(first: 1) {
            edges {
              node {
                id
                slug
                title
                creator {
                  slug
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
        };
        corpus: {
          id: string;
          title: string;
        } | null;
      };
    }>;
  };
}

export const SEARCH_ANNOTATIONS_FOR_MENTION = gql`
  query SearchAnnotationsForMention($textSearch: String!, $corpusId: ID) {
    searchAnnotationsForMention(
      textSearch: $textSearch
      corpusId: $corpusId
      first: 10
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
          }
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
      }
    }
  }
`;

export interface GetDocumentDetailsInput {
  documentId: string;
}

export interface GetDocumentDetailsOutput {
  document: RawDocumentType;
}

export const GET_DOCUMENT_DETAILS = gql`
  query GetDocumentDetails($documentId: String!) {
    document(id: $documentId) {
      id
      title
      fileType
      creator {
        email
      }
      created
      mdSummaryFile
      pdfFile
      txtExtractFile
      pawlsParseFile
      myPermissions
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
    $documentId: String!
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
          email
        }
      }
      allDocRelationships(corpusId: $corpusId) {
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

      # Annotation fields
      allStructuralAnnotations {
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
        myPermissions
        structural
      }
      allAnnotations(corpusId: $corpusId, analysisId: $analysisId) {
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
        myPermissions
        structural
      }
      allRelationships(corpusId: $corpusId, analysisId: $analysisId) {
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
    allStructuralAnnotations: ServerAnnotationType[];
    allAnnotations: ServerAnnotationType[];
    allRelationships: RelationshipType[];
  };
}

export const GET_DOCUMENT_ANNOTATIONS_ONLY = gql`
  query GetDocumentAnnotationsOnly(
    $documentId: String!
    $corpusId: ID!
    $analysisId: ID
  ) {
    document(id: $documentId) {
      id
      allStructuralAnnotations {
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
        myPermissions
        structural
      }
      allAnnotations(corpusId: $corpusId, analysisId: $analysisId) {
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
        myPermissions
        structural
      }
      allRelationships(corpusId: $corpusId, analysisId: $analysisId) {
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
    allStructuralAnnotations?: ServerAnnotationType[];
    allNotesWithoutCorpus?: Array<{
      id: string;
      title: string;
      content: string;
      creator: {
        email: string;
      };
      created: string;
    }>;
    corpusSet?: {
      edges: Array<{
        node: {
          id: string;
          title: string;
        };
      }>;
    };
  };
}

export const GET_DOCUMENT_WITH_STRUCTURE = gql`
  query GetDocumentWithStructure($documentId: String!) {
    document(id: $documentId) {
      id
      title
      fileType
      creator {
        id
        email
      }
      created
      pdfFile
      pdfFileHash
      txtExtractFile
      pawlsParseFile
      myPermissions
      # Structural annotations (headers, sections, etc.) - no corpus required
      allStructuralAnnotations {
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
        myPermissions
        structural
      }
      # Structural relationships (no corpus required)
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
          email
        }
        created
      }
      # Check if document is in any corpus (for UI hints)
      corpusSet {
        edges {
          node {
            id
            title
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
          documents {
            totalCount
          }
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
  // Add other fields (data, createdAt, creator, etc.) if you need them
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
        name
        description
        badgeConfig
        avatarUrl
      }
      content
      state
      data
      creator {
        id
        username
        email
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
  ) {
    conversations(
      corpusId: $corpusId
      title_Contains: $title_Contains
      createdAt_Gte: $createdAt_Gte
      createdAt_Lte: $createdAt_Lte
      first: $limit
      after: $cursor
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
      username
      slug
      name
      firstName
      lastName
      phone
      isUsageCapped # Crucially, fetch this field
      isProfilePublic # Issue #611
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
  userBySlug: {
    id: string;
    username: string;
    slug: string;
    name: string;
    firstName: string;
    lastName: string;
    email: string;
    isProfilePublic: boolean;
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
  query GetDocumentByIdForRedirect($id: String!) {
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

export const GET_UNREAD_NOTIFICATION_COUNT = gql`
  query GetUnreadNotificationCount {
    unreadNotificationCount
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

export interface GetUnreadNotificationCountOutput {
  unreadNotificationCount: number;
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
              slug
            }
          }
          chatWithDocument {
            id
            title
            slug
            creator {
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
