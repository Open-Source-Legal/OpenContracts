import {
  ExportTypes,
  MultipageAnnotationJson,
  PermissionTypes,
  SpanAnnotationJson,
  TokenId,
} from "../components/types";
import { JSONSchema7 } from "json-schema";
import { WebSocketSources } from "../components/chat/types";

export type Maybe<T> = T | null;
export type InputMaybe<T> = Maybe<T>;
export type Exact<T extends { [key: string]: unknown }> = {
  [K in keyof T]: T[K];
};
export type MakeOptional<T, K extends keyof T> = Omit<T, K> & {
  [SubKey in K]?: Maybe<T[SubKey]>;
};
export type MakeMaybe<T, K extends keyof T> = Omit<T, K> & {
  [SubKey in K]: Maybe<T[SubKey]>;
};

/** Auto-generated built-in and custom scalars, mapped to their actual values, for GraphQL API */
export type Scalars = {
  ID: string;
  String: string;
  Boolean: boolean;
  Int: number;
  Float: number;
  DateTime: any;
  GenericScalar: any;
  JSONString: any;
  UUID: any;
};

export enum DocumentProcessingStatus {
  PENDING = "PENDING",
  PROCESSING = "PROCESSING",
  COMPLETED = "COMPLETED",
  FAILED = "FAILED",
}

export type AddAnnotation = {
  __typename?: "AddAnnotation";
  ok?: Maybe<Scalars["Boolean"]>;
  annotation?: Maybe<ServerAnnotationType>;
};

export type AddDocTypeAnnotation = {
  __typename?: "AddDocTypeAnnotation";
  ok?: Maybe<Scalars["Boolean"]>;
  annotation?: Maybe<ServerAnnotationType>;
};

export type AddRelationship = {
  __typename?: "AddRelationship";
  ok?: Maybe<Scalars["Boolean"]>;
  relationship?: Maybe<RelationshipType>;
};

export type AnnotationLabelType = Node & {
  __typename?: "AnnotationLabelType";
  id: Scalars["ID"];
  labelType?: LabelType;
  analyzer?: Maybe<AnalyzerType>;
  color?: Scalars["String"];
  description?: Scalars["String"];
  icon?: string;
  text?: Scalars["String"];
  creator?: UserType;
  needed_by_analyzer_id?: Scalars["String"];
  used_by_analyses?: AnalysisTypeConnection;
  created?: Scalars["DateTime"];
  modified?: Scalars["DateTime"];
  isPublic?: Scalars["Boolean"];
  readonly?: Scalars["Boolean"];
  myPermissions?: PermissionTypes[];
  relationshipSet?: RelationshipTypeConnection;
  annotationSet?: AnnotationTypeConnection;
  labelsetSet?: LabelSetTypeConnection;
};

export type AnnotationLabelTypeRelationshipSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type AnnotationLabelTypeAnnotationSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type AnnotationLabelTypeLabelsetSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type AnnotationLabelTypeConnection = {
  __typename?: "AnnotationLabelTypeConnection";
  pageInfo: PageInfo;
  edges: Array<Maybe<AnnotationLabelTypeEdge>>;
  totalCount?: Maybe<Scalars["Int"]>;
};

export type AnnotationLabelTypeEdge = {
  __typename?: "AnnotationLabelTypeEdge";
  node?: Maybe<AnnotationLabelType>;
  cursor: Scalars["String"];
};

/* -------------------------------------------------
 *  Annotation types – raw vs typed
 * ------------------------------------------------- */

/**
 * GraphQL returns `myPermissions` as an array of raw strings.
 * We keep that shape in `RawServerAnnotationType` and convert
 * to the typed enum in `ServerAnnotationType`, just like we do
 * for documents (`RawDocumentType` ⇢ `DocumentType`).
 */
export type RawServerAnnotationType = Node & {
  __typename?: "AnnotationType";
  id: Scalars["ID"];
  parent?: Maybe<ServerAnnotationType>; // keep typed reference
  page: Scalars["Int"];
  annotationType?: LabelType;
  userFeedback?: FeedbackTypeConnection;
  created_by_analyses?: AnalysisTypeConnection;
  rawText?: Maybe<Scalars["String"]>;
  json?: MultipageAnnotationJson | SpanAnnotationJson;
  annotationLabel: AnnotationLabelType;
  document?: DocumentType;
  structural?: boolean;
  corpus?: Maybe<CorpusType>;
  creator?: UserType;
  created?: Scalars["DateTime"];
  modified?: Scalars["DateTime"];
  isPublic?: Scalars["Boolean"];

  /** Raw permission strings straight from the API */
  myPermissions?: string[];

  /** Content modalities present in this annotation: TEXT, IMAGE, etc. */
  contentModalities?: string[];

  analysis?: Maybe<AnalysisType>;
  corpusAction?: Maybe<CorpusActionType>;
  assignmentSet?: AssignmentTypeConnection;
  sourceNodeInRelationships?: RelationshipTypeConnection;
  targetNodeInRelationships?: RelationshipTypeConnection;
  chatMessages?: ChatMessageTypeConnection;
  createdByChatMessage?: ChatMessageTypeConnection;
};

/**
 * Application-level annotation object with enum-based permissions.
 */
export type ServerAnnotationType = Omit<
  RawServerAnnotationType,
  "myPermissions"
> & {
  /** Type-safe permissions list */
  myPermissions?: PermissionTypes[];
};

export type AnnotationTypeAssignmentSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type AnnotationTypeSourceNodeInRelationshipsArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type AnnotationTypeTargetNodeInRelationshipsArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type AnnotationTypeConnection = {
  __typename?: "AnnotationTypeConnection";
  pageInfo: PageInfo;
  edges: Array<Maybe<AnnotationTypeEdge>>;
  totalCount?: Maybe<Scalars["Int"]>;
};

export type AnnotationTypeEdge = {
  __typename?: "AnnotationTypeEdge";
  node?: Maybe<ServerAnnotationType>;
  cursor: Scalars["String"];
};

export type AssignmentType = Node & {
  __typename?: "AssignmentType";
  id: Scalars["ID"];
  name?: Maybe<Scalars["String"]>;
  document: DocumentType;
  corpus?: Maybe<CorpusType>;
  resultingAnnotations: AnnotationTypeConnection;
  resultingRelationships: RelationshipTypeConnection;
  comments: Scalars["String"];
  assignor: UserType;
  assignee?: Maybe<UserType>;
  completedAt?: Maybe<Scalars["DateTime"]>;
  created: Scalars["DateTime"];
  modified: Scalars["DateTime"];
  isPublic?: Scalars["Boolean"];
  myPermissions?: PermissionTypes[];
};

export type AssignmentTypeResultingAnnotationsArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type AssignmentTypeResultingRelationshipsArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type AssignmentTypeConnection = {
  __typename?: "AssignmentTypeConnection";
  pageInfo: PageInfo;
  edges: Array<Maybe<AssignmentTypeEdge>>;
  totalCount?: Maybe<Scalars["Int"]>;
};

export type AssignmentTypeEdge = {
  __typename?: "AssignmentTypeEdge";
  node?: Maybe<AssignmentType>;
  cursor: Scalars["String"];
};

