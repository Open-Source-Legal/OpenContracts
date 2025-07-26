import { v4 as uuidv4 } from "uuid";
import {
  UserType,
  AssignmentTypeConnection,
  DocumentTypeConnection,
  CorpusTypeConnection,
  AnnotationLabelTypeConnection,
  RelationshipTypeConnection,
  AnnotationTypeConnection,
  LabelSetTypeConnection,
  UserExportTypeConnection,
  UserImportTypeConnection,
  PageInfo,
  AnalysisTypeConnection,
  ExtractType,
  ColumnType,
  DatacellType,
  CorpusType,
  FieldsetType,
  DocumentType,
} from "../../types/graphql-api";

export function generateMockUser(): UserType {
  return {
    __typename: "UserType",
    id: uuidv4(),
    password: "mockPassword",
    lastLogin: new Date().toISOString(),
    isSuperuser: false,
    username: "mockUsername",
    email: "mock@example.com",
    isStaff: false,
    isActive: true,
    dateJoined: new Date().toISOString(),
    name: "Mock User",
    createdAssignments: generateMockAssignmentConnection(),
    myAssignments: generateMockAssignmentConnection(),
    userexportSet: generateMockUserExportTypeConnection(),
    userimportSet: generateMockUserImportTypeConnection(),
    editingDocuments: generateMockDocumentConnection(),
    documentSet: generateMockDocumentConnection(),
    corpusSet: generateMockCorpusConnection(),
    editingCorpuses: generateMockCorpusConnection(),
    labelSet: generateMockAnnotationLabelConnection(),
    relationshipSet: generateMockRelationshipConnection(),
    annotationSet: generateMockAnnotationConnection(),
    labelsetSet: generateMockLabelSetConnection(),
  };
}

export function generateMockAssignmentConnection(): AssignmentTypeConnection {
  return {
    __typename: "AssignmentTypeConnection",
    pageInfo: generateMockPageInfo(),
    edges: [],
    totalCount: 0,
  };
}

export function generateMockUserExportTypeConnection(): UserExportTypeConnection {
  return {
    __typename: "UserExportTypeConnection",
    pageInfo: generateMockPageInfo(),
    edges: [],
    totalCount: 0,
  };
}

export function generateMockUserImportTypeConnection(): UserImportTypeConnection {
  return {
    __typename: "UserImportTypeConnection",
    pageInfo: generateMockPageInfo(),
    edges: [],
    totalCount: 0,
  };
}

export function generateMockDocumentConnection(): DocumentTypeConnection {
  return {
    __typename: "DocumentTypeConnection",
    pageInfo: generateMockPageInfo(),
    edges: [],
    totalCount: 0,
  };
}

export function generateMockCorpusConnection(): CorpusTypeConnection {
  return {
    __typename: "CorpusTypeConnection",
    pageInfo: generateMockPageInfo(),
    edges: [],
    totalCount: 0,
  };
}

export function generateMockAnnotationLabelConnection(): AnnotationLabelTypeConnection {
  return {
    __typename: "AnnotationLabelTypeConnection",
    pageInfo: generateMockPageInfo(),
    edges: [],
    totalCount: 0,
  };
}

export function generateMockRelationshipConnection(): RelationshipTypeConnection {
  return {
    __typename: "RelationshipTypeConnection",
    pageInfo: generateMockPageInfo(),
    edges: [],
    totalCount: 0,
  };
}

export function generateMockAnnotationConnection(): AnnotationTypeConnection {
  return {
    __typename: "AnnotationTypeConnection",
    pageInfo: generateMockPageInfo(),
    edges: [],
    totalCount: 0,
  };
}

export function generateMockLabelSetConnection(): LabelSetTypeConnection {
  return {
    __typename: "LabelSetTypeConnection",
    pageInfo: generateMockPageInfo(),
    edges: [],
    totalCount: 0,
  };
}

export function generateMockPageInfo(): PageInfo {
  return {
    __typename: "PageInfo",
    hasNextPage: false,
    hasPreviousPage: false,
    startCursor: null,
    endCursor: null,
  };
}

export function generateMockFieldset(creator: UserType): FieldsetType {
  return {
    id: uuidv4(),
    creator,
    name: "mockFieldset",
    description: "Mock fieldset description",
    columns: {
      edges: [],
    },
  };
}

export function generateMockColumn(fieldset: FieldsetType): ColumnType {
  return {
    id: uuidv4(),
    fieldset,
    name: "mockName",
    query: "mockQuery",
    matchText: "mockMatchText",
    outputType: "mockOutputType",
    limitToLabel: "mockLimitToLabel",
    instructions: "mockInstructions",
    taskName: "mockTaskName",
  };
}

export function generateMockCorpus(creator: UserType): CorpusType {
  return {
    __typename: "CorpusType",
    id: uuidv4(),
    title: "Mock Corpus",
    appliedAnalyzerIds: [],
    is_selected: false,
    is_opened: false,
    description: "Mock corpus description",
    icon: "mockIcon",
    documents: generateMockDocumentConnection(),
    labelSet: null,
    creator,
    parent: undefined,
    backendLock: false,
    userLock: null,
    error: false,
    created: new Date().toISOString(),
    modified: new Date().toISOString(),
    assignmentSet: generateMockAssignmentConnection(),
    relationshipSet: generateMockRelationshipConnection(),
    allAnnotationSummaries: [],
    analyses: generateMockAnalysisConnection(),
    isPublic: false,
    myPermissions: [],
  };
}

export function generateMockExtract(
  corpus: CorpusType,
  creator: UserType,
  fieldset: FieldsetType
): ExtractType {
  return {
    id: uuidv4(),
    corpus,
    name: "Mock Extract",
    fieldset,
    creator,
    created: new Date().toISOString(),
    started: null,
    finished: null,
    error: null,
  };
}

export function generateMockRow(
  extract: ExtractType,
  column: ColumnType,
  document: DocumentType
): DatacellType {
  return {
    id: uuidv4(),
    extract,
    column,
    document,
    data: {
      data: "Some Data",
    },
    dataDefinition: "str",
    started: null,
    completed: null,
    failed: null,
    rejectedBy: null,
    approvedBy: null,
    correctedData: null,
  };
}

export function generateMockAnalysisConnection(): AnalysisTypeConnection {
  return {
    __typename: "AnalysisTypeConnection",
    pageInfo: generateMockPageInfo(),
    edges: [],
    totalCount: 0,
  };
}
