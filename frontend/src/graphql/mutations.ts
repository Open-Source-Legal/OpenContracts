import { gql } from "@apollo/client";
import { SemanticICONS } from "semantic-ui-react/dist/commonjs/generic";
import { ExportTypes, MultipageAnnotationJson } from "../components/types";
import {
  AnalysisType,
  AnnotationLabelType,
  ColumnType,
  CorpusQueryType,
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
  ) {
    updateCorpus(
      id: $id
      icon: $icon
      description: $description
      labelSet: $labelSet
      title: $title
      preferredEmbedder: $preferredEmbedder
    ) {
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
  ) {
    createCorpus(
      description: $description
      icon: $icon
      labelSet: $labelSet
      title: $title
      preferredEmbedder: $preferredEmbedder
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
  ok?: boolean;
  message?: string;
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
  ok?: boolean;
  message?: string;
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
  labelIdsToDelete: string[];
}

export interface DeleteMultipleAnnotationLabelOutputs {
  ok?: boolean;
  message?: string;
}

export const DELETE_MULTIPLE_ANNOTATION_LABELS = gql`
  mutation ($labelIdsToDelete: [String]!) {
    deleteMultipleLabels(labelIdsToDelete: $labelIdsToDelete) {
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
  ok?: boolean;
  message?: string;
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
}

export interface UploadDocumentOutputProps {
  uploadDocument: {
    document: {
      id: string;
      icon: string;
      pdfFile: string;
      title: string;
      description: string;
      backendLock: boolean;
      docAnnotations: {
        edges: {
          node: {
            id: string;
          };
        };
      }[];
    };
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
    ) {
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
  ) {
    updateDocument(
      id: $id
      pdfFile: $pdfFile
      customMeta: $customMeta
      description: $description
      title: $title
    ) {
      ok
      message
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

export interface AskQueryOfCorpusInputType {
  corpusId: string;
  query: string;
}

export interface AskQueryOfCorpusOutputType {
  askQuery: {
    ok: boolean;
    message: string;
    obj: CorpusQueryType;
  };
}

export const ASK_QUERY_OF_CORPUS = gql`
  mutation AskQuery($corpusId: String!, $query: String!) {
    askQuery(corpusId: $corpusId, query: $query) {
      ok
      message
      obj {
        id
        query
        response
        started
        completed
        failed
        stacktrace
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
    $disabled: Boolean
    $runOnAllCorpuses: Boolean
  ) {
    createCorpusAction(
      corpusId: $corpusId
      trigger: $trigger
      name: $name
      fieldsetId: $fieldsetId
      analyzerId: $analyzerId
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
      }
    }
  }
`;

export interface CreateCorpusActionInput {
  corpusId: string;
  trigger: "add_document" | "edit_document";
  name?: string;
  fieldsetId?: string;
  analyzerId?: string;
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
