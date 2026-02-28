import { gql } from "@apollo/client";
import { SemanticICONS } from "semantic-ui-react/dist/commonjs/generic";
import { ExportTypes, MultipageAnnotationJson } from "../components/types";
import {
  AnalysisType,
  AnnotationLabelType,
  ColumnType,
  CorpusType,
  DatacellType,
  DocumentType,
  ExtractType,
  FeedbackType,
  FieldsetType,
  LabelSetType,
  LabelType,
  Maybe,
  UserExportType,
  CorpusActionType,
} from "../types/graphql-api";

///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
///
/// LOGIN-RELATED MUTATIONS
///
/// Only used if USE_AUTH0 is set to false
///
///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
export interface LoginInputs {
  username: string;
  password: string;
}

export interface LoginOutputs {
  tokenAuth: {
    token: string;
    refreshExpiresIn: number;
    payload: string;
    user: {
      id: string;
      email: string;
      name: string;
      username: string;
      isUsageCapped: boolean;
      isSuperuser: boolean;
    };
  };
}

export const LOGIN_MUTATION = gql`
  mutation ($username: String!, $password: String!) {
    tokenAuth(username: $username, password: $password) {
      token
      refreshExpiresIn
      payload
      user {
        id
        email
        name
        username
        isUsageCapped
        isSuperuser
      }
    }
  }
`;

///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
/// CORPUS-RELATED MUTATIONS
///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

export interface DeleteCorpusInputs {
  id: string;
}

export interface DeleteCorpusOutputs {
  deleteCorpus: {
    ok?: boolean;
    message?: string;
  };
}

export const DELETE_CORPUS = gql`
  mutation ($id: String!) {
    deleteCorpus(id: $id) {
      ok
      message
    }
  }
`;

export interface UpdateCorpusInputs {
  id: string;
  title?: string;
  description?: string;
  icon?: string;
  filename?: string;
  preferredEmbedder?: string;
  labelSet?: string;
  slug?: string;
  // NOTE: isPublic removed - use SET_CORPUS_VISIBILITY mutation instead
  corpusAgentInstructions?: string;
  documentAgentInstructions?: string;
  categories?: string[];
}

export interface UpdateCorpusOutputs {
  updateCorpus: {
    ok: boolean;
    message: string;
    obj: {
      id: string;
      title: string;
      description: string;
      icon?: string;
      labelSet?: LabelSetType;
    };
  };
}

export const UPDATE_CORPUS = gql`
  mutation (
    $id: String!
    $icon: String
    $description: String
    $labelSet: String
    $title: String
    $preferredEmbedder: String
    $slug: String
    $corpusAgentInstructions: String
    $documentAgentInstructions: String
    $categories: [ID]
  ) {
    updateCorpus(
      id: $id
      icon: $icon
      description: $description
      labelSet: $labelSet
      title: $title
      preferredEmbedder: $preferredEmbedder
      slug: $slug
      corpusAgentInstructions: $corpusAgentInstructions
      documentAgentInstructions: $documentAgentInstructions
      categories: $categories
    ) {
      ok
      message
    }
  }
`;

// NOTE: Use SET_CORPUS_VISIBILITY to change corpus visibility (isPublic)
// This mutation has proper permission checks (owner OR PERMISSION permission)
export interface SetCorpusVisibilityInputs {
  corpusId: string;
  isPublic: boolean;
}

export interface SetCorpusVisibilityOutputs {
  setCorpusVisibility: {
    ok: boolean;
    message: string;
  };
}

export const SET_CORPUS_VISIBILITY = gql`
  mutation SetCorpusVisibility($corpusId: ID!, $isPublic: Boolean!) {
    setCorpusVisibility(corpusId: $corpusId, isPublic: $isPublic) {
      ok
      message
    }
  }
`;

export const UPDATE_CORPUS_DESCRIPTION = gql`
  mutation UpdateCorpusDescription($corpusId: ID!, $newContent: String!) {
    updateCorpusDescription(corpusId: $corpusId, newContent: $newContent) {
      ok
      message
      version
      obj {
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
      }
    }
  }
`;

export interface UpdateCorpusDescriptionInputs {
  corpusId: string;
  newContent: string;
}

export interface UpdateCorpusDescriptionOutputs {
  updateCorpusDescription: {
    ok: boolean;
    message: string;
    version?: number;
    obj?: {
      id: string;
      title: string;
      description: string;
      mdDescription?: string;
      descriptionRevisions: Array<{
        id: string;
        version: number;
        author: {
          id: string;
          email: string;
        };
        created: string;
        diff: string;
        snapshot?: string;
      }>;
    };
  };
}

export interface CreateCorpusInputs {
  title?: string;
  description?: string;
  icon?: string;
  filename?: string;
  labelSet?: string;
  preferredEmbedder?: string;
  categories?: string[];
}

export interface CreateCorpusOutputs {
  createCorpus: {
    ok?: boolean;
    message?: string;
  };
}

export const CREATE_CORPUS = gql`
  mutation (
    $description: String
    $icon: String
    $labelSet: String
    $title: String
    $preferredEmbedder: String
    $slug: String
    $categories: [ID]
  ) {
    createCorpus(
      description: $description
      icon: $icon
      labelSet: $labelSet
      title: $title
      preferredEmbedder: $preferredEmbedder
      slug: $slug
      categories: $categories
    ) {
      ok
      message
    }
  }
`;

export interface StartExportCorpusInputs {
  corpusId: string;
  exportFormat: ExportTypes;
  postProcessors?: string[];
  inputKwargs?: Record<any, any>;
}

export interface StartExportCorpusOutputs {
  exportCorpus: {
    ok?: boolean;
    message?: string;
    export?: Maybe<UserExportType>;
  };
}

export const START_EXPORT_CORPUS = gql`
  mutation (
    $corpusId: String!
    $exportFormat: ExportType!
    $postProcessors: [String]
    $inputKwargs: GenericScalar
  ) {
    exportCorpus(
      corpusId: $corpusId
      exportFormat: $exportFormat
      postProcessors: $postProcessors
      inputKwargs: $inputKwargs
    ) {
      ok
      message
      export {
        id
      }
    }
  }
`;

export interface AcceptCookieConsentInputs {}

export interface AcceptCookieConsentOutputs {
  acceptCookieConsent: {
    ok?: boolean;
    message?: string;
  };
}

export const ACCEPT_COOKIE_CONSENT = gql`
  mutation {
    acceptCookieConsent {
      ok
      message
    }
  }
`;

export interface DeleteExportInputs {
  id: string;
}

export interface DeleteExportOutputs {
  deleteExport: {
    ok?: boolean;
    message?: string;
  };
}

export const DELETE_EXPORT = gql`
  mutation ($id: String!) {
    deleteExport(id: $id) {
      ok
      message
    }
  }
`;

export interface StartImportCorpusInputs {
  base64FileString: string;
}

export interface StartImportCorpusExport {
  ok: boolean;
  message: string;
  corpus: CorpusType;
}

export const START_IMPORT_CORPUS = gql`
  mutation ($base64FileString: String!) {
    importOpenContractsZip(base64FileString: $base64FileString) {
      ok
      message
      corpus {
        id
        icon
        description
        title
        backendLock
      }
    }
  }
`;

export interface StartForkCorpusInput {
  corpusId: string;
}

export interface StartForkCorpusOutput {
  ok: boolean;
  message: string;
  newCorpus: CorpusType;
}

export const START_FORK_CORPUS = gql`
  mutation ($corpusId: String!) {
    forkCorpus(corpusId: $corpusId) {
      ok
      message
      newCorpus {
        id
        icon
        title
        description
        backendLock
        labelSet {
          id
        }
      }
    }
  }
`;

///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
/// LABELSET-RELATED MUTATIONS
///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

export interface DeleteLabelsetInputs {
  id: string;
}

export interface DeleteLabelsetOutputs {
  deleteLabelset: {
    ok?: boolean;
    message?: string;
  };
}

export const DELETE_LABELSET = gql`
  mutation ($id: String!) {
    deleteLabelset(id: $id) {
      ok
      message
    }
  }
`;

export interface CreateLabelsetInputs {
  title?: string;
  description?: string;
  base64IconString?: string;
  filename?: string;
}

export interface CreateLabelsetOutputs {
  ok?: boolean;
  message?: string;
  obj?: LabelSetType;
}

export const CREATE_LABELSET = gql`
  mutation (
    $title: String!
    $description: String
    $icon: String
    $filename: String
  ) {
    createLabelset(
      title: $title
      description: $description
      base64IconString: $icon
      filename: $filename
    ) {
      ok
      message
      obj {
        id
        title
        description
        icon
      }
    }
  }
`;

export interface UpdateLabelsetInputs {
  id: string;
  title?: string;
  description?: string;
  icon?: string;
}

export interface UpdateLabelsetOutputs {
  ok?: boolean;
  message?: string;
}