// Corpus Category Types
export type CorpusCategoryType = Node & {
  __typename?: "CorpusCategoryType";
  id: Scalars["ID"];
  name: Scalars["String"];
  description?: Maybe<Scalars["String"]>;
  icon?: Maybe<Scalars["String"]>;
  color?: Maybe<Scalars["String"]>;
  sortOrder?: Maybe<Scalars["Int"]>;
  corpusCount?: Maybe<Scalars["Int"]>;
  isPublic?: Scalars["Boolean"];
  created?: Scalars["DateTime"];
  modified?: Scalars["DateTime"];
};

export type CorpusCategoryTypeConnection = {
  __typename?: "CorpusCategoryTypeConnection";
  pageInfo: PageInfo;
  edges: Array<Maybe<CorpusCategoryTypeEdge>>;
  totalCount?: Maybe<Scalars["Int"]>;
};

export type CorpusCategoryTypeEdge = {
  __typename?: "CorpusCategoryTypeEdge";
  node?: Maybe<CorpusCategoryType>;
  cursor: Scalars["String"];
};

export type RawCorpusType = Node & {
  __typename?: "CorpusType";
  id: Scalars["ID"];
  slug?: Scalars["String"];
  title?: Scalars["String"];
  allowComments?: boolean;
  appliedAnalyzerIds?: string[];
  is_selected?: boolean;
  is_opened?: boolean;
  description?: Scalars["String"];
  mdDescription?: Maybe<Scalars["String"]>;
  icon?: Maybe<Scalars["String"]>;
  documents?: DocumentTypeConnection;
  documentCount?: Scalars["Int"];
  annotationCount?: Scalars["Int"];
  labelSet?: Maybe<LabelSetType>;
  preferredEmbedder?: Maybe<Scalars["String"]>;
  creator?: UserType;
  parent?: CorpusType;
  backendLock?: Scalars["Boolean"];
  userLock?: Maybe<UserType>;
  error?: Scalars["Boolean"];
  created?: Scalars["DateTime"];
  modified?: Scalars["DateTime"];
  assignmentSet?: AssignmentTypeConnection;
  relationshipSet?: RelationshipTypeConnection;
  annotations?: AnnotationTypeConnection;
  allAnnotationSummaries?: ServerAnnotationType[];
  analyses: AnalysisTypeConnection;
  isPublic?: Scalars["Boolean"];
  isPersonal?: Scalars["Boolean"];
  myPermissions?: string[];
  conversations?: ConversationTypeConnection;
  // Note: categories is returned as a List (array), not a Connection, from the backend
  categories?: CorpusCategoryType[];
  license?: Maybe<Scalars["String"]>;
  licenseLink?: Maybe<Scalars["String"]>;
};

export type CorpusType = Omit<RawCorpusType, "myPermissions"> & {
  myPermissions?: PermissionTypes[];
};

export type CorpusTypeDocumentsArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type CorpusTypeAssignmentSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type CorpusTypeRelationshipSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type CorpusTypeAnnotationSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type CorpusTypeConnection = {
  __typename?: "CorpusTypeConnection";
  pageInfo: PageInfo;
  edges: Array<Maybe<CorpusTypeEdge>>;
  totalCount?: Maybe<Scalars["Int"]>;
};

export type CorpusTypeEdge = {
  __typename?: "CorpusTypeEdge";
  node?: Maybe<RawCorpusType>;
  cursor: Scalars["String"];
};

export type RawDocumentType = Node & {
  __typename?: "DocumentType";
  id: Scalars["ID"];
  slug?: Scalars["String"];
  title?: Maybe<Scalars["String"]>;
  description?: Maybe<Scalars["String"]>;
  customMeta?: Maybe<Scalars["JSONString"]>;
  icon?: Scalars["String"];
  pdfFile?: Scalars["String"];
  pdfFileHash?: Maybe<Scalars["String"]>;
  mdSummaryFile?: Scalars["String"];
  is_open?: boolean;
  is_selected?: boolean;
  pageCount?: Maybe<Scalars["Int"]>;
  txtExtractFile?: Maybe<Scalars["String"]>;
  pawlsParseFile?: Maybe<Scalars["String"]>;
  backendLock?: Scalars["Boolean"];
  fileType?: Scalars["String"];
  userLock?: Maybe<UserType>;
  creator?: UserType;
  created?: Scalars["DateTime"];
  modified?: Scalars["DateTime"];
  assignmentSet?: AssignmentTypeConnection;
  pathRecords?: DocumentPathTypeConnection;
  annotationSet?: AnnotationTypeConnection;
  isPublic?: Scalars["Boolean"];
  myPermissions?: string[];
  allAnnotations?: RawServerAnnotationType[];
  allRelationships?: RelationshipType[];
  allDocRelationships?: DocumentRelationshipType[];
  docRelationshipCount?: Maybe<Scalars["Int"]>;
  allStructuralAnnotations?: RawServerAnnotationType[];
  docLabelAnnotations?: Maybe<AnnotationTypeConnection>;
  metadataAnnotations?: Maybe<AnnotationTypeConnection>;
  conversations?: ConversationTypeConnection;
  chatMessages?: ChatMessageTypeConnection;
  allNotes?: NoteType[];
  // Version metadata fields
  hasVersionHistory?: Maybe<Scalars["Boolean"]>;
  versionCount?: Maybe<Scalars["Int"]>;
  isLatestVersion?: Maybe<Scalars["Boolean"]>;
  canViewHistory?: Maybe<Scalars["Boolean"]>;
  canRestore?: Maybe<Scalars["Boolean"]>;
  versionNumber?: Maybe<Scalars["Int"]>;
  lastModified?: Maybe<Scalars["DateTime"]>;
  // Processing status fields
  processingStatus?: Maybe<DocumentProcessingStatus>;
  processingError?: Maybe<Scalars["String"]>;
  canRetry?: Maybe<Scalars["Boolean"]>;
};

export type DocumentType = Omit<RawDocumentType, "myPermissions"> & {
  myPermissions?: PermissionTypes[];
};

export type DocumentTypeAssignmentSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type DocumentTypeCorpusSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type DocumentTypeAnnotationSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type DocumentTypeConnection = {
  __typename?: "DocumentTypeConnection";
  pageInfo: PageInfo;
  edges: Array<Maybe<DocumentTypeEdge>>;
  totalCount?: Maybe<Scalars["Int"]>;
};

export type DocumentTypeEdge = {
  __typename?: "DocumentTypeEdge";
  node?: Maybe<DocumentType>;
  cursor: Scalars["String"];
};

export type DocumentPathType = Node & {
  __typename?: "DocumentPathType";
  id: Scalars["ID"];
  corpus?: RawCorpusType;
  path?: Maybe<Scalars["String"]>;
  versionNumber?: Maybe<Scalars["Int"]>;
  isCurrent?: Scalars["Boolean"];
  isDeleted?: Scalars["Boolean"];
};

export type DocumentPathTypeConnection = {
  __typename?: "DocumentPathTypeConnection";
  pageInfo: PageInfo;
  edges: Array<Maybe<DocumentPathTypeEdge>>;
  totalCount?: Maybe<Scalars["Int"]>;
};

export type DocumentPathTypeEdge = {
  __typename?: "DocumentPathTypeEdge";
  node?: Maybe<DocumentPathType>;
  cursor: Scalars["String"];
};

