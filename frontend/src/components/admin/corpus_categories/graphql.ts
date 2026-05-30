import { gql } from "@apollo/client";
import { CorpusCategoryType } from "../../../types/graphql-api";

// ============================================================================
// GraphQL Query/Mutation Result + Input Types
// ============================================================================

/**
 * Subset of CorpusCategoryType fields managed by the admin panel.
 */
export type ManagedCorpusCategory = Pick<
  CorpusCategoryType,
  "id" | "name" | "description" | "icon" | "color" | "sortOrder" | "corpusCount"
>;

export interface AdminCorpusCategoriesResult {
  corpusCategories: {
    edges: Array<{ node: ManagedCorpusCategory }>;
  };
}

export interface CorpusCategoryMutationResult {
  ok: boolean;
  message: string;
  obj?: ManagedCorpusCategory | null;
}

export interface CreateCorpusCategoryOutput {
  createCorpusCategory: CorpusCategoryMutationResult;
}

export interface UpdateCorpusCategoryOutput {
  updateCorpusCategory: CorpusCategoryMutationResult;
}

export interface DeleteCorpusCategoryOutput {
  deleteCorpusCategory: { ok: boolean; message: string };
}

export interface CreateCorpusCategoryInputs {
  name: string;
  description?: string;
  icon?: string;
  color?: string;
  sortOrder?: number;
}

export interface UpdateCorpusCategoryInputs {
  id: string;
  name?: string;
  description?: string;
  icon?: string;
  color?: string;
  sortOrder?: number;
}

export interface DeleteCorpusCategoryInputs {
  id: string;
}

// ============================================================================
// GraphQL Operations
// ============================================================================

export const GET_ADMIN_CORPUS_CATEGORIES = gql`
  query GetAdminCorpusCategories {
    corpusCategories {
      edges {
        node {
          id
          name
          description
          icon
          color
          sortOrder
          corpusCount
        }
      }
    }
  }
`;

export const CREATE_CORPUS_CATEGORY = gql`
  mutation CreateCorpusCategory(
    $name: String!
    $description: String
    $icon: String
    $color: String
    $sortOrder: Int
  ) {
    createCorpusCategory(
      name: $name
      description: $description
      icon: $icon
      color: $color
      sortOrder: $sortOrder
    ) {
      ok
      message
      obj {
        id
        name
        description
        icon
        color
        sortOrder
        corpusCount
      }
    }
  }
`;

export const UPDATE_CORPUS_CATEGORY = gql`
  mutation UpdateCorpusCategory(
    $id: ID!
    $name: String
    $description: String
    $icon: String
    $color: String
    $sortOrder: Int
  ) {
    updateCorpusCategory(
      id: $id
      name: $name
      description: $description
      icon: $icon
      color: $color
      sortOrder: $sortOrder
    ) {
      ok
      message
      obj {
        id
        name
        description
        icon
        color
        sortOrder
        corpusCount
      }
    }
  }
`;

export const DELETE_CORPUS_CATEGORY = gql`
  mutation DeleteCorpusCategory($id: ID!) {
    deleteCorpusCategory(id: $id) {
      ok
      message
    }
  }
`;