export const UPDATE_LABELSET = gql`
  mutation ($id: String!, $title: String, $description: String, $icon: String) {
    updateLabelset(
      id: $id
      title: $title
      description: $description
      icon: $icon
    ) {
      ok
      message
    }
  }
`;

///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
/// ANNOTATION LABEL-RELATED MUTATIONS
///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

export interface UpdateAnnotationLabelInputs {
  id: string;
  color?: string;
  description?: string;
  icon?: SemanticICONS;
  text?: string;
  labelType?: LabelType;
}

export interface UpdateAnnotationLabelOutputs {
  updateAnnotationLabel: {
    ok?: boolean;
    message?: string;
  };
}

export const UPDATE_ANNOTATION_LABEL = gql`
  mutation (
    $id: String!
    $color: String
    $description: String
    $icon: String
    $text: String
    $labelType: String
  ) {
    updateAnnotationLabel(
      color: $color
      description: $description
      icon: $icon
      id: $id
      text: $text
      labelType: $labelType
    ) {
      ok
      message
    }
  }
`;

export interface CreateAnnotationLabelInputs {
  color?: string;
  description?: string;
  icon?: SemanticICONS;
  title?: string;
  type?: LabelType;
}

export interface CreateAnnotationLabelOutputs {
  ok?: boolean;
  message?: string;
}

export const CREATE_ANNOTATION_LABEL = gql`
  mutation (
    $color: String
    $description: String
    $icon: String
    $title: String
    $type: String
  ) {
    createLabel(
      color: $color
      description: $description
      icon: $icon
      title: $title
      type: $type
    ) {
      ok
      message
    }
  }
`;

export interface CreateAnnotationLabelForLabelsetInputs {
  color?: string;
  description?: string;
  icon?: SemanticICONS;
  text?: string;
  labelType?: LabelType;
  labelsetId: string;
}

export interface CreateAnnotationLabelForLabelsetOutputs {
  ok?: boolean;
  message?: string;
}

export const CREATE_ANNOTATION_LABEL_FOR_LABELSET = gql`
  mutation (
    $color: String
    $description: String
    $icon: String
    $text: String
    $labelType: String
    $labelsetId: String!
  ) {
    createAnnotationLabelForLabelset(
      color: $color
      description: $description
      icon: $icon
      text: $text
      labelType: $labelType
      labelsetId: $labelsetId
    ) {
      ok
      message
    }
  }
`;

// Smart Label Mutations
export interface SmartLabelSearchOrCreateInputs {
  corpusId: string;
  searchTerm: string;
  labelType: string;
  color?: string;
  description?: string;
  icon?: string;
  createIfNotFound?: boolean;
  labelsetTitle?: string;
  labelsetDescription?: string;
}

export interface SmartLabelSearchOrCreateOutputs {
  smartLabelSearchOrCreate: {
    ok: boolean;
    message: string;
    labels: AnnotationLabelType[];
    labelset?: LabelSetType;
    labelsetCreated: boolean;
    labelCreated: boolean;
  };
}

export const SMART_LABEL_SEARCH_OR_CREATE = gql`
  mutation (
    $corpusId: String!
    $searchTerm: String!
    $labelType: String!
    $color: String
    $description: String
    $icon: String
    $createIfNotFound: Boolean
    $labelsetTitle: String
    $labelsetDescription: String
  ) {
    smartLabelSearchOrCreate(
      corpusId: $corpusId
      searchTerm: $searchTerm
      labelType: $labelType
      color: $color
      description: $description
      icon: $icon
      createIfNotFound: $createIfNotFound
      labelsetTitle: $labelsetTitle
      labelsetDescription: $labelsetDescription
    ) {
      ok
      message
      labels {
        id
        text
        description
        color
        icon
        labelType
      }
      labelset {
        id
        title
        description
      }
      labelsetCreated
      labelCreated
    }
  }
`;

export interface SmartLabelListInputs {
  corpusId: string;
  labelType?: string;
}

export interface SmartLabelListOutputs {
  smartLabelList: {
    ok: boolean;
    message: string;
    labels: AnnotationLabelType[];
    hasLabelset: boolean;
    canCreateLabels: boolean;
  };
}

export const SMART_LABEL_LIST = gql`
  mutation ($corpusId: String!, $labelType: String) {
    smartLabelList(corpusId: $corpusId, labelType: $labelType) {
      ok
      message
      labels {
        id
        text
        description
        color
        icon
        labelType
      }
      hasLabelset
      canCreateLabels
    }
  }
`;

export interface RemoveAnnotationLabelsFromLabelsetInputs {
  label_ids: string[];
  labelset_id: string;
}

export interface RemoveAnnotationLabelsFromLabelsetOutputs {
  ok?: boolean;
  message?: string;
}

export const REMOVE_ANNOTATION_LABELS_FROM_LABELSET = gql`
  mutation ($labelIds: [String]!, $labelsetId: String!) {
    removeAnnotationLabelsFromLabelset(
      labelIds: $labelIds
      labelsetId: $labelsetId
    ) {
      ok
      message
    }
  }
`;

export interface DeleteAnnotationLabelInputs {
  id: string;
}

export interface DeleteAnnotationLabelOutputs {
  ok?: boolean;
  message?: string;
}

export const DELETE_ANNOTATION_LABEL = gql`
  mutation ($id: String!) {
    deleteLabel(id: $id) {
      ok
      message
    }
  }
`;

export interface DeleteMultipleAnnotationLabelInputs {
  annotationLabelIdsToDelete: string[];
}

export interface DeleteMultipleAnnotationLabelOutputs {
  deleteMultipleAnnotationLabels: {
    ok?: boolean;
    message?: string;
  };
}

export const DELETE_MULTIPLE_ANNOTATION_LABELS = gql`
  mutation ($annotationLabelIdsToDelete: [String]!) {
    deleteMultipleAnnotationLabels(
      annotationLabelIdsToDelete: $annotationLabelIdsToDelete
    ) {
      ok
      message
    }
  }
`;

///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
/// DOCUMENT-RELATED MUTATIONS
///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

export interface LinkDocumentsToCorpusInputs {
  corpusId: string;
  documentIds: string[];
}

export interface LinkDocumentsToCorpusOutputs {
  ok?: boolean;
  message?: string;
}

export const LINK_DOCUMENTS_TO_CORPUS = gql`
  mutation ($corpusId: String!, $documentIds: [String]!) {
    linkDocumentsToCorpus(corpusId: $corpusId, documentIds: $documentIds) {
      ok
      message
    }
  }
`;

export interface RemoveDocumentsFromCorpusInputs {
  corpusId: string;
  documentIdsToRemove: string[];
}

export interface RemoveDocumentsFromCorpusOutputs {
  removeDocumentsFromCorpus: {
    ok?: boolean;
    message?: string;
  };
}

export const REMOVE_DOCUMENTS_FROM_CORPUS = gql`
  mutation ($corpusId: String!, $documentIdsToRemove: [String]!) {
    removeDocumentsFromCorpus(
      corpusId: $corpusId
      documentIdsToRemove: $documentIdsToRemove
    ) {
      ok
      message
    }
  }
`;

export interface UploadDocumentInputProps {
  base64FileString: string;
  filename: string;
  customMeta: Record<string, any>;
  makePublic: boolean;
  description?: string;
  title?: string;
  addToCorpusId?: string;
  addToFolderId?: string;
  slug?: string;
}

export interface UploadDocumentOutputProps {
  uploadDocument: {
    ok: boolean;
    message: string;
    document: {
      id: string;
      icon: string;
      pdfFile: string;
      title: string;
      description: string;
      backendLock: boolean;
      fileType: string;
      docAnnotations: {
        edges: {
          node: {
            id: string;
          };
        };
      }[];
    } | null;
  };
}

export const UPLOAD_DOCUMENT = gql`
  mutation (
    $base64FileString: String!
    $filename: String!
    $customMeta: GenericScalar!
    $description: String!
    $title: String!
    $makePublic: Boolean!
    $addToCorpusId: ID
    $addToExtractId: ID
    $addToFolderId: ID
    $slug: String
  ) {
    uploadDocument(
      base64FileString: $base64FileString
      filename: $filename
      customMeta: $customMeta
      description: $description
      title: $title
      makePublic: $makePublic
      addToCorpusId: $addToCorpusId
      addToExtractId: $addToExtractId
      addToFolderId: $addToFolderId
      slug: $slug
    ) {
      ok
      message
      document {
        id
        icon
        pdfFile
        title
        description
        backendLock
        fileType
        docAnnotations {
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

export interface UpdateDocumentInputs {
  id: string;
  title?: string;
  description?: string;
  pdfFile?: string;
  customMeta?: Record<string, any>;
  slug?: string;
}

export interface UpdateDocumentOutputs {
  ok?: boolean;
  message?: string;
}

export const UPDATE_DOCUMENT = gql`
  mutation (
    $id: String!
    $pdfFile: String
    $customMeta: GenericScalar
    $description: String
    $title: String
    $slug: String
  ) {
    updateDocument(
      id: $id
      pdfFile: $pdfFile
      customMeta: $customMeta
      description: $description
      title: $title
      slug: $slug
    ) {
      ok
      message
    }
  }