export type LabelSetType = Node & {
  __typename?: "LabelSetType";
  id?: Scalars["ID"];
  used_by_analyzer_id?: Scalars["String"];
  title?: Scalars["String"];
  description?: Scalars["String"];
  icon?: Scalars["String"];
  annotationLabels?: AnnotationLabelTypeConnection;
  allAnnotationLabels?: AnnotationLabelType[];
  docLabelCount?: Scalars["Int"];
  spanLabelCount?: Scalars["Int"];
  tokenLabelCount?: Scalars["Int"];
  corpusCount?: Scalars["Int"];
  creator?: UserType;
  created?: Scalars["DateTime"];
  modified?: Scalars["DateTime"];
  corpusSet?: CorpusTypeConnection;
  isPublic?: Scalars["Boolean"];
  isDefault?: Scalars["Boolean"];
  myPermissions?: PermissionTypes[];
};

export type LabelSetTypeLabelsArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
  type?: InputMaybe<Scalars["String"]>;
};

export type LabelSetTypeCorpusSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type LabelSetTypeConnection = {
  __typename?: "LabelSetTypeConnection";
  pageInfo: PageInfo;
  edges: Array<Maybe<LabelSetTypeEdge>>;
  totalCount?: Maybe<Scalars["Int"]>;
};

export type LabelSetTypeEdge = {
  __typename?: "LabelSetTypeEdge";
  node?: Maybe<LabelSetType>;
  cursor: Scalars["String"];
};

export enum LabelType {
  RelationshipLabel = "RELATIONSHIP_LABEL",
  DocTypeLabel = "DOC_TYPE_LABEL",
  TokenLabel = "TOKEN_LABEL",
  SpanLabel = "SPAN_LABEL",
}

export enum AnnotationTypeEnum {
  HUMAN_ANNOTATION = "HUMAN_ANNOTATION",
  MACHINE_ANNOTATION = "MACHINE_ANNOTATION",
}

export enum LabelDisplayBehavior {
  ALWAYS = "ALWAYS",
  ON_HOVER = "ON_HOVER",
  HIDE = "HIDE",
}

export type Mutation = {
  __typename?: "Mutation";
  tokenAuth?: Maybe<ObtainJsonWebToken>;
  verifyToken?: Maybe<Verify>;
  refreshToken?: Maybe<Refresh>;
  addAnnotation?: Maybe<AddAnnotation>;
  removeAnnotation?: Maybe<RemoveAnnotation>;
  addRelationship?: Maybe<AddRelationship>;
  removeRelationship?: Maybe<RemoveRelationship>;
  removeRelationships?: Maybe<RemoveRelationships>;
  addDocTypeAnnotation?: Maybe<AddDocTypeAnnotation>;
  removeDocTypeAnnotation?: Maybe<RemoveAnnotation>;
  updateRelationships?: Maybe<UpdateRelations>;
};

export type MutationTokenAuthArgs = {
  username: Scalars["String"];
  password: Scalars["String"];
};

export type MutationVerifyTokenArgs = {
  token?: InputMaybe<Scalars["String"]>;
};

export type MutationRefreshTokenArgs = {
  refreshToken?: InputMaybe<Scalars["String"]>;
};

export interface TextSearchResultsProps {
  start: TokenId;
  end: TokenId;
}

export type MutationAddAnnotationArgs = {
  json: Scalars["GenericScalar"];
  corpusId: Scalars["String"];
  documentId: Scalars["String"];
  annotationLabelId: Scalars["String"];
  annotationType: LabelType;
  page: Scalars["Int"];
  rawText: Scalars["String"];
};

export type MutationRemoveAnnotationArgs = {
  annotationId: Scalars["String"];
};

export type MutationAddRelationshipArgs = {
  corpusId: Scalars["String"];
  labelId: Scalars["String"];
  sourceIds: Array<InputMaybe<Scalars["String"]>>;
  targetIds: Array<InputMaybe<Scalars["String"]>>;
};

export type MutationRemoveRelationshipArgs = {
  relationshipId: Scalars["String"];
};

export type MutationRemoveRelationshipsArgs = {
  relationshipIds?: InputMaybe<Array<InputMaybe<Scalars["String"]>>>;
};

export type MutationAddDocTypeAnnotationArgs = {
  corpusId: Scalars["String"];
  documentId: Scalars["String"];
  labelId: Scalars["String"];
};

export type MutationRemoveDocTypeAnnotationArgs = {
  annotationId: Scalars["String"];
};

export type MutationUpdateRelationshipsArgs = {
  relationships?: InputMaybe<Array<InputMaybe<RelationInputType>>>;
};

export type Node = {
  id: Scalars["ID"];
};

export type ObtainJsonWebToken = {
  __typename?: "ObtainJSONWebToken";
  payload: Scalars["GenericScalar"];
  refreshExpiresIn: Scalars["Int"];
  token: Scalars["String"];
  refreshToken: Scalars["String"];
};

export type PageInfo = {
  __typename?: "PageInfo";
  hasNextPage: Scalars["Boolean"];
  hasPreviousPage: Scalars["Boolean"];
  startCursor?: Maybe<Scalars["String"]>;
  endCursor?: Maybe<Scalars["String"]>;
};

export type Query = {
  __typename?: "Query";
  annotations?: Maybe<AnnotationTypeConnection>;
  annotation?: Maybe<ServerAnnotationType>;
  relationships?: Maybe<RelationshipTypeConnection>;
  relationship?: Maybe<RelationshipType>;
  assignments?: Maybe<AssignmentTypeConnection>;
  assignment?: Maybe<AssignmentType>;
  labels?: Maybe<AnnotationLabelTypeConnection>;
  label?: Maybe<AnnotationLabelType>;
  labelsets?: Maybe<LabelSetTypeConnection>;
  labelset?: Maybe<LabelSetType>;
  corpuses?: Maybe<CorpusTypeConnection>;
  corpus?: Maybe<CorpusType>;
  documents?: Maybe<DocumentTypeConnection>;
  document?: Maybe<DocumentType>;
  userimports?: Maybe<UserImportTypeConnection>;
  userimport?: Maybe<UserImportType>;
  userexports?: Maybe<UserExportTypeConnection>;
  userexport?: Maybe<UserExportType>;
};

export type QueryAnnotationsArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type QueryAnnotationArgs = {
  id: Scalars["ID"];
};

export type QueryRelationshipsArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type QueryRelationshipArgs = {
  id: Scalars["ID"];
};

export type QueryAssignmentsArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
  assignor_Email?: InputMaybe<Scalars["String"]>;
  assignee_Email?: InputMaybe<Scalars["String"]>;
  documentId?: InputMaybe<Scalars["String"]>;
};

export type QueryAssignmentArgs = {
  id: Scalars["ID"];
};

export type QueryLabelsArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
  type?: InputMaybe<Scalars["String"]>;
};

export type QueryLabelArgs = {
  id: Scalars["ID"];
};

export type QueryLabelsetsArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type QueryLabelsetArgs = {
  id: Scalars["ID"];
};

export type QueryCorpusesArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type QueryCorpusArgs = {
  id: Scalars["ID"];
};

export type QueryDocumentsArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type QueryDocumentArgs = {
  id: Scalars["ID"];
};

export type QueryUserimportsArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type QueryUserimportArgs = {
  id: Scalars["ID"];
};

export type QueryUserexportsArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type QueryUserexportArgs = {
  id: Scalars["ID"];
};

export type Refresh = {
  __typename?: "Refresh";
  payload: Scalars["GenericScalar"];
  refreshExpiresIn: Scalars["Int"];
  token: Scalars["String"];
  refreshToken: Scalars["String"];
};

