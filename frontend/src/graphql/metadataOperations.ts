import { gql } from "@apollo/client";

// Queries
export const GET_CORPUS_METADATA_COLUMNS = gql`
  query GetCorpusMetadataColumns($corpusId: ID!) {
    corpusMetadataColumns(corpusId: $corpusId) {
      id
      name
      dataType
      helpText
      validationConfig
      defaultValue
      displayOrder
      isManualEntry
    }
  }
`;

export const GET_DOCUMENT_METADATA_DATACELLS = gql`
  query GetDocumentMetadataDatacells($documentId: ID!, $corpusId: ID!) {
    documentMetadataDatacells(documentId: $documentId, corpusId: $corpusId) {
      id
      data
      dataDefinition
      column {
        id
        name
        dataType
        validationConfig
        helpText
        isManualEntry
      }
      creator {
        id
        slug
        email
      }
    }
  }
`;

export const GET_DOCUMENTS_METADATA_BATCH = gql`
  query GetDocumentsMetadataBatch($documentIds: [ID]!, $corpusId: ID!) {
    documentsMetadataDatacellsBatch(
      documentIds: $documentIds
      corpusId: $corpusId
    ) {
      documentId
      datacells {
        id
        data
        dataDefinition
        column {
          id
          name
          dataType
          validationConfig
          helpText
          isManualEntry
        }
        creator {
          id
          slug
          email
        }
      }
    }
  }
`;

// Mutations
export const CREATE_METADATA_COLUMN = gql`
  mutation CreateMetadataColumn(
    $corpusId: ID!
    $name: String!
    $dataType: String!
    $validationConfig: GenericScalar
    $defaultValue: GenericScalar
    $helpText: String
    $displayOrder: Int
  ) {
    createMetadataColumn(
      corpusId: $corpusId
      name: $name
      dataType: $dataType
      validationConfig: $validationConfig
      defaultValue: $defaultValue
      helpText: $helpText
      displayOrder: $displayOrder
    ) {
      ok
      message
      obj {
        id
        name
        dataType
        helpText
        validationConfig
        defaultValue
        displayOrder
        isManualEntry
      }
    }
  }
`;

export const UPDATE_METADATA_COLUMN = gql`
  mutation UpdateMetadataColumn(
    $columnId: ID!
    $name: String
    $validationConfig: GenericScalar
    $defaultValue: GenericScalar
    $helpText: String
    $displayOrder: Int
  ) {
    updateMetadataColumn(
      columnId: $columnId
      name: $name
      validationConfig: $validationConfig
      defaultValue: $defaultValue
      helpText: $helpText
      displayOrder: $displayOrder
    ) {
      ok
      message
      obj {
        id
        name
        dataType
        helpText
        validationConfig
        defaultValue
        displayOrder
        isManualEntry
      }
    }
  }
`;

export const DELETE_METADATA_COLUMN = gql`
  mutation DeleteMetadataColumn($columnId: ID!) {
    deleteMetadataColumn(columnId: $columnId) {
      ok
      message
    }
  }
`;

export const SET_METADATA_VALUE = gql`
  mutation SetMetadataValue(
    $documentId: ID!
    $corpusId: ID!
    $columnId: ID!
    $value: GenericScalar!
  ) {
    setMetadataValue(
      documentId: $documentId
      corpusId: $corpusId
      columnId: $columnId
      value: $value
    ) {
      ok
      message
      obj {
        id
        data
        dataDefinition
        column {
          id
          name
          dataType
        }
      }
    }
  }
`;

export const DELETE_METADATA_VALUE = gql`
  mutation DeleteMetadataValue(
    $documentId: ID!
    $corpusId: ID!
    $columnId: ID!
  ) {
    deleteMetadataValue(
      documentId: $documentId
      corpusId: $corpusId
      columnId: $columnId
    ) {
      ok
      message
    }
  }
`;

// Type definitions for GraphQL operations
export interface GetCorpusMetadataColumnsInput {
  corpusId: string;
}

export interface GetCorpusMetadataColumnsOutput {
  corpusMetadataColumns: {
    id: string;
    name: string;
    dataType: string;
    helpText?: string;
    validationConfig?: any;
    defaultValue?: any;
    displayOrder: number;
    isManualEntry: boolean;
  }[];
}

export interface GetDocumentsMetadataBatchInput {
  documentIds: string[];
  corpusId: string;
}

export interface GetDocumentsMetadataBatchOutput {
  documentsMetadataDatacellsBatch: {
    documentId: string;
    datacells: {
      id: string;
      data: any;
      dataDefinition: string;
      column: {
        id: string;
        name: string;
        dataType: string;
        validationConfig?: any;
        helpText?: string;
        isManualEntry: boolean;
      };
      creator: {
        id: string;
        email: string;
      };
    }[];
  }[];
}

export interface CreateMetadataColumnInput {
  corpusId: string;
  name: string;
  dataType: string;
  validationConfig?: any;
  defaultValue?: any;
  helpText?: string;
  displayOrder?: number;
}

export interface CreateMetadataColumnOutput {
  createMetadataColumn: {
    ok: boolean;
    message: string;
    obj: {
      id: string;
      name: string;
      dataType: string;
      helpText?: string;
      validationConfig?: any;
      defaultValue?: any;
      displayOrder: number;
      isManualEntry: boolean;
    };
  };
}

export interface UpdateMetadataColumnInput {
  columnId: string;
  name?: string;
  validationConfig?: any;
  defaultValue?: any;
  helpText?: string;
  displayOrder?: number;
}

export interface UpdateMetadataColumnOutput {
  updateMetadataColumn: {
    ok: boolean;
    message: string;
    obj: {
      id: string;
      name: string;
      dataType: string;
      helpText?: string;
      validationConfig?: any;
      defaultValue?: any;
      displayOrder: number;
      isManualEntry: boolean;
    };
  };
}

export interface DeleteMetadataColumnInput {
  columnId: string;
}

export interface DeleteMetadataColumnOutput {
  deleteMetadataColumn: {
    ok: boolean;
    message: string;
  };
}

export interface SetMetadataValueInput {
  documentId: string;
  corpusId: string;
  columnId: string;
  value: any;
}

export interface SetMetadataValueOutput {
  setMetadataValue: {
    ok: boolean;
    message: string;
    obj: {
      id: string;
      data: any;
      dataDefinition: string;
      column: {
        id: string;
        name: string;
        dataType: string;
      };
    };
  };
}

export interface DeleteMetadataValueInput {
  documentId: string;
  corpusId: string;
  columnId: string;
}

export interface DeleteMetadataValueOutput {
  deleteMetadataValue: {
    ok: boolean;
    message: string;
  };
}