`;

// ---------------- User profile updates ----------------
export interface UpdateMeInputs {
  name?: string;
  firstName?: string;
  lastName?: string;
  phone?: string;
  slug?: string;
}

export interface UpdateMeOutputs {
  updateMe: {
    ok: boolean;
    message?: string;
    user?: {
      id: string;
      username: string;
      slug?: string;
      name?: string;
      firstName?: string;
      lastName?: string;
      phone?: string;
    };
  };
}

export const UPDATE_ME = gql`
  mutation (
    $name: String
    $firstName: String
    $lastName: String
    $phone: String
    $slug: String
  ) {
    updateMe(
      name: $name
      firstName: $firstName
      lastName: $lastName
      phone: $phone
      slug: $slug
    ) {
      ok
      message
      user {
        id
        username
        slug
        name
        firstName
        lastName
        phone
      }
    }
  }
`;

export interface DeleteDocumenInputs {
  id: string;
}

export interface DeleteDocumentOutputs {
  ok?: boolean;
  message?: string;
}

export const DELETE_DOCUMENT = gql`
  mutation ($id: String!) {
    deleteDocument(id: $id) {
      ok
      message
    }
  }
`;

export interface DeleteMultipleDocumentsInputs {
  documentIdsToDelete: string[];
}

export interface DeleteMultipleDocumentsOutputs {
  ok?: boolean;
  message?: string;
}

export const DELETE_MULTIPLE_DOCUMENTS = gql`
  mutation ($documentIdsToDelete: [String]!) {
    deleteMultipleDocuments(documentIdsToDelete: $documentIdsToDelete) {
      ok
      message
    }
  }
`;

export interface RetryDocumentProcessingOutputType {
  retryDocumentProcessing: {
    ok: boolean;
    message: string;
    document: DocumentType | null;
  };
}

export interface RetryDocumentProcessingInputType {
  documentId: string;
}

export const RETRY_DOCUMENT_PROCESSING = gql`
  mutation ($documentId: String!) {
    retryDocumentProcessing(documentId: $documentId) {
      ok
      message
      document {
        id
        backendLock
        processingStatus
        processingError
        canRetry
      }
    }
  }