export type RelationInputType = {
  id?: InputMaybe<Scalars["String"]>;
  sourceIds?: InputMaybe<Array<InputMaybe<Scalars["String"]>>>;
  targetIds?: InputMaybe<Array<InputMaybe<Scalars["String"]>>>;
  labelId?: InputMaybe<Scalars["String"]>;
  corpusId?: InputMaybe<Scalars["String"]>;
  documentId?: InputMaybe<Scalars["String"]>;
};

export type RelationshipType = Node & {
  __typename?: "RelationshipType";
  id: Scalars["ID"];
  relationshipLabel: AnnotationLabelType;
  corpus: CorpusType;
  document: DocumentType;
  sourceAnnotations: AnnotationTypeConnection;
  targetAnnotations: AnnotationTypeConnection;
  creator: UserType;
  created: Scalars["DateTime"];
  modified: Scalars["DateTime"];
  assignmentSet: AssignmentTypeConnection;
  isPublic?: Scalars["Boolean"];
  myPermissions?: PermissionTypes[];
  structural?: Scalars["Boolean"];
};

export type RelationshipTypeSourceAnnotationsArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type RelationshipTypeTargetAnnotationsArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type RelationshipTypeAssignmentSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type RelationshipTypeConnection = {
  __typename?: "RelationshipTypeConnection";
  pageInfo: PageInfo;
  edges: Array<Maybe<RelationshipTypeEdge>>;
  totalCount?: Maybe<Scalars["Int"]>;
};

export type RelationshipTypeEdge = {
  __typename?: "RelationshipTypeEdge";
  node: RelationshipType;
  cursor: Scalars["String"];
};

export type RemoveAnnotation = {
  __typename?: "RemoveAnnotation";
  ok?: Maybe<Scalars["Boolean"]>;
};

export type RemoveRelationship = {
  __typename?: "RemoveRelationship";
  ok?: Maybe<Scalars["Boolean"]>;
};

export type RemoveRelationships = {
  __typename?: "RemoveRelationships";
  ok?: Maybe<Scalars["Boolean"]>;
};

export type UpdateRelations = {
  __typename?: "UpdateRelations";
  ok?: Maybe<Scalars["Boolean"]>;
};

export type UserExportType = Node & {
  __typename?: "UserExportType";
  id: Scalars["ID"];
  file: Scalars["String"];
  backendLock?: Scalars["Boolean"];
  name?: Maybe<Scalars["String"]>;
  created: Scalars["DateTime"];
  started?: Maybe<Scalars["DateTime"]>;
  finished?: Maybe<Scalars["DateTime"]>;
  format?: ExportTypes;
  errors: Scalars["String"];
  creator: UserType;
  postProcessors?: string[];
  inputKwargs?: Record<any, any>;
  isPublic?: Scalars["Boolean"];
  myPermissions?: PermissionTypes[];
};

export type UserExportTypeConnection = {
  __typename?: "UserExportTypeConnection";
  pageInfo: PageInfo;
  edges: Array<Maybe<UserExportTypeEdge>>;
  totalCount?: Maybe<Scalars["Int"]>;
};

export type UserExportTypeEdge = {
  __typename?: "UserExportTypeEdge";
  node?: Maybe<UserExportType>;
  cursor: Scalars["String"];
};

export type UserImportType = Node & {
  __typename?: "UserImportType";
  id: Scalars["ID"];
  zip: Scalars["String"];
  name?: Maybe<Scalars["String"]>;
  created: Scalars["DateTime"];
  started?: Maybe<Scalars["DateTime"]>;
  finished?: Maybe<Scalars["DateTime"]>;
  errors: Scalars["String"];
  creator: UserType;
  isPublic?: Scalars["Boolean"];
  myPermissions?: PermissionTypes[];
};

export type UserImportTypeConnection = {
  __typename?: "UserImportTypeConnection";
  pageInfo: PageInfo;
  edges: Array<Maybe<UserImportTypeEdge>>;
  totalCount?: Maybe<Scalars["Int"]>;
};

export type UserImportTypeEdge = {
  __typename?: "UserImportTypeEdge";
  node?: Maybe<UserImportType>;
  cursor: Scalars["String"];
};

export type UserType = Node & {
  __typename?: "UserType";
  id?: Scalars["ID"];
  password?: Scalars["String"];
  lastLogin?: Maybe<Scalars["DateTime"]>;
  isUsageCapped?: Scalars["Boolean"];
  canImportCorpus?: Scalars["Boolean"];
  isSuperuser?: Scalars["Boolean"];
  username?: Scalars["String"];
  email: Scalars["String"];
  isStaff?: Scalars["Boolean"];
  isActive?: Scalars["Boolean"];
  dateJoined?: Scalars["DateTime"];
  name?: Scalars["String"];
  slug?: Scalars["String"];
  createdAssignments?: AssignmentTypeConnection;
  myAssignments?: AssignmentTypeConnection;
  userexportSet?: UserExportTypeConnection;
  userimportSet?: UserImportTypeConnection;
  editingDocuments?: DocumentTypeConnection;
  documentSet?: DocumentTypeConnection;
  corpusSet?: CorpusTypeConnection;
  editingCorpuses?: CorpusTypeConnection;
  labelSet?: AnnotationLabelTypeConnection;
  relationshipSet?: RelationshipTypeConnection;
  annotationSet?: AnnotationTypeConnection;
  labelsetSet?: LabelSetTypeConnection;
};

export type UserTypeCreatedAssignmentsArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type UserTypeMyAssignmentsArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type UserTypeUserexportSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type UserTypeUserimportSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type UserTypeEditingDocumentsArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type UserTypeDocumentSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type UserTypeCorpusSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type UserTypeEditingCorpusesArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type UserTypeLabelSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
  type?: InputMaybe<Scalars["String"]>;
};

export type UserTypeRelationshipSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type UserTypeAnnotationSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type UserTypeLabelsetSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type Verify = {
  __typename?: "Verify";
  payload: Scalars["GenericScalar"];
};

/**
 *  Analyzer Types
 */
export enum AnalysisStatus {
  Created = "CREATED",
  Queued = "QUEUED",
  Running = "RUNNING",
  Completed = "COMPLETED",
  Failed = "FAILED",
}

export type AnalysisType = Node & {
  __typename?: "AnalysisType";
  id: Scalars["ID"];
  created: Scalars["DateTime"];
  modified: Scalars["DateTime"];
  isPublic: Scalars["Boolean"];
  creator: UserType;
  analyzer: AnalyzerType;
  callbackToken: Scalars["UUID"];
  receivedCallbackFile?: Maybe<Scalars["String"]>;
  analyzedCorpus: CorpusType;
  corpusAction?: CorpusActionType;
  importLog?: Maybe<Scalars["String"]>;
  analyzedDocuments: DocumentTypeConnection;
  analysisStarted?: Maybe<Scalars["DateTime"]>;
  analysisCompleted?: Maybe<Scalars["DateTime"]>;
  status: AnalysisStatus;
  annotations: AnnotationTypeConnection;
  myPermissions?: Maybe<PermissionTypes[]>;
  isPublished?: Maybe<Scalars["Boolean"]>;
  objectSharedWith?: Maybe<Scalars["GenericScalar"]>;
  fullAnnotationList?: Maybe<Array<ServerAnnotationType>>;
};

export type AnalysisTypeAnalyzedDocumentsArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type AnalysisTypeAnnotationsArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
  rawText_Contains?: InputMaybe<Scalars["String"]>;
  annotationLabelId?: InputMaybe<Scalars["ID"]>;
  annotationLabel_Text?: InputMaybe<Scalars["String"]>;
  annotationLabel_Text_Contains?: InputMaybe<Scalars["String"]>;
  annotationLabel_Description_Contains?: InputMaybe<Scalars["String"]>;
  annotationLabel_LabelType?: InputMaybe<Scalars["String"]>;
  documentId?: InputMaybe<Scalars["ID"]>;
  corpusId?: InputMaybe<Scalars["ID"]>;
  usesLabelFromLabelsetId?: InputMaybe<Scalars["String"]>;
};

export type AnalysisTypeConnection = {
  __typename?: "AnalysisTypeConnection";
  pageInfo: PageInfo;
  edges: Array<Maybe<AnalysisTypeEdge>>;
  totalCount?: Maybe<Scalars["Int"]>;
};

export type AnalysisTypeEdge = {
  __typename?: "AnalysisTypeEdge";
  node?: Maybe<AnalysisType>;
  cursor: Scalars["String"];
};

export type AnalyzerType = Node & {
  __typename?: "AnalyzerType";
  creator: UserType;
  created: Scalars["DateTime"];
  modified: Scalars["DateTime"];
  id: Scalars["ID"];
  taskName?: Scalars["String"];
  manifest?: Maybe<AnalyzerManifestType>;
  description: Scalars["String"];
  hostGremlin: GremlinEngineType_Write;
  disabled: Scalars["Boolean"];
  isPublic: Scalars["Boolean"];
  fullLabelList: Maybe<AnnotationLabelType[]>;
  annotationlabelSet: AnnotationLabelTypeConnection;
  relationshipSet: RelationshipTypeConnection;
  labelsetSet: LabelSetTypeConnection;
  analysisSet: AnalysisTypeConnection;
  myPermissions?: Maybe<PermissionTypes[]>;
  isPublished?: Maybe<Scalars["Boolean"]>;
  objectSharedWith?: Maybe<Scalars["GenericScalar"]>;
  analyzerId?: Maybe<Scalars["String"]>;
  inputSchema?: JSONSchema7;
};

export type AnalyzerTypeAnnotationlabelSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type AnalyzerTypeRelationshipSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type AnalyzerTypeLabelsetSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type AnalyzerTypeAnalysisSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type AnalyzerTypeConnection = {
  __typename?: "AnalyzerTypeConnection";
  pageInfo: PageInfo;
  edges: Array<Maybe<AnalyzerTypeEdge>>;
  totalCount?: Maybe<Scalars["Int"]>;
};

export type AnalyzerTypeEdge = {
  __typename?: "AnalyzerTypeEdge";
  node?: Maybe<AnalyzerType>;
  cursor: Scalars["String"];
};

/**
 * Gremlin Engine Types
 */
export type GremlinEngineType_Read = Node & {
  __typename?: "GremlinEngineType_READ";
  id: Scalars["ID"];
  creator: UserType;
  created: Scalars["DateTime"];
  modified: Scalars["DateTime"];
  url: Scalars["String"];
  lastSynced?: Maybe<Scalars["DateTime"]>;
  installStarted?: Maybe<Scalars["DateTime"]>;
  installCompleted?: Maybe<Scalars["DateTime"]>;
  isPublic: Scalars["Boolean"];
  analyzerSet: AnalyzerTypeConnection;
  myPermissions?: Maybe<PermissionTypes[]>;
  isPublished?: Maybe<Scalars["Boolean"]>;
  objectSharedWith?: Maybe<Scalars["GenericScalar"]>;
};

export type GremlinEngineType_ReadAnalyzerSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type GremlinEngineType_ReadConnection = {
  __typename?: "GremlinEngineType_READConnection";
  pageInfo: PageInfo;
  edges: Array<Maybe<GremlinEngineType_ReadEdge>>;
  totalCount?: Maybe<Scalars["Int"]>;
};

export type GremlinEngineType_ReadEdge = {
  __typename?: "GremlinEngineType_READEdge";
  node?: Maybe<GremlinEngineType_Read>;
  cursor: Scalars["String"];
};

export type GremlinEngineType_Write = Node & {
  __typename?: "GremlinEngineType_WRITE";
  id: Scalars["ID"];
  creator: UserType;
  created: Scalars["DateTime"];
  modified: Scalars["DateTime"];
  url: Scalars["String"];
  lastSynced?: Maybe<Scalars["DateTime"]>;
  installStarted?: Maybe<Scalars["DateTime"]>;
  installCompleted?: Maybe<Scalars["DateTime"]>;
  isPublic: Scalars["Boolean"];
  analyzerSet: AnalyzerTypeConnection;
  apiKey?: Maybe<Scalars["String"]>;
  myPermissions?: Maybe<PermissionTypes[]>;
  isPublished?: Maybe<Scalars["Boolean"]>;
  objectSharedWith?: Maybe<Scalars["GenericScalar"]>;
};

export type GremlinEngineType_WriteAnalyzerSetArgs = {
  offset?: InputMaybe<Scalars["Int"]>;
  before?: InputMaybe<Scalars["String"]>;
  after?: InputMaybe<Scalars["String"]>;
  first?: InputMaybe<Scalars["Int"]>;
  last?: InputMaybe<Scalars["Int"]>;
};

export type GremlinEngineType_WriteConnection = {
  __typename?: "GremlinEngineType_WRITEConnection";
  pageInfo: PageInfo;
  edges: Array<Maybe<GremlinEngineType_WriteEdge>>;
  totalCount?: Maybe<Scalars["Int"]>;
};

export type GremlinEngineType_WriteEdge = {
  __typename?: "GremlinEngineType_WRITEEdge";
  node?: Maybe<GremlinEngineType_Write>;
  cursor: Scalars["String"];
};

/**
 * Gremlin Engine Manifest Types
 */
export type AnalyzerMetadataType = {
  id: string;
  description: string;
  title: string;
  dependencies: string[];
  author_name: string;
  author_email: string;
  more_details_url: string;
};

export type AnnotationLabelPythonType = {
  id: string;
  color: string;
  description: string;
  icon: string;
  text: string;
  label_type: LabelType;
};

export type OpenContractsLabelSetType = {
  id: number | string;
  title: string;
  description: string;
  icon_data?: string[];
  icon_name?: string;
  creator: string;
};

export type AnalyzerManifestType = {
  metadata: AnalyzerMetadataType;
  doc_labels: AnnotationLabelPythonType[];
  text_labels: AnnotationLabelPythonType[];
  label_set: OpenContractsLabelSetType;
};

export interface FieldsetType extends Node {
  creator: UserType;
  name: string;
  description: string;
  columns: ColumnTypeEdge;
  fullColumnList?: ColumnType[];
  inUse?: boolean;
}

export interface ColumnType extends Node {
  name: string;
  fieldset?: FieldsetType;
  query?: string;
  matchText?: string;
  mustContainText?: string;
  outputType: string;
  limitToLabel?: string;
  instructions?: string;
  extractIsList?: boolean;
  fieldsetId?: string;
  taskName: string;
}

export interface ColumnTypeEdge {
  __typename?: "ColumnTypeEdge";
  pageInfo?: PageInfo;
  edges: {
    node: ColumnType;
  }[];
}

