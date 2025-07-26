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
  ConversationTypeConnection,
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
      textSearch: $textSearch
      hasLabelWithId: $hasLabelWithId
      hasAnnotationsWithIds: $hasAnnotationsWithIds
      first: $limit
      after: $cursor
    ) {
      edges {
        node {
          id
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
          is_selected @client
          is_open @client
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
          metadata_annotations: docAnnotations(
            annotationLabel_LabelType: METADATA_LABEL
          ) @include(if: $includeMetadata) {
            edges {
              node {
                id
                annotationLabel {
                  labelType
                  text
                }
                rawText
                corpus {
                  title
                  icon
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
      title
      description
      mdDescription
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
      allAnnotationSummaries(labelTypes: [METADATA_LABEL]) {
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
      title
      description
      mdDescription
      created
      modified
      creator {
        id
        email
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
  };
  created: string;
  diff: string;
  snapshot?: string;
}

export interface GetCorpusWithHistoryQuery {
  corpus: {
    id: string;
    title: string;
    description: string;
    mdDescription?: string;
    created: string;
    modified: string;
    creator: {
      id: string;
      email: string;
    };
    descriptionRevisions: CorpusRevision[];
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
          icon
          title
          creator {
            email
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
            metadataLabelCount
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
            icon
            title
            description
            preferredEmbedder
            __typename
          }
          document {
            id
            title
            description
            backendLock
            pdfFile
            txtExtractFile
            pawlsParseFile
            icon
            fileType
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
  ) {
    conversations(
      documentId: $documentId
      corpusId: $corpusId
      first: $limit
      after: $cursor
      title_Contains: $title_Contains
      createdAt_Gte: $createdAt_Gte
      createdAt_Lte: $createdAt_Lte
    ) {
      edges {
        node {
          id
          title
          createdAt
          updatedAt
          creator {
            id
            email
          }
          chatMessages {
            totalCount
          }
          isPublic
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

/**
 * Fetches all the data needed for the DocumentKnowledgeBase component:
 * - Basic document info (title, fileType, creator, created)
 * - All non-structural annotations for this document in the specified corpus
 * - All direct document-document relationships (e.g., references, related)
 * - All notes associated with this document
 */

export interface GetDocumentKnowledgeBaseInputs {
  documentId: string;
  corpusId: string;
}

export interface GetDocumentKnowledgeBaseOutputs {
  document: DocumentType;
}

export const GET_DOCUMENT_KNOWLEDGE_BASE = gql`
  query GetDocumentKnowledgeBase($documentId: String, $corpusId: ID!) {
    document(id: $documentId) {
      id
      title

      fileType
      creator {
        email
      }
      created
      mdSummaryFile
      allAnnotations(corpusId: $corpusId) {
        id
        page
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
      allNotes(corpusId: $corpusId) {
        id
        title
        content
        created
        creator {
          email
        }
      }
    }
  }
`;

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
        email
      }
      created
      mdSummaryFile
      pdfFile
      txtExtractFile
      pawlsParseFile
      myPermissions
      allNotes(corpusId: $corpusId) {
        id
        title
        content
        created
        creator {
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
      content
      state
      data
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
      # Add any other user fields you need globally
      isUsageCapped # Crucially, fetch this field
      # email
      # firstName
      # lastName
    }
  }
`;

// Define interfaces for the query output
export interface GetMeOutputs {
  me: UserType | null; // It can be null if not logged in
}

// No inputs needed for this query
export interface GetMeInputs {}