`;

export interface NewAnnotationOutputType {
  addAnnotation: {
    ok: boolean;
    annotation: {
      id: string;
      page: number;
      rawText: string;
      json: MultipageAnnotationJson;
      annotationType: LabelType;
      annotationLabel: AnnotationLabelType;
      myPermissions: string[];
      isPublic: boolean;
      sourceNodeInRelationships: {
        edges: [
          {
            node: {
              id: string;
            };
          }
        ];
      };
    };
  };
}

export interface NewAnnotationInputType {
  page: number;
  json: MultipageAnnotationJson;
  rawText: string;
  corpusId: string;
  documentId: string;
  annotationLabelId: string;
  annotationType: LabelType;
}

export const REQUEST_ADD_ANNOTATION = gql`
  mutation (
    $json: GenericScalar!
    $page: Int!
    $rawText: String!
    $corpusId: String!
    $documentId: String!
    $annotationLabelId: String!
    $annotationType: LabelType!
  ) {
    addAnnotation(
      json: $json
      page: $page
      rawText: $rawText
      corpusId: $corpusId
      documentId: $documentId
      annotationLabelId: $annotationLabelId
      annotationType: $annotationType
    ) {
      ok
      annotation {
        id
        page
        bounds: boundingBox
        rawText
        json
        isPublic
        myPermissions
        annotationType
        annotationLabel {
          id
          icon
          description
          color
          text
          labelType
        }
        sourceNodeInRelationships {
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

export interface NewDocTypeAnnotationOutputType {
  addDocTypeAnnotation: {
    ok: boolean;
    annotation: {
      id: string;
      myPermissions?: string[];
      isPublic?: boolean;
      annotationLabel: AnnotationLabelType;
    };
  };
}

export interface NewDocTypeAnnotationInputType {
  corpusId: string;
  documentId: string;
  annotationLabelId: string;
}

export const REQUEST_ADD_DOC_TYPE_ANNOTATION = gql`
  mutation (
    $corpusId: String!
    $documentId: String!
    $annotationLabelId: String!
  ) {
    addDocTypeAnnotation(
      corpusId: $corpusId
      documentId: $documentId
      annotationLabelId: $annotationLabelId
    ) {
      ok
      annotation {
        id
        isPublic
        myPermissions
        annotationLabel {
          id
          icon
          description
          color
          text
          labelType
        }
      }
    }
  }
`;

export interface RemoveDocTypeAnnotationOutputType {
  removeDocTypeAnnotation: {
    ok: boolean;
  };
}

export interface RemoveDocTypeAnnotationInputType {
  annotationId: string;
}

export const REQUEST_DELETE_DOC_TYPE_ANNOTATION = gql`
  mutation ($annotationId: String!) {
    removeDocTypeAnnotation(annotationId: $annotationId) {
      ok
    }
  }
`;

export interface RemoveAnnotationOutputType {
  removeAnnotation: {
    ok: boolean;
  };
}

export interface RemoveAnnotationInputType {
  annotationId: string;
}

export const REQUEST_DELETE_ANNOTATION = gql`
  mutation ($annotationId: String!) {
    removeAnnotation(annotationId: $annotationId) {
      ok
    }
  }
`;

export interface RequestDeleteExtractInputType {
  id: string;
}

export interface RequestDeleteExtractOutputType {
  deleteExtract: {
    ok: boolean;
  };
}

export const REQUEST_DELETE_EXTRACT = gql`
  mutation ($id: String!) {
    deleteExtract(id: $id) {
      ok
    }
  }
`;

export interface NewRelationshipInputType {
  relationshipLabelId: string;
  documentId: string;
  corpusId: string;
  sourceIds: string[];
  targetIds: string[];
}

export interface NewRelationshipOutputType {
  addRelationship: {
    ok: boolean;
    relationship: {
      id: string;
      relationshipLabel: AnnotationLabelType;
      sourceAnnotations: {
        edges: [
          {
            node: {
              id: string;
            };
          }
        ];
      };
      targetAnnotations: {
        edges: [
          {
            node: {
              id: string;
            };
          }
        ];
      };
    };
  };
}

export const REQUEST_CREATE_RELATIONSHIP = gql`
  mutation (
    $sourceIds: [String]!
    $targetIds: [String]!
    $relationshipLabelId: String!
    $corpusId: String!
    $documentId: String!
  ) {
    addRelationship(
      sourceIds: $sourceIds
      targetIds: $targetIds
      relationshipLabelId: $relationshipLabelId
      corpusId: $corpusId
      documentId: $documentId
    ) {
      ok
      relationship {
        id
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
        relationshipLabel {
          id
          icon
          description
          color
          text
          labelType
        }
      }
    }
  }
`;

export interface UpdateRelationshipInput {
  relationshipId: string;
  addSourceIds?: string[];
  addTargetIds?: string[];
  removeSourceIds?: string[];
  removeTargetIds?: string[];
}

export interface UpdateRelationshipOutput {
  updateRelationship: {
    ok: boolean;
    message: string;
    relationship: {
      id: string;
      structural: boolean;
      relationshipLabel: AnnotationLabelType;
      sourceAnnotations: {
        edges: Array<{
          node: {
            id: string;
          };
        }>;
      };
      targetAnnotations: {
        edges: Array<{
          node: {
            id: string;
          };
        }>;
      };
    } | null;
  };
}

export const UPDATE_RELATIONSHIP = gql`
  mutation UpdateRelationship(
    $relationshipId: String!
    $addSourceIds: [String!]
    $addTargetIds: [String!]
    $removeSourceIds: [String!]
    $removeTargetIds: [String!]
  ) {
    updateRelationship(
      relationshipId: $relationshipId
      addSourceIds: $addSourceIds
      addTargetIds: $addTargetIds
      removeSourceIds: $removeSourceIds
      removeTargetIds: $removeTargetIds
    ) {
      ok
      message
      relationship {
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

export interface RemoveRelationshipOutputType {
  removeRelationship: {
    ok: boolean;
  };
}

export interface RemoveRelationshipInputType {
  relationshipId: string;
}

export const REQUEST_REMOVE_RELATIONSHIP = gql`
  mutation ($relationshipId: String!) {
    removeRelationship(relationshipId: $relationshipId) {
      ok
    }
  }
`;

export interface UpdateRelationOutputType {
  updateRelationships: {
    ok: boolean;
  };
}

export interface UpdateRelationInputType {
  relationships: {
    id: string;
    sourceIds: string[];
    targetIds: string[];
    relationshipLabelId: string;
    corpusId: string;
    documentId: string;
  }[];
}

export const REQUEST_UPDATE_RELATIONS = gql`
  mutation ($relationships: [RelationInputType]) {
    updateRelationships(relationships: $relationships) {
      ok
    }
  }
`;

export interface UpdateAnnotationOutputType {
  updateAnnotation: {
    ok?: boolean;
    message?: string;
  };
}

export interface UpdateAnnotationInputType {
  id: string;
  annotationLabel?: string;
  json?: Record<string, any>;
  page?: number;
  rawText?: string;
}

export const REQUEST_UPDATE_ANNOTATION = gql`
  mutation (
    $id: String!
    $annotationLabel: String
    $json: GenericScalar
    $page: Int
    $rawText: String
  ) {
    updateAnnotation(
      id: $id
      annotationLabel: $annotationLabel
      json: $json
      page: $page
      rawText: $rawText
    ) {
      ok
      message
    }
  }
`;

export interface RemoveRelationshipsOutputType {
  removeRelationships: {
    ok: boolean;
  };
}

export interface RemoveRelationshipsInputType {
  relationshipIds: string[];
}

export const REQUEST_REMOVE_RELATIONSHIPS = gql`
  mutation ($relationshipIds: [String]) {
    removeRelationships(relationshipIds: $relationshipIds) {
      ok
    }
  }
`;

///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
/// ANALYZER-RELATED MUTATIONS
///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
export interface RequestDeleteAnalysisOutputType {
  deleteAnalysis: {
    ok: boolean;
    message: string;
  };
}

export interface RequestDeleteAnalysisInputType {
  id: string;
}

export const REQUEST_DELETE_ANALYSIS = gql`
  mutation ($id: String!) {
    deleteAnalysis(id: $id) {
      ok
      message
    }
  }
`;

export interface RequestCreateFieldsetInputType {
  name: string;
  description: string;
}

export interface RequestCreateFieldsetOutputType {
  createFieldset: {
    ok: boolean;
    message: string;
    obj: FieldsetType;
  };
}

export const REQUEST_CREATE_FIELDSET = gql`
  mutation CreateFieldset($name: String!, $description: String!) {
    createFieldset(name: $name, description: $description) {
      ok
      message
      obj {
        id
        name
        description
      }
    }
  }
`;

export interface RequestUpdateFieldsetOutputType {
  updateFieldset: {
    ok: boolean;
    message: string;
    obj: FieldsetType;
  };
}

export interface RequestUpdateFieldsetInputType {
  id: string;
  name?: string;
  description?: string;
}

export const REQUEST_UPDATE_FIELDSET = gql`
  mutation UpdateFieldset($id: ID!, $name: String, $description: String) {
    updateFieldset(id: $id, name: $name, description: $description) {
      msg
      ok
      obj {
        id
        name
        description
      }
    }
  }
`;

export interface RequestCreateColumnInputType {
  fieldsetId?: string;
  query: string;
  matchText?: string;
  outputType: string;
  limitToLabel?: string;
  instructions?: string;
  taskName: string;
  name: string;
}

export interface RequestCreateColumnOutputType {
  createColumn: {
    ok: boolean;
    message: string;
    obj: ColumnType;
  };
}

export const REQUEST_CREATE_COLUMN = gql`
  mutation CreateColumn(
    $name: String!
    $fieldsetId: ID!
    $query: String
    $matchText: String
    $outputType: String!
    $limitToLabel: String
    $instructions: String
    $taskName: String
  ) {
    createColumn(
      fieldsetId: $fieldsetId
      query: $query
      matchText: $matchText
      outputType: $outputType
      limitToLabel: $limitToLabel
      instructions: $instructions
      taskName: $taskName
      name: $name
    ) {
      message
      ok
      obj {
        id
        name
        query
        matchText
        outputType
        limitToLabel
        instructions
        taskName
      }
    }
  }
`;

export interface RequestDeleteColumnOutputType {
  deleteColumn: {
    ok: boolean;
    message: string;
    deletedId: string;
  };
}

export interface RequestDeleteColumnInputType {
  id: string;
}

export const REQUEST_DELETE_COLUMN = gql`
  mutation DeleteColumn($id: ID!) {
    deleteColumn(id: $id) {
      ok
      message
      deletedId
    }
  }
`;

export interface RequestAddDocToExtractOutputType {
  addDocsToExtract: {
    ok: boolean;
    message: string;
    objs: DocumentType[];
  };
}

export interface RequestAddDocToExtractInputType {
  documentIds: string[];
  extractId: string;
}

export const REQUEST_ADD_DOC_TO_EXTRACT = gql`
  mutation AddDocToExtract($documentIds: [ID]!, $extractId: ID!) {
    addDocsToExtract(documentIds: $documentIds, extractId: $extractId) {
      ok
      message
      objs {
        __typename
        id
        title
        description
        pageCount
      }
    }
  }
`;

export interface RequestRemoveDocFromExtractOutputType {
  removeDocsFromExtract: {
    ok: boolean;
    message: string;
    idsRemoved: string[];
  };
}

export interface RequestRemoveDocFromExtractInputType {
  documentIdsToRemove: string[];
  extractId: string;
}

export const REQUEST_REMOVE_DOC_FROM_EXTRACT = gql`
  mutation RemoveDocsFromExtract($documentIdsToRemove: [ID]!, $extractId: ID!) {
    removeDocsFromExtract(
      documentIdsToRemove: $documentIdsToRemove
      extractId: $extractId
    ) {
      ok
      message
      idsRemoved
    }
  }
`;

export interface RequestUpdateColumnInputType {
  id: string;
  fieldsetId?: string;
  query?: string;
  matchText?: string;
  outputType?: string;
  limitToLabel?: string;
  instructions?: string;
  taskName?: string;
}

export interface RequestUpdateColumnOutputType {
  updateColumn: {
    ok: boolean;
    message: string;
    obj: ColumnType;
  };
}

export const REQUEST_UPDATE_COLUMN = gql`
  mutation UpdateColumn(
    $id: ID!
    $name: String
    $query: String
    $matchText: String
    $outputType: String
    $limitToLabel: String
    $instructions: String
    $taskName: String
  ) {
    updateColumn(
      id: $id
      name: $name
      query: $query
      matchText: $matchText
      outputType: $outputType
      limitToLabel: $limitToLabel
      instructions: $instructions
      taskName: $taskName
    ) {
      message
      ok
      obj {
        id
        name
        query
        matchText
        outputType
        limitToLabel
        instructions
        taskName
      }
    }
  }
`;

export interface RequestCreateExtractOutputType {
  createExtract: {
    msg: string;
    ok: boolean;
    obj: ExtractType;
  };
}

export interface RequestCreateExtractInputType {
  corpusId?: string;
  name: string;
  fieldsetId?: string;
}

export const REQUEST_CREATE_EXTRACT = gql`
  mutation CreateExtract($corpusId: ID, $name: String!, $fieldsetId: ID) {
    createExtract(corpusId: $corpusId, name: $name, fieldsetId: $fieldsetId) {
      msg
      ok
      obj {
        id
        name
      }
    }
  }
`;

export interface RequestStartExtractOutputType {
  startExtract: {
    message: string;
    ok: boolean;
    obj: ExtractType;
  };
}

export interface RequestStartExtractInputType {
  extractId: string;
}

export const REQUEST_START_EXTRACT = gql`
  mutation StartExtract($extractId: ID!) {
    startExtract(extractId: $extractId) {
      message
      ok
      obj {
        id
        started
        finished
      }
    }
  }
`;

export interface RequestApproveDatacellInputType {
  datacellId: string;
}

export interface RequestApproveDatacellOutputType {
  approveDatacell: {
    ok: boolean;
    message: string;
    obj: DatacellType;
  };
}

export const REQUEST_APPROVE_DATACELL = gql`
  mutation ApproveDatacell($datacellId: String!) {
    approveDatacell(datacellId: $datacellId) {
      ok
      message
      obj {
        id
        data
        started
        completed
        stacktrace
        correctedData
        column {
          id
        }
        document {
          id
        }
        approvedBy {
          id
          username
        }
        rejectedBy {
          id
          username
        }
      }
    }
  }
`;

export interface RequestRejectDatacellInputType {
  datacellId: string;
}

export interface RequestRejectDatacellOutputType {
  rejectDatacell: {
    ok: boolean;
    message: string;
    obj: DatacellType;
  };
}

export const REQUEST_REJECT_DATACELL = gql`
  mutation RejectDatacell($datacellId: String!) {
    rejectDatacell(datacellId: $datacellId) {
      ok
      message
      obj {
        id
        data
        started
        completed
        stacktrace
        correctedData
        column {
          id
        }
        document {
          id
        }
        approvedBy {
          id
          username
        }
        rejectedBy {
          id
          username
        }
      }
    }
  }
`;

export interface RequestEditDatacellInputType {
  datacellId: string;
  editedData: Record<any, any>;
}

export interface RequestEditDatacellOutputType {
  editDatacell: {
    ok: boolean;
    message: string;
    obj: DatacellType;
  };
}

export const REQUEST_EDIT_DATACELL = gql`
  mutation EditDatacell($datacellId: String!, $editedData: GenericScalar!) {
    editDatacell(datacellId: $datacellId, editedData: $editedData) {
      ok
      message
      obj {
        id
        data
        started
        completed
        stacktrace
        correctedData
        approvedBy {
          id
          username
        }
        rejectedBy {
          id
          username
        }
      }
    }
  }
`;

export interface StartAnalysisInput {
  documentId?: string;
  analyzerId: string;
  corpusId?: string;
  analysisInputData?: Record<string, any>;
}

export interface StartAnalysisOutput {
  startAnalysisOnDoc: {
    ok: boolean;
    message: string;
    obj: AnalysisType;
  };
}

export const START_ANALYSIS = gql`
  mutation StartDocumentAnalysis(
    $documentId: ID
    $analyzerId: ID!
    $corpusId: ID
    $analysisInputData: GenericScalar
  ) {
    startAnalysisOnDoc(
      documentId: $documentId
      analyzerId: $analyzerId
      corpusId: $corpusId
      analysisInputData: $analysisInputData
    ) {
      ok
      message
      obj {
        id
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
        analyzer {
          id
          analyzerId
          description
          manifest
          labelsetSet {
            totalCount
          }
          hostGremlin {
            id
          }
        }
      }
    }
  }
`;

export interface StartDocumentExtractInput {
  documentId: string;
  fieldsetId: string;
  corpusId?: string;
}

export interface StartDocumentExtractOutput {
  startExtractForDoc: {
    ok: boolean;
    message: string;
    obj: ExtractType;
  };
}

export const START_DOCUMENT_EXTRACT = gql`
  mutation StartDocumentExtract(
    $documentId: ID!
    $fieldsetId: ID!
    $corpusId: ID
  ) {
    startExtractForDoc(
      documentId: $documentId
      fieldsetId: $fieldsetId
      corpusId: $corpusId
    ) {
      ok
      message
      obj {
        id
        name
        started
        corpus {
          id
          title
        }
      }
    }
  }
`;

export interface ApproveAnnotationInput {
  annotationId: string;
  comment?: string;
}

export interface RejectAnnotationInput {
  annotationId: string;
  comment?: string;
}

export interface ApproveAnnotationOutput {
  approveAnnotation: {
    ok: boolean;
    userFeedback: FeedbackType | null;
  };
}

export interface RejectAnnotationOutput {
  rejectAnnotation: {
    ok: boolean;
    userFeedback: FeedbackType | null;
  };
}

// Mutations
export const APPROVE_ANNOTATION = gql`
  mutation ApproveAnnotation($annotationId: ID!, $comment: String) {
    approveAnnotation(annotationId: $annotationId, comment: $comment) {
      ok
      userFeedback {
        id
        approved
        rejected
        comment
        commentedAnnotation {
          id
        }
      }
    }
  }
`;

export const REJECT_ANNOTATION = gql`
  mutation RejectAnnotation($annotationId: ID!, $comment: String) {
    rejectAnnotation(annotationId: $annotationId, comment: $comment) {
      ok
      userFeedback {
        id
        approved
        rejected
        comment
        commentedAnnotation {
          id
        }
      }
    }
  }
`;

export interface RequestUpdateExtractInputType {
  id: string;
  title?: string;
  fieldsetId?: string;
}

export interface RequestUpdateExtractOutputType {
  updateExtract: {
    ok: boolean;
    message: string;
    obj: {
      id: string;
    };
  };
}

export const REQUEST_UPDATE_EXTRACT = gql`
  mutation UpdateExtract($id: ID!, $title: String, $fieldsetId: ID) {
    updateExtract(id: $id, title: $title, fieldsetId: $fieldsetId) {
      ok
      message
      obj {
        id
      }
    }
  }
`;

export const UPDATE_CORPUS_SETTINGS = gql`
  mutation UpdateCorpusSettings(
    $corpusId: ID!
    $title: String
    $description: String
    $allowComments: Boolean
  ) {
    updateCorpus(
      input: {
        id: $corpusId
        title: $title
        description: $description
        allowComments: $allowComments
      }
    ) {
      corpus {
        id
        title
        description
        allowComments
      }
    }
  }
`;

export interface UpdateCorpusSettingsInput {
  corpusId: string;
  title?: string;
  description?: string;
  allowComments?: boolean;
}

export interface UpdateCorpusSettingsOutput {
  updateCorpus: {
    corpus: {
      id: string;
      title?: string;
      description?: string;
      allowComments?: boolean;
    };
  };
}

export const CREATE_CORPUS_ACTION = gql`
  mutation CreateCorpusAction(
    $corpusId: ID!
    $trigger: String!
    $name: String
    $fieldsetId: ID
    $analyzerId: ID
    $agentConfigId: ID
    $taskInstructions: String
    $preAuthorizedTools: [String]
    $createAgentInline: Boolean
    $inlineAgentName: String
    $inlineAgentDescription: String
    $inlineAgentInstructions: String
    $inlineAgentTools: [String]
    $disabled: Boolean
    $runOnAllCorpuses: Boolean
  ) {
    createCorpusAction(
      corpusId: $corpusId
      trigger: $trigger
      name: $name
      fieldsetId: $fieldsetId
      analyzerId: $analyzerId
      agentConfigId: $agentConfigId
      taskInstructions: $taskInstructions
      preAuthorizedTools: $preAuthorizedTools
      createAgentInline: $createAgentInline
      inlineAgentName: $inlineAgentName
      inlineAgentDescription: $inlineAgentDescription
      inlineAgentInstructions: $inlineAgentInstructions
      inlineAgentTools: $inlineAgentTools
      disabled: $disabled
      runOnAllCorpuses: $runOnAllCorpuses
    ) {
      ok
      message
      obj {
        id
        name
        trigger
        disabled
        runOnAllCorpuses
        fieldset {
          id
          name
        }
        analyzer {
          id
          description
        }
        agentConfig {
          id
          name
          description
        }
        taskInstructions
        preAuthorizedTools
      }
    }
  }
`;

export interface CreateCorpusActionInput {
  corpusId: string;
  trigger: "add_document" | "edit_document" | "new_thread" | "new_message";
  name?: string;
  fieldsetId?: string;
  analyzerId?: string;
  agentConfigId?: string;
  taskInstructions?: string;
  preAuthorizedTools?: string[];
  // Inline agent creation parameters
  createAgentInline?: boolean;
  inlineAgentName?: string;
  inlineAgentDescription?: string;
  inlineAgentInstructions?: string;
  inlineAgentTools?: string[];
  disabled?: boolean;
  runOnAllCorpuses?: boolean;
}

export interface CreateCorpusActionOutput {
  createCorpusAction: {
    ok: boolean;
    message: string;
    obj: CorpusActionType | null;
  };
}

export const DELETE_CORPUS_ACTION = gql`
  mutation DeleteCorpusAction($id: String!) {
    deleteCorpusAction(id: $id) {
      ok
      message
    }
  }
`;

export interface DeleteCorpusActionInput {
  id: string;
}

export interface DeleteCorpusActionOutput {
  deleteCorpusAction: {
    ok: boolean;
    message: string;
  };
}

export const UPDATE_CORPUS_ACTION = gql`
  mutation UpdateCorpusAction(
    $id: ID!
    $name: String
    $trigger: String
    $fieldsetId: ID
    $analyzerId: ID
    $agentConfigId: ID
    $taskInstructions: String
    $preAuthorizedTools: [String]
    $disabled: Boolean
    $runOnAllCorpuses: Boolean
  ) {
    updateCorpusAction(
      id: $id
      name: $name
      trigger: $trigger
      fieldsetId: $fieldsetId
      analyzerId: $analyzerId
      agentConfigId: $agentConfigId
      taskInstructions: $taskInstructions
      preAuthorizedTools: $preAuthorizedTools
      disabled: $disabled
      runOnAllCorpuses: $runOnAllCorpuses
    ) {
      ok
      message
      obj {
        id
        name
        trigger
        disabled
        runOnAllCorpuses
        fieldset {
          id
          name
        }
        analyzer {
          id
          description
        }
        agentConfig {
          id
          name
          description
        }
        taskInstructions
        preAuthorizedTools
      }
    }
  }
`;

export interface UpdateCorpusActionInput {
  id: string;
  name?: string;
  trigger?: string;
  fieldsetId?: string;
  analyzerId?: string;
  agentConfigId?: string;
  taskInstructions?: string;
  preAuthorizedTools?: string[];
  disabled?: boolean;
  runOnAllCorpuses?: boolean;
}

export interface UpdateCorpusActionOutput {
  updateCorpusAction: {
    ok: boolean;
    message: string;
    obj: CorpusActionType | null;
  };
}

export const RUN_CORPUS_ACTION = gql`
  mutation RunCorpusAction($corpusActionId: ID!, $documentId: ID!) {
    runCorpusAction(corpusActionId: $corpusActionId, documentId: $documentId) {
      ok
      message
      obj {
        id
        status
        actionType
        trigger
        queuedAt
        corpusAction {
          id
          name
        }
        document {
          id
          title
        }
      }
    }
  }
`;

export interface RunCorpusActionInput {
  corpusActionId: string;
  documentId: string;
}

export interface RunCorpusActionOutput {
  runCorpusAction: {
    ok: boolean;
    message: string;
    obj: {
      id: string;
      status: string;
      actionType: string;
      trigger: string;
      queuedAt: string;
      corpusAction: { id: string; name: string };
      document: { id: string; title: string };
    } | null;
  };
}

///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
/// BADGE-RELATED MUTATIONS
///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

export const CREATE_BADGE = gql`
  mutation CreateBadge(
    $name: String!
    $description: String!
    $icon: String!
    $badgeType: String!
    $color: String
    $corpusId: ID
    $isAutoAwarded: Boolean
    $criteriaConfig: JSONString
  ) {
    createBadge(
      name: $name
      description: $description
      icon: $icon
      badgeType: $badgeType
      color: $color
      corpusId: $corpusId
      isAutoAwarded: $isAutoAwarded
      criteriaConfig: $criteriaConfig
    ) {
      ok
      message
      badge {
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
      }
    }
  }
`;

export interface CreateBadgeInput {
  name: string;
  description: string;
  icon: string;
  badgeType: "GLOBAL" | "CORPUS";
  color?: string;
  corpusId?: string;
  isAutoAwarded?: boolean;
  criteriaConfig?: any;
}

export interface CreateBadgeOutput {
  createBadge: {
    ok: boolean;
    message: string;
    badge: {
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
    } | null;
  };
}

export const UPDATE_BADGE = gql`
  mutation UpdateBadge(
    $badgeId: ID!
    $name: String
    $description: String
    $icon: String
    $color: String
    $isAutoAwarded: Boolean
    $criteriaConfig: JSONString
  ) {
    updateBadge(
      badgeId: $badgeId
      name: $name
      description: $description
      icon: $icon
      color: $color
      isAutoAwarded: $isAutoAwarded
      criteriaConfig: $criteriaConfig
    ) {
      ok
      message
      badge {
        id
        name
        description
        icon
        color
        isAutoAwarded
        criteriaConfig
      }
    }
  }
`;

export interface UpdateBadgeInput {
  badgeId: string;
  name?: string;
  description?: string;
  icon?: string;
  color?: string;
  isAutoAwarded?: boolean;
  criteriaConfig?: any;
}

export interface UpdateBadgeOutput {
  updateBadge: {
    ok: boolean;
    message: string;
    badge: {
      id: string;
      name: string;
      description: string;
      icon: string;
      color: string;
      isAutoAwarded: boolean;
      criteriaConfig: any;
    } | null;
  };
}

export const DELETE_BADGE = gql`
  mutation DeleteBadge($badgeId: ID!) {
    deleteBadge(badgeId: $badgeId) {
      ok
      message
    }
  }
`;

export interface DeleteBadgeInput {
  badgeId: string;
}

export interface DeleteBadgeOutput {
  deleteBadge: {
    ok: boolean;
    message: string;
  };
}

export const AWARD_BADGE = gql`
  mutation AwardBadge($badgeId: ID!, $userId: ID!, $corpusId: ID) {
    awardBadge(badgeId: $badgeId, userId: $userId, corpusId: $corpusId) {
      ok
      message
      userBadge {
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
        }
        awardedBy {
          id
          username
        }
      }
    }
  }
`;

export interface AwardBadgeInput {
  badgeId: string;
  userId: string;
  corpusId?: string;
}

export interface AwardBadgeOutput {
  awardBadge: {
    ok: boolean;
    message: string;
    userBadge: {
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
      };
      awardedBy?: {
        id: string;
        username: string;
      };
    } | null;
  };
}

export const REVOKE_BADGE = gql`
  mutation RevokeBadge($userBadgeId: ID!) {
    revokeBadge(userBadgeId: $userBadgeId) {
      ok
      message
    }
  }
`;

export interface RevokeBadgeInput {
  userBadgeId: string;
}

export interface RevokeBadgeOutput {
  revokeBadge: {
    ok: boolean;
    message: string;
  };
}

// ============================================================================
// Thread and Message Mutations
// ============================================================================

export const CREATE_THREAD = gql`
  mutation CreateThread(
    $corpusId: String
    $documentId: String
    $title: String!
    $description: String
    $initialMessage: String!
  ) {
    createThread(
      corpusId: $corpusId
      documentId: $documentId
      title: $title
      description: $description
      initialMessage: $initialMessage
    ) {
      ok
      message
      obj {
        id
        title
        description
        chatWithDocument {
          id
          title
          slug
          creator {
            slug
          }
        }
        chatWithCorpus {
          id
          title
          slug
          creator {
            slug
          }
        }
      }
    }
  }
`;

export interface CreateThreadInput {
  corpusId?: string;
  documentId?: string;
  title: string;
  description?: string;
  initialMessage: string;
}

export interface CreateThreadOutput {
  createThread: {
    ok: boolean;
    message: string;
    obj?: {
      id: string;
      title: string;
      description?: string;
    };
  };
}

export const CREATE_THREAD_MESSAGE = gql`
  mutation CreateThreadMessage($conversationId: String!, $content: String!) {
    createThreadMessage(conversationId: $conversationId, content: $content) {
      ok
      message
      obj {
        id
        content
        created
        modified
        creator {
          id
          username
          email
        }
        conversation {
          id
          title
        }
        upvoteCount
        downvoteCount
        # userVote — backend field not yet exposed in the schema
      }
    }
  }
`;

export interface CreateThreadMessageInput {
  conversationId: string;
  content: string;
}

export interface CreateThreadMessageOutput {
  createThreadMessage: {
    ok: boolean;
    message: string;
    obj: {
      id: string;
      content: string;
      created: string;
      modified: string;
      creator: {
        id: string;
        username: string;
        email: string;
      };
      conversation: {
        id: string;
        title: string;
      };
      upvoteCount: number;
      downvoteCount: number;
      userVote?: string;
    } | null;
  };
}

export const REPLY_TO_MESSAGE = gql`
  mutation ReplyToMessage($parentMessageId: String!, $content: String!) {
    replyToMessage(parentMessageId: $parentMessageId, content: $content) {
      ok
      message
      obj {
        id
        content
        created
        modified
        creator {
          id
          username
          email
        }
        parentMessage {
          id
          content
          creator {
            id
            username
          }
        }
        conversation {
          id
          title
        }
        upvoteCount
        downvoteCount
        # userVote — backend field not yet exposed in the schema
      }
    }
  }
`;

export interface ReplyToMessageInput {
  parentMessageId: string;
  content: string;
}

export interface ReplyToMessageOutput {
  replyToMessage: {
    ok: boolean;
    message: string;
    obj: {
      id: string;
      content: string;
      created: string;
      modified: string;
      creator: {
        id: string;
        username: string;
        email: string;
      };
      parentMessage: {
        id: string;
        content: string;
        creator: {
          id: string;
          username: string;
        };
      } | null;
      conversation: {
        id: string;
        title: string;
      };
      upvoteCount: number;
      downvoteCount: number;
      userVote?: string;
    } | null;
  };
}

export const DELETE_CONVERSATION = gql`
  mutation DeleteConversation($conversationId: ID!) {
    deleteConversation(conversationId: $conversationId) {
      ok
      message
    }
  }
`;

export interface DeleteConversationInput {
  conversationId: string;
}

export interface DeleteConversationOutput {
  deleteConversation: {
    ok: boolean;
    message: string;
  };
}

export const DELETE_MESSAGE = gql`
  mutation DeleteMessage($messageId: ID!) {
    deleteMessage(messageId: $messageId) {
      ok
      message
    }
  }
`;

export interface DeleteMessageInput {
  messageId: string;
}

export interface DeleteMessageOutput {
  deleteMessage: {
    ok: boolean;
    message: string;
  };
}

/**
 * Update the content of an existing message.
 * Only the message creator or a moderator can edit messages.
 * Part of Issue #686 - Mobile UI for Edit Message Modal
 */
export const UPDATE_MESSAGE = gql`
  mutation UpdateMessage($messageId: ID!, $content: String!) {
    updateMessage(messageId: $messageId, content: $content) {
      ok
      message
      obj {
        id
        content
        modified
      }
    }
  }
`;

export interface UpdateMessageInput {
  messageId: string;
  content: string;
}

export interface UpdateMessageOutput {
  updateMessage: {
    ok: boolean;
    message: string;
    obj: {
      id: string;
      content: string;
      modified: string;
    } | null;
  };
}

// ============================================================================
// Voting Mutations
// ============================================================================

/**
 * Upvote a message. Uses the backend vote_message mutation with vote_type="upvote".
 * Returns the updated message with vote counts and current user's vote status.
 */
export const UPVOTE_MESSAGE = gql`
  mutation UpvoteMessage($messageId: ID!) {
    voteMessage(messageId: $messageId, voteType: "upvote") {
      ok
      message
      obj {
        id
        upvoteCount
        downvoteCount
        userVote
      }
    }
  }
`;

export interface UpvoteMessageInput {
  messageId: string;
}

/** Response shape for vote mutations (upvote uses voteMessage mutation) */
export interface VoteMessageResponse {
  ok: boolean;
  message: string;
  obj: {
    id: string;
    upvoteCount: number;
    downvoteCount: number;
    userVote: string | null;
  } | null;
}

export interface UpvoteMessageOutput {
  voteMessage: VoteMessageResponse;
}

/**
 * Downvote a message. Uses the backend vote_message mutation with vote_type="downvote".
 * Returns the updated message with vote counts and current user's vote status.
 */
export const DOWNVOTE_MESSAGE = gql`
  mutation DownvoteMessage($messageId: ID!) {
    voteMessage(messageId: $messageId, voteType: "downvote") {
      ok
      message
      obj {
        id
        upvoteCount
        downvoteCount
        userVote
      }
    }
  }
`;

export interface DownvoteMessageInput {
  messageId: string;
}

export interface DownvoteMessageOutput {
  voteMessage: VoteMessageResponse;
}

/**
 * Remove a vote from a message.
 * Returns the updated message with vote counts and current user's vote status (null after removal).
 */
export const REMOVE_VOTE = gql`
  mutation RemoveVote($messageId: ID!) {
    removeVote(messageId: $messageId) {
      ok
      message
      obj {
        id
        upvoteCount
        downvoteCount
        userVote
      }
    }
  }
`;

export interface RemoveVoteInput {
  messageId: string;
}

export interface RemoveVoteOutput {
  removeVote: VoteMessageResponse;
}

// ============================================================================
// Conversation/Thread Voting Mutations
// ============================================================================

/** Response shape for conversation vote mutations */
export interface VoteConversationResponse {
  ok: boolean;
  message: string;
  obj: {
    id: string;
    upvoteCount: number;
    downvoteCount: number;
    userVote: string | null;
  } | null;
}

/**
 * Upvote a conversation/thread. Uses the backend vote_conversation mutation with vote_type="upvote".
 * Returns the updated conversation with vote counts and current user's vote status.
 */
export const UPVOTE_CONVERSATION = gql`
  mutation UpvoteConversation($conversationId: String!) {
    voteConversation(conversationId: $conversationId, voteType: "upvote") {
      ok
      message
      obj {
        id
        upvoteCount
        downvoteCount
        userVote
      }
    }
  }
`;

export interface UpvoteConversationInput {
  conversationId: string;
}

export interface UpvoteConversationOutput {
  voteConversation: VoteConversationResponse;
}

/**
 * Downvote a conversation/thread. Uses the backend vote_conversation mutation with vote_type="downvote".
 * Returns the updated conversation with vote counts and current user's vote status.
 */
export const DOWNVOTE_CONVERSATION = gql`
  mutation DownvoteConversation($conversationId: String!) {
    voteConversation(conversationId: $conversationId, voteType: "downvote") {
      ok
      message
      obj {
        id
        upvoteCount
        downvoteCount
        userVote
      }
    }
  }
`;

export interface DownvoteConversationInput {
  conversationId: string;
}

export interface DownvoteConversationOutput {
  voteConversation: VoteConversationResponse;
}

/**
 * Remove a vote from a conversation/thread.
 * Returns the updated conversation with vote counts and current user's vote status (null after removal).
 */
export const REMOVE_CONVERSATION_VOTE = gql`
  mutation RemoveConversationVote($conversationId: String!) {
    removeConversationVote(conversationId: $conversationId) {
      ok
      message
      obj {
        id
        upvoteCount
        downvoteCount
        userVote
      }
    }
  }
`;

export interface RemoveConversationVoteInput {
  conversationId: string;
}

export interface RemoveConversationVoteOutput {
  removeConversationVote: VoteConversationResponse;
}

// ============================================================================
// Moderation Mutations
// ============================================================================

export const PIN_THREAD = gql`
  mutation PinThread($conversationId: ID!) {
    pinThread(conversationId: $conversationId) {
      ok
      message
      conversation {
        id
        isPinned
        pinnedBy {
          id
          username
        }
        pinnedAt
      }
    }
  }
`;

export interface PinThreadInput {
  conversationId: string;
}

export interface PinThreadOutput {
  pinThread: {
    ok: boolean;
    message: string;
    conversation: {
      id: string;
      isPinned: boolean;
      pinnedBy: {
        id: string;
        username: string;
      } | null;
      pinnedAt: string | null;
    } | null;
  };
}

export const UNPIN_THREAD = gql`
  mutation UnpinThread($conversationId: ID!) {
    unpinThread(conversationId: $conversationId) {
      ok
      message
      conversation {
        id
        isPinned
        pinnedBy {
          id
          username
        }
        pinnedAt
      }
    }
  }
`;

export interface UnpinThreadInput {
  conversationId: string;
}

export interface UnpinThreadOutput {
  unpinThread: {
    ok: boolean;
    message: string;
    conversation: {
      id: string;
      isPinned: boolean;
      pinnedBy: {
        id: string;
        username: string;
      } | null;
      pinnedAt: string | null;
    } | null;
  };
}

export const LOCK_THREAD = gql`
  mutation LockThread($conversationId: ID!) {
    lockThread(conversationId: $conversationId) {
      ok
      message
      conversation {
        id
        isLocked
        lockedBy {
          id
          username
        }
        lockedAt
      }
    }
  }
`;

export interface LockThreadInput {
  conversationId: string;
}

export interface LockThreadOutput {
  lockThread: {
    ok: boolean;
    message: string;
    conversation: {
      id: string;
      isLocked: boolean;
      lockedBy: {
        id: string;
        username: string;
      } | null;
      lockedAt: string | null;
    } | null;
  };
}

export const UNLOCK_THREAD = gql`
  mutation UnlockThread($conversationId: ID!) {
    unlockThread(conversationId: $conversationId) {
      ok
      message
      conversation {
        id
        isLocked
        lockedBy {
          id
          username
        }
        lockedAt
      }
    }
  }
`;

export interface UnlockThreadInput {
  conversationId: string;
}

export interface UnlockThreadOutput {
  unlockThread: {
    ok: boolean;
    message: string;
    conversation: {
      id: string;
      isLocked: boolean;
      lockedBy: {
        id: string;
        username: string;
      } | null;
      lockedAt: string | null;
    } | null;
  };
}

export const DELETE_THREAD = gql`
  mutation DeleteThread($conversationId: ID!) {
    deleteThread(conversationId: $conversationId) {
      ok
      message
      conversation {
        id
        isDeleted
        deletedBy {
          id
          username
        }
        deletedAt
      }
    }
  }
`;

export interface DeleteThreadInput {
  conversationId: string;
}

export interface DeleteThreadOutput {
  deleteThread: {
    ok: boolean;
    message: string;
    conversation: {
      id: string;
      isDeleted: boolean;
      deletedBy: {
        id: string;
        username: string;
      } | null;
      deletedAt: string | null;
    } | null;
  };
}

export const RESTORE_THREAD = gql`
  mutation RestoreThread($conversationId: ID!) {
    restoreThread(conversationId: $conversationId) {
      ok
      message
      conversation {
        id
        isDeleted
        deletedBy {
          id
          username
        }
        deletedAt
      }
    }
  }
`;

export interface RestoreThreadInput {
  conversationId: string;
}

export interface RestoreThreadOutput {
  restoreThread: {
    ok: boolean;
    message: string;
    conversation: {
      id: string;
      isDeleted: boolean;
      deletedBy: {
        id: string;
        username: string;
      } | null;
      deletedAt: string | null;
    } | null;
  };
}

/**
 * ============================================================================
 * NOTIFICATION MUTATIONS
 * ============================================================================
 */

export const MARK_NOTIFICATION_READ = gql`
  mutation MarkNotificationRead($notificationId: ID!) {
    markNotificationRead(notificationId: $notificationId) {
      ok
      message
      notification {
        id
        isRead
        modified
      }
    }
  }
`;

export interface MarkNotificationReadInput {
  notificationId: string;
}

export interface MarkNotificationReadOutput {
  markNotificationRead: {
    ok: boolean;
    message: string;
    notification: {
      id: string;
      isRead: boolean;
      modified: string;
    } | null;
  };
}

export const MARK_NOTIFICATION_UNREAD = gql`
  mutation MarkNotificationUnread($notificationId: ID!) {
    markNotificationUnread(notificationId: $notificationId) {
      ok
      message
      notification {
        id
        isRead
        modified
      }
    }
  }
`;

export interface MarkNotificationUnreadInput {
  notificationId: string;
}

export interface MarkNotificationUnreadOutput {
  markNotificationUnread: {
    ok: boolean;
    message: string;
    notification: {
      id: string;
      isRead: boolean;
      modified: string;
    } | null;
  };
}

export const MARK_ALL_NOTIFICATIONS_READ = gql`
  mutation MarkAllNotificationsRead {
    markAllNotificationsRead {
      ok
      message
      count
    }
  }
`;

export interface MarkAllNotificationsReadOutput {
  markAllNotificationsRead: {
    ok: boolean;
    message: string;
    count: number;
  };
}

export const DELETE_NOTIFICATION = gql`
  mutation DeleteNotification($notificationId: ID!) {
    deleteNotification(notificationId: $notificationId) {
      ok
      message
    }
  }
`;

export interface DeleteNotificationInput {
  notificationId: string;
}

export interface DeleteNotificationOutput {
  deleteNotification: {
    ok: boolean;
    message: string;
  };
}

///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
///
/// DOCUMENT VERSIONING MUTATIONS
///
///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

export const RESTORE_DELETED_DOCUMENT = gql`
  mutation RestoreDeletedDocument($documentId: ID!, $corpusId: ID!) {
    restoreDeletedDocument(documentId: $documentId, corpusId: $corpusId) {
      ok
      message
      document {
        id
        title
      }
    }
  }
`;

export interface RestoreDeletedDocumentInput {
  documentId: string;
  corpusId: string;
}

export interface RestoreDeletedDocumentOutput {
  restoreDeletedDocument: {
    ok: boolean;
    message: string;
    document: {
      id: string;
      title: string;
    } | null;
  };
}

export const PERMANENTLY_DELETE_DOCUMENT = gql`
  mutation PermanentlyDeleteDocument($documentId: String!, $corpusId: String!) {
    permanentlyDeleteDocument(documentId: $documentId, corpusId: $corpusId) {
      ok
      message
    }
  }
`;

export interface PermanentlyDeleteDocumentInput {
  documentId: string;
  corpusId: string;
}

export interface PermanentlyDeleteDocumentOutput {
  permanentlyDeleteDocument: {
    ok: boolean;
    message: string;
  };
}

export const EMPTY_TRASH = gql`
  mutation EmptyTrash($corpusId: String!) {
    emptyTrash(corpusId: $corpusId) {
      ok
      message
      deletedCount
    }
  }
`;

export interface EmptyTrashInput {
  corpusId: string;
}

export interface EmptyTrashOutput {
  emptyTrash: {
    ok: boolean;
    message: string;
    deletedCount: number;
  };
}

// ============================================================================
// MODERATION MUTATIONS
// ============================================================================

export const ROLLBACK_MODERATION_ACTION = gql`
  mutation RollbackModerationAction($actionId: ID!, $reason: String) {
    rollbackModerationAction(actionId: $actionId, reason: $reason) {
      ok
      message
      rollbackAction {
        id
        actionType
        created
        moderator {
          id
          username
        }
      }
    }
  }
`;

export interface RollbackModerationActionInput {
  actionId: string;
  reason?: string;
}

export interface RollbackModerationActionOutput {
  rollbackModerationAction: {
    ok: boolean;
    message: string;
    rollbackAction: {
      id: string;
      actionType: string;
      created: string;
      moderator: {
        id: string;
        username: string;
      } | null;
    } | null;
  };
}

// ============================================================================
// DOCUMENT RELATIONSHIP MUTATIONS
// ============================================================================

export interface CreateDocumentRelationshipInputs {
  sourceDocumentId: string;
  targetDocumentId: string;
  relationshipType: string; // "RELATIONSHIP" | "NOTES"
  corpusId: string;
  annotationLabelId?: string;
  data?: Record<string, any>;
}

export interface CreateDocumentRelationshipOutputs {
  createDocumentRelationship: {
    ok: boolean;
    message: string;
    documentRelationship: {
      id: string;
      relationshipType: string;
      data?: Record<string, any>;
      sourceDocument: {
        id: string;
        title: string;
        icon?: string;
      };
      targetDocument: {
        id: string;
        title: string;
        icon?: string;
      };
      annotationLabel?: {
        id: string;
        text: string;
        color: string;
        icon?: string;
      };
      corpus: {
        id: string;
      };
      creator: {
        id: string;
        username: string;
      };
      created: string;
      myPermissions?: string[];
    } | null;
  };
}

export const CREATE_DOCUMENT_RELATIONSHIP = gql`
  mutation CreateDocumentRelationship(
    $sourceDocumentId: String!
    $targetDocumentId: String!
    $relationshipType: String!
    $corpusId: String!
    $annotationLabelId: String
    $data: GenericScalar
  ) {
    createDocumentRelationship(
      sourceDocumentId: $sourceDocumentId
      targetDocumentId: $targetDocumentId
      relationshipType: $relationshipType
      corpusId: $corpusId
      annotationLabelId: $annotationLabelId
      data: $data
    ) {
      ok
      message
      documentRelationship {
        id
        relationshipType
        data
        sourceDocument {
          id
          title
          icon
        }
        targetDocument {
          id
          title
          icon
        }
        annotationLabel {
          id
          text
          color
          icon
        }
        corpus {
          id
        }
        creator {
          id
          username
        }
        created
        myPermissions
      }
    }
  }
`;

export interface UpdateDocumentRelationshipInputs {
  documentRelationshipId: string;
  relationshipType?: string;
  annotationLabelId?: string;
  data?: Record<string, any>;
}

export interface UpdateDocumentRelationshipOutputs {
  updateDocumentRelationship: {
    ok: boolean;
    message: string;
    documentRelationship: {
      id: string;
      relationshipType: string;
      data?: Record<string, any>;
      annotationLabel?: {
        id: string;
        text: string;
        color: string;
        icon?: string;
      };
      modified: string;
      myPermissions?: string[];
    } | null;
  };
}

export const UPDATE_DOCUMENT_RELATIONSHIP = gql`
  mutation UpdateDocumentRelationship(
    $documentRelationshipId: String!
    $relationshipType: String
    $annotationLabelId: String
    $data: GenericScalar
  ) {
    updateDocumentRelationship(
      documentRelationshipId: $documentRelationshipId
      relationshipType: $relationshipType
      annotationLabelId: $annotationLabelId
      data: $data
    ) {
      ok
      message
      documentRelationship {
        id
        relationshipType
        data
        annotationLabel {
          id
          text
          color
          icon
        }
        modified
        myPermissions
      }
    }
  }
`;

export interface DeleteDocumentRelationshipInputs {
  documentRelationshipId: string;
}

export interface DeleteDocumentRelationshipOutputs {
  deleteDocumentRelationship: {
    ok: boolean;
    message: string;
  };
}

export const DELETE_DOCUMENT_RELATIONSHIP = gql`
  mutation DeleteDocumentRelationship($documentRelationshipId: String!) {
    deleteDocumentRelationship(
      documentRelationshipId: $documentRelationshipId
    ) {
      ok
      message
    }
  }
`;

export interface DeleteDocumentRelationshipsInputs {
  documentRelationshipIds: string[];
}

export interface DeleteDocumentRelationshipsOutputs {
  deleteDocumentRelationships: {
    ok: boolean;
    message: string;
    deletedCount: number;
  };
}

export const DELETE_DOCUMENT_RELATIONSHIPS = gql`
  mutation DeleteDocumentRelationships($documentRelationshipIds: [String!]!) {
    deleteDocumentRelationships(
      documentRelationshipIds: $documentRelationshipIds
    ) {
      ok
      message
      deletedCount
    }
  }
`;

///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
/// ZIP IMPORT MUTATION - Imports zip file with folder structure preserved
///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

export interface ImportZipToCorpusInputs {
  base64FileString: string;
  corpusId: string;
  targetFolderId?: string;
  titlePrefix?: string;
  description?: string;
  customMeta?: Record<string, any>;
  makePublic: boolean;
}

export interface ImportZipToCorpusOutputs {
  importZipToCorpus: {
    ok: boolean;
    message: string;
    jobId?: string;
  };
}

export const IMPORT_ZIP_TO_CORPUS = gql`
  mutation ImportZipToCorpus(
    $base64FileString: String!
    $corpusId: ID!
    $targetFolderId: ID
    $titlePrefix: String
    $description: String
    $customMeta: GenericScalar
    $makePublic: Boolean!
  ) {
    importZipToCorpus(
      base64FileString: $base64FileString
      corpusId: $corpusId
      targetFolderId: $targetFolderId
      titlePrefix: $titlePrefix
      description: $description
      customMeta: $customMeta
      makePublic: $makePublic
    ) {
      ok
      message
      jobId
    }
  }
`;