export type DatacellTypeConnection = {
  __typename?: "DatacellTypeConnection";
  pageInfo: PageInfo;
  edges: Array<Maybe<DatacellTypeEdge>>;
  totalCount?: Maybe<Scalars["Int"]>;
};

export type DatacellTypeEdge = {
  __typename?: "DatacellTypeEdge";
  node?: Maybe<DatacellType>;
  cursor: Scalars["String"];
};

export interface ExtractType extends Node {
  corpus: CorpusType;
  name: string;
  fieldset: FieldsetType;
  creator: UserType;
  created: string;
  started?: Maybe<string>;
  finished?: Maybe<string>;
  error?: Maybe<string>;
  documents?: DocumentType[];
  corpusAction?: CorpusActionType;
  extractedDatacells?: DatacellTypeConnection;
  /**
   * Datacells visible to the current user. Accepts optional `limit`/`offset`
   * arguments on the server; callers that need a bounded payload should
   * fetch `datacellCount` alongside this field to display "N of M" indicators.
   */
  fullDatacellList?: DatacellType[];
  fullDocumentList?: DocumentType[];
  /**
   * Total number of datacells visible to the current user, ignoring any
   * `limit`/`offset` applied to `fullDatacellList`. Used alongside a bounded
   * `fullDatacellList` to render "showing N of M" indicators (see #1204).
   */
  datacellCount?: number | null;
  /**
   * Captured run-time model configuration (e.g. `{model, temperature}`) used
   * for this iteration. Null/empty for legacy extracts created before
   * iteration support landed.
   */
  modelConfig?: Record<string, any> | null;
  /**
   * Best-effort axis label inferred from the parent relationship: tells the
   * UI which dimension this iteration tests (model/doc-versions/fieldset).
   */
  iterationAxis?: "MODEL" | "DOCUMENT_VERSIONS" | "FIELDSET" | null;
  parentExtract?: ExtractType | null;
  /** Direct iterations forked from this extract (one level deep). */
  fullIterationList?: ExtractType[];
  myPermissions?: PermissionTypes[];
}

export interface DatacellType extends Node {
  extract: ExtractType;
  column: ColumnType;
  document: DocumentType;
  data: any;
  dataDefinition: string;
  started?: Maybe<string>;
  completed?: Maybe<string>;
  failed?: Maybe<string>;
  rejectedBy: Maybe<UserType>;
  approvedBy: Maybe<UserType>;
  correctedData: any;
  fullSourceList?: ServerAnnotationType[];
  sources?: AnnotationTypeConnection;
}
export interface ExportObject {
  id: string;
  name: string;
  finished: Scalars["DateTime"];
  started: Scalars["DateTime"];
  created: Scalars["DateTime"];
  errors: string;
  backendLock: boolean;
  file: string;
}
export interface PageAwareAnnotationType {
  pdfPageInfo: {
    pageCount: number;
    currentPage: number;
    corpusId: string;
    documentId: string;
    hasNextPage: boolean;
    hasPreviousPage: boolean;
    labelType: LabelType;
    forAnalysisIds: string;
  };
  pageAnnotations: ServerAnnotationType[];
}

export type CorpusActionType = Node & {
  __typename?: "CorpusActionType";
  id: Scalars["ID"];
  name: Scalars["String"];
  corpus: CorpusType;
  fieldset?: Maybe<FieldsetType>;
  analyzer?: Maybe<AnalyzerType>;
  trigger: Scalars["String"];
  creator: UserType;
  created: Scalars["DateTime"];
  modified: Scalars["DateTime"];
};

export type CorpusActionTypeConnection = {
  __typename?: "CorpusActionTypeConnection";
  pageInfo: PageInfo;
  edges: Array<Maybe<CorpusActionTypeEdge>>;
  totalCount?: Maybe<Scalars["Int"]>;
};

export type CorpusActionTypeEdge = {
  __typename?: "CorpusActionTypeEdge";
  node?: Maybe<CorpusActionType>;
  cursor: Scalars["String"];
};

export type DocumentCorpusActionsType = {
  __typename?: "DocumentCorpusActionsType";
  corpus_actions: Array<Maybe<CorpusActionType>>;
  extracts: Array<Maybe<ExtractType>>;
  analyses: Array<Maybe<AnalysisType>>;
};

export interface AnalysisRowType extends Node {
  id: Scalars["ID"];
  userLock: Maybe<UserType>;
  backendLock: Scalars["Boolean"];
  isPublic: Scalars["Boolean"];
  creator: UserType;
  created: Scalars["DateTime"];
  modified: Scalars["DateTime"];
  document: DocumentType;
  annotations: AnnotationTypeConnection;
  data: DatacellTypeConnection;
  analysis: Maybe<AnalysisType>;
  extract: Maybe<ExtractType>;
  myPermissions: Maybe<Array<PermissionTypes>>;
  isPublished: Maybe<Scalars["Boolean"]>;
  objectSharedWith: Maybe<Scalars["GenericScalar"]>;
}

export type FeedbackTypeConnection = {
  __typename?: "UserFeedbackTypeConnection";
  pageInfo: PageInfo;
  edges: Array<Maybe<FeedbackTypeEdge>>;
  totalCount?: Maybe<Scalars["Int"]>;
};

export type FeedbackTypeEdge = {
  __typename?: "UserFeedbackTypeEdge";
  node?: Maybe<FeedbackType>;
  cursor: Scalars["String"];
};

export interface FeedbackType extends Node {
  id: Scalars["ID"];
  userLock: Maybe<UserType>;
  backendLock: Scalars["Boolean"];
  isPublic: Scalars["Boolean"];
  creator: UserType;
  created: Scalars["DateTime"];
  modified: Scalars["DateTime"];
  approved?: Boolean;
  rejected?: Boolean;
  markdown?: string;
  metadata: Record<any, any>;
  commented_annotation?: ServerAnnotationType | null;
}

export type ConversationTypeEnum = "CHAT" | "THREAD";
export type AgentTypeEnum = "DOCUMENT_AGENT" | "CORPUS_AGENT";
export type MessageStateChoices =
  | "IN_PROGRESS"
  | "COMPLETED"
  | "CANCELLED"
  | "ERROR"
  | "AWAITING_APPROVAL";
export type VoteType = "UPVOTE" | "DOWNVOTE";

/**
 * Agent Configuration Type - represents bot/agent profiles
 */
export type AgentConfigurationType = Node & {
  __typename?: "AgentConfigurationType";
  id: Scalars["ID"];
  name: Scalars["String"];
  slug?: Maybe<Scalars["String"]>;
  description?: Maybe<Scalars["String"]>;
  systemInstructions: Scalars["String"];
  availableTools?: Maybe<Scalars["GenericScalar"]>;
  permissionRequiredTools?: Maybe<Scalars["GenericScalar"]>;
  badgeConfig?: Maybe<Scalars["GenericScalar"]>;
  avatarUrl?: Maybe<Scalars["String"]>;
  scope: Scalars["String"];
  corpus?: Maybe<CorpusType>;
  isActive: Scalars["Boolean"];
  creator: UserType;
  isPublic?: Scalars["Boolean"];
  created: Scalars["DateTime"];
  modified: Scalars["DateTime"];
  myPermissions?: PermissionTypes[];
};

export type AgentConfigurationTypeConnection = {
  __typename?: "AgentConfigurationTypeConnection";
  pageInfo: PageInfo;
  edges: Array<Maybe<AgentConfigurationTypeEdge>>;
  totalCount?: Maybe<Scalars["Int"]>;
};

export type AgentConfigurationTypeEdge = {
  __typename?: "AgentConfigurationTypeEdge";
  node?: Maybe<AgentConfigurationType>;
  cursor: Scalars["String"];
};

/**
 * User Badge Type - represents awarded badges to users
 */
export type UserBadgeType = Node & {
  __typename?: "UserBadgeType";
  id: Scalars["ID"];
  user: UserType;
  badge: BadgeType;
  awardedAt: Scalars["DateTime"];
  awardedBy?: Maybe<UserType>;
  corpus?: Maybe<CorpusType>;
};

/**
 * Badge Type - represents badge definitions
 */
export type BadgeType = Node & {
  __typename?: "BadgeType";
  id: Scalars["ID"];
  name: Scalars["String"];
  description: Scalars["String"];
  icon: Scalars["String"];
  color: Scalars["String"];
  badgeType: Scalars["String"];
  isAutoAwarded?: Scalars["Boolean"];
};

export type ConversationType = Node & {
  __typename?: "ConversationType";
  id: Scalars["ID"];
  conversationType?: ConversationTypeEnum;
  title?: Maybe<Scalars["String"]>;
  description?: Maybe<Scalars["String"]>;
  createdAt: Scalars["DateTime"];
  updatedAt: Scalars["DateTime"];
  chatWithCorpus?: Maybe<CorpusType>;
  chatWithDocument?: Maybe<DocumentType>;
  chatMessages: ChatMessageTypeConnection;
  allMessages?: Maybe<ChatMessageType[]>;
  creator: UserType;
  created: Scalars["DateTime"];
  modified: Scalars["DateTime"];
  isPublic?: Scalars["Boolean"];
  myPermissions?: PermissionTypes[];

  // Voting fields
  upvoteCount?: Scalars["Int"];
  downvoteCount?: Scalars["Int"];
  userVote?: Maybe<Scalars["String"]>; // "UPVOTE", "DOWNVOTE", or null

  // Moderation fields
  isLocked?: Scalars["Boolean"];
  lockedBy?: Maybe<UserType>;
  lockedAt?: Maybe<Scalars["DateTime"]>;
  isPinned?: Scalars["Boolean"];
  pinnedBy?: Maybe<UserType>;
  pinnedAt?: Maybe<Scalars["DateTime"]>;
  deletedAt?: Maybe<Scalars["DateTime"]>;
};

export type ConversationTypeConnection = {
  __typename?: "ConversationTypeConnection";
  pageInfo: PageInfo;
  edges: Array<Maybe<ConversationTypeEdge>>;
  totalCount?: Maybe<Scalars["Int"]>;
};

export type ConversationTypeEdge = {
  __typename?: "ConversationTypeEdge";
  node?: Maybe<ConversationType>;
  cursor: Scalars["String"];
};

// Mentioned resource type for @corpus:, @document:, and annotation mentions (Issue #623, #689)
export type MentionedResourceType = {
  __typename?: "MentionedResourceType";
  type: "CORPUS" | "DOCUMENT" | "ANNOTATION";
  id: Scalars["ID"];
  slug?: Maybe<Scalars["String"]>; // Null for annotations
  title: Scalars["String"];
  url: Scalars["String"];
  corpus?: Maybe<{
    slug: Scalars["String"];
    title: Scalars["String"];
  }>;
  // Annotation-specific fields (Issue #689)
  rawText?: Maybe<Scalars["String"]>;
  annotationLabel?: Maybe<Scalars["String"]>;
  document?: Maybe<{
    id: Scalars["ID"];
    slug: Scalars["String"];
    title: Scalars["String"];
  }>;
};

export type ChatMessageType = Node & {
  __typename?: "ChatMessageType";
  id: Scalars["ID"];
  conversation: ConversationType;
  msgType: Scalars["String"];
  agentType?: Maybe<AgentTypeEnum>;
  agentConfiguration?: Maybe<AgentConfigurationType>;
  content: Scalars["String"];
  data?: Maybe<{
    sources?: WebSocketSources[];
    message_id?: string;
  }>;
  state?: MessageStateChoices;
  createdAt: Scalars["DateTime"];
  sourceDocument?: Maybe<DocumentType>;
  sourceAnnotations: AnnotationTypeConnection;
  createdAnnotations: AnnotationTypeConnection;
  creator: UserType;
  created: Scalars["DateTime"];
  modified: Scalars["DateTime"];
  isPublic?: Scalars["Boolean"];
  myPermissions?: PermissionTypes[];

  // Threading fields
  parentMessage?: Maybe<ChatMessageType>;
  replies?: Maybe<ChatMessageType[]>;

  // Voting fields
  upvoteCount?: Scalars["Int"];
  downvoteCount?: Scalars["Int"];
  userVote?: Maybe<VoteType>;

  // Soft delete
  deletedAt?: Maybe<Scalars["DateTime"]>;
  deletedBy?: Maybe<UserType>;

  // Mentioned resources (Issue #623)
  mentionedResources?: Maybe<MentionedResourceType[]>;
};

export type ChatMessageTypeConnection = {
  __typename?: "ChatMessageTypeConnection";
  pageInfo: PageInfo;
  edges: Array<Maybe<ChatMessageTypeEdge>>;
  totalCount?: Maybe<Scalars["Int"]>;
};

export type ChatMessageTypeEdge = {
  __typename?: "ChatMessageTypeEdge";
  node?: Maybe<ChatMessageType>;
  cursor: Scalars["String"];
};

/**
 * Represents a single Note record in GraphQL.
 * Includes hierarchical tree fields (descendantsTree, fullTree, subtree).
 */
export type NoteType = Node & {
  __typename?: "NoteType";
  id: string;
  title: string;
  content: string;
  parent?: Maybe<NoteType>;
  annotation?: Maybe<ServerAnnotationType>;
  document: DocumentType;
  isPublic: boolean;
  creator: UserType;
  created: string; // DateTime
  modified: string; // DateTime
  myPermissions?: Maybe<Array<Maybe<PermissionTypes>>>;
  /**
   * A flat list of descendant notes, each including only
   * the IDs of its immediate children.
   * Freeform data structure.
   */
  descendantsTree?: Maybe<any>;
  /**
   * A flat list of notes from the root ancestor,
   * each including only the IDs of its immediate children.
   * Freeform data structure.
   */
  fullTree?: Maybe<any>;
  /**
   * A combined tree that includes the path
   * from the root ancestor to this note
   * and all its descendants.
   * Freeform data structure.
   */
  subtree?: Maybe<any>;
};

export type NoteTypeEdge = {
  __typename?: "NoteTypeEdge";
  node?: Maybe<NoteType>;
  cursor: string;
};

export type NoteTypeConnection = {
  __typename?: "NoteTypeConnection";
  edges: Array<Maybe<NoteTypeEdge>>;
  pageInfo: PageInfo;
  totalCount?: Maybe<number>;
};

/**
 * Represents a relationship between two documents in GraphQL.
 */
export type DocumentRelationshipType = Node & {
  __typename?: "DocumentRelationshipType";
  id: string;
  /**
   * Arbitrary JSON data field.
   */
  data?: Maybe<any>;
  relationshipType: string;
  annotationLabel?: Maybe<AnnotationLabelType>;
  corpus?: Maybe<CorpusType>;
  sourceDocument: DocumentType;
  targetDocument: DocumentType;
  creator: UserType;
  created: string; // DateTime
  modified: string; // DateTime
  isPublic?: Maybe<boolean>;
  myPermissions?: Maybe<Array<Maybe<PermissionTypes>>>;
};

export type DocumentRelationshipTypeEdge = {
  __typename?: "DocumentRelationshipTypeEdge";
  node?: Maybe<DocumentRelationshipType>;
  cursor: string;
};

export type DocumentRelationshipTypeConnection = {
  __typename?: "DocumentRelationshipTypeConnection";
  edges: Array<Maybe<DocumentRelationshipTypeEdge>>;
  pageInfo: PageInfo;
  totalCount?: Maybe<number>;
};

/** Graphene type for pipeline components. */
export type PipelineComponentType = {
  /** Name of the component class. */
  name?: string;
  /** Title of the component. */
  title?: string;
  /** Description of the component. */
  description?: string;
  /** Author of the component. */
  author?: string;
  /** List of dependencies required by the component. */
  dependencies?: string[];
  /** Vector size for embedders. */
  vectorSize?: number;
  className?: string;
  /** Module name for the component. */
  moduleName?: string;
  /** List of supported file types. */
  supportedFileTypes?: FileTypeEnum[];
  /** Type of the component (parser, embedder, or thumbnailer). */
  componentType?: string;
  /** JSONSchema schema for inputs supported from user (experimental - not fully implemented). */
  inputSchema?: Record<any, any>;
  /** Schema for component configuration settings stored in PipelineSettings. */
  settingsSchema?: Maybe<Array<Maybe<ComponentSettingSchemaType>>>;
  /** Whether this component is enabled in the current pipeline settings. */
  enabled?: boolean;
};

/** Valid setting types for pipeline component configuration. */
export type SettingTypeEnum = "required" | "optional" | "secret";

/** Common Python type hints used in settings schemas. */
export type PythonTypeEnum = "str" | "int" | "float" | "bool" | "any" | string;

export type ComponentSettingSchemaType = {
  __typename?: "ComponentSettingSchemaType";
  /** Setting name (used as key in component_settings dict). */
  name: string;
  /** Type: 'required', 'optional', or 'secret'. */
  settingType: SettingTypeEnum;
  /** Python type hint (e.g., 'str', 'int', 'bool'). */
  pythonType?: PythonTypeEnum;
  /** Whether this setting must have a value for the component to work. */
  required: boolean;
  /** Human-readable description of the setting. */
  description?: string;
  /** Default value if not configured. */
  default?: Scalars["GenericScalar"];
  /** Environment variable name used during migration seeding. */
  envVar?: string;
  /** Whether this setting currently has a value configured. */
  hasValue?: boolean;
  /** Current value (always null for secrets to avoid exposure). */
  currentValue?: Scalars["GenericScalar"];
};

/** Graphene type for grouping pipeline components. */
export type PipelineComponentsType = {
  /** List of available parsers. */
  parsers?: Maybe<Array<Maybe<PipelineComponentType>>>;
  /** List of available embedders. */
  embedders?: Maybe<Array<Maybe<PipelineComponentType>>>;
  /** List of available thumbnail generators. */
  thumbnailers?: Maybe<Array<Maybe<PipelineComponentType>>>;
};

/** Enum for file types. */
export enum FileTypeEnum {
  /** PDF file type. */
  PDF = "application/pdf",
  /** Plain text file type. */
  TXT = "text/plain",
  /** DOCX file type. */
  DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

/** Per-stage availability for a file type. */
export type StageCoverageType = {
  __typename?: "StageCoverageType";
  /** Whether at least one parser supports this file type. */
  parser: boolean;
  /** Whether at least one embedder supports this file type. */
  embedder: boolean;
  /** Whether at least one thumbnailer supports this file type. */
  thumbnailer: boolean;
};

/** Information about a MIME type's support level in the pipeline. */
export type SupportedMimeTypeType = {
  __typename?: "SupportedMimeTypeType";
  /** Canonical MIME type string (e.g. 'application/pdf'). */
  mimetype: string;
  /** Short file type label (e.g. 'pdf'). */
  fileType: string;
  /** Human-readable label (e.g. 'PDF'). */
  label: string;
  /** Whether all required pipeline stages have at least one component. */
  fullySupported: boolean;
  /** Per-stage availability for this file type. */
  stageCoverage: StageCoverageType;
};

/**
 * Pipeline Settings Type - represents system-wide document processing configuration.
 * Only modifiable by superusers.
 */
export type PipelineSettingsType = {
  __typename?: "PipelineSettingsType";
  /** Mapping of MIME types to parser class paths. */
  preferredParsers?: Maybe<Scalars["GenericScalar"]>;
  /** Mapping of MIME types to embedder class paths. */
  preferredEmbedders?: Maybe<Scalars["GenericScalar"]>;
  /** Mapping of MIME types to thumbnailer class paths. */
  preferredThumbnailers?: Maybe<Scalars["GenericScalar"]>;
  /** Mapping of parser class paths to configuration kwargs. */
  parserKwargs?: Maybe<Scalars["GenericScalar"]>;
  /** Mapping of component class paths to settings overrides. */
  componentSettings?: Maybe<Scalars["GenericScalar"]>;
  /** Default embedder class path. */
  defaultEmbedder?: Maybe<Scalars["String"]>;
  /** List of components with encrypted secrets configured (actual secrets never exposed). */
  componentsWithSecrets?: Maybe<Array<Maybe<Scalars["String"]>>>;
  /** List of enabled component class paths. */
  enabledComponents?: Maybe<Array<Maybe<Scalars["String"]>>>;
  /** When settings were last modified. */
  modified?: Maybe<Scalars["DateTime"]>;
  /** User who last modified the settings. */
  modifiedBy?: Maybe<UserType>;
};

/**
 * Mutation response for updating pipeline settings.
 */
export type UpdatePipelineSettingsResponse = {
  __typename?: "UpdatePipelineSettingsMutation";
  ok?: Maybe<Scalars["Boolean"]>;
  message?: Maybe<Scalars["String"]>;
  pipelineSettings?: Maybe<PipelineSettingsType>;
};

/**
 * Mutation response for resetting pipeline settings.
 */
export type ResetPipelineSettingsResponse = {
  __typename?: "ResetPipelineSettingsMutation";
  ok?: Maybe<Scalars["Boolean"]>;
  message?: Maybe<Scalars["String"]>;
  pipelineSettings?: Maybe<PipelineSettingsType>;
};

/**
 * Mutation response for updating component secrets.
 */
export type UpdateComponentSecretsResponse = {
  __typename?: "UpdateComponentSecretsMutation";
  ok?: Maybe<Scalars["Boolean"]>;
  message?: Maybe<Scalars["String"]>;
  componentsWithSecrets?: Maybe<Array<Maybe<Scalars["String"]>>>;
};

/**
 * Mutation response for deleting component secrets.
 */
export type DeleteComponentSecretsResponse = {
  __typename?: "DeleteComponentSecretsMutation";
  ok?: Maybe<Scalars["Boolean"]>;
  message?: Maybe<Scalars["String"]>;
  componentsWithSecrets?: Maybe<Array<Maybe<Scalars["String"]>>>;
};
