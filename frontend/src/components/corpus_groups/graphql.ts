import { gql } from "@apollo/client";
import { CorpusGroupType } from "../../types/graphql-api";

// ============================================================================
// GraphQL Query/Mutation Result + Input Types
// ============================================================================

/**
 * How many member corpora to load per group.
 *
 * This is a *membership* fetch, not a display preview: the edit form seeds
 * ``corpusIds`` from these edges and ``updateCorpusGroup`` replaces the
 * caller-visible membership, so a member that is not loaded here cannot be
 * re-submitted. ``handleSubmit`` compares the loaded count against the
 * connection's ``totalCount`` and refuses to save when they disagree, so the
 * pathological >LIMIT case fails safe instead of silently dropping members.
 *
 * MUST NOT exceed the server's ``RELAY_CONNECTION_MAX_LIMIT``
 * (``config/graphql/core/relay.py``), which is a hard ``assert`` — not a clamp.
 * Requesting more makes every query and mutation selecting ``corpora`` fail
 * with an ``AssertionError`` rather than returning a truncated page.
 *
 * Passed as the ``$corporaLimit`` operation variable rather than interpolated
 * into the document. ``scripts/validate_frontend_graphql.py`` skips any
 * document containing an interpolation, so interpolating this constant would
 * silently drop the query from the validation sweep.
 */
export const CORPUS_GROUP_MEMBERSHIP_FETCH_LIMIT = 100;

/**
 * Subset of CorpusGroupType fields managed by the corpus-group panel.
 */
export type ManagedCorpusGroup = Pick<
  CorpusGroupType,
  | "id"
  | "title"
  | "slug"
  | "description"
  | "isPublic"
  | "created"
  | "modified"
  | "creator"
  | "defaultAgent"
  | "corpora"
  | "myPermissions"
>;

export interface MyCorpusGroupsResult {
  corpusGroups: {
    /** Total matching groups server-side — may exceed the loaded edges. */
    totalCount: number;
    edges: Array<{ node: ManagedCorpusGroup }>;
  };
}

export interface MyCorpusGroupsInputs {
  /**
   * Narrows the visibility-scoped connection to groups the viewer created.
   * Omitted/false returns everything visible (own + public + shared).
   */
  mine?: boolean;
  corporaLimit?: number;
}

export interface CorpusGroupMutationResult {
  ok: boolean;
  message: string;
  corpusGroup?: ManagedCorpusGroup | null;
}

export interface CreateCorpusGroupOutput {
  createCorpusGroup: CorpusGroupMutationResult;
}

export interface UpdateCorpusGroupOutput {
  updateCorpusGroup: CorpusGroupMutationResult;
}

export interface DeleteCorpusGroupOutput {
  deleteCorpusGroup: { ok: boolean; message: string };
}

export interface CreateCorpusGroupInputs {
  title: string;
  /** Leave unset to let the backend derive one from the title. */
  slug?: string;
  description?: string;
  /** Relay global IDs of the corpora to bundle. */
  corpusIds?: string[];
  /** Relay global ID of the orchestrator agent to bind. */
  defaultAgentId?: string;
  isPublic?: boolean;
  corporaLimit?: number;
}

export interface UpdateCorpusGroupInputs {
  /** Relay global ID of the group being edited. */
  corpusGroupId: string;
  title?: string;
  slug?: string;
  description?: string;
  /**
   * REPLACES the group's membership when provided, so the edit form always
   * sends the full desired set of relay global IDs — never a delta.
   */
  corpusIds?: string[];
  /**
   * Default-agent set/clear idiom. ``defaultAgentId`` and
   * ``clearDefaultAgent`` are MUTUALLY EXCLUSIVE: send a global ID to bind an
   * agent, or ``clearDefaultAgent: true`` to unbind. Never send both, and
   * never send an empty string — omitting both leaves the binding unchanged.
   */
  defaultAgentId?: string | null;
  /** See ``defaultAgentId`` — mutually exclusive with it. */
  clearDefaultAgent?: boolean;
  isPublic?: boolean;
  corporaLimit?: number;
}

export interface DeleteCorpusGroupInputs {
  corpusGroupId: string;
}

// ============================================================================
// GraphQL Operations
// ============================================================================

export const GET_MY_CORPUS_GROUPS = gql`
  query GetMyCorpusGroups($mine: Boolean, $corporaLimit: Int) {
    corpusGroups(mine: $mine) {
      totalCount
      edges {
        node {
          id
          title
          slug
          description
          isPublic
          created
          modified
          myPermissions
          creator {
            id
            displayName
          }
          defaultAgent {
            id
            name
          }
          corpora(first: $corporaLimit) {
            totalCount
            edges {
              node {
                id
                title
              }
            }
          }
        }
      }
    }
  }
`;

export const CREATE_CORPUS_GROUP = gql`
  mutation CreateCorpusGroup(
    $title: String!
    $slug: String
    $description: String
    $corpusIds: [ID]
    $defaultAgentId: ID
    $isPublic: Boolean
    $corporaLimit: Int
  ) {
    createCorpusGroup(
      title: $title
      slug: $slug
      description: $description
      corpusIds: $corpusIds
      defaultAgentId: $defaultAgentId
      isPublic: $isPublic
    ) {
      ok
      message
      corpusGroup {
        id
        title
        slug
        description
        isPublic
        created
        modified
        myPermissions
        creator {
          id
          displayName
        }
        defaultAgent {
          id
          name
        }
        corpora(first: $corporaLimit) {
          totalCount
          edges {
            node {
              id
              title
            }
          }
        }
      }
    }
  }
`;

export const UPDATE_CORPUS_GROUP = gql`
  mutation UpdateCorpusGroup(
    $corpusGroupId: ID!
    $title: String
    $slug: String
    $description: String
    $corpusIds: [ID]
    $defaultAgentId: ID
    $clearDefaultAgent: Boolean
    $isPublic: Boolean
    $corporaLimit: Int
  ) {
    updateCorpusGroup(
      corpusGroupId: $corpusGroupId
      title: $title
      slug: $slug
      description: $description
      corpusIds: $corpusIds
      defaultAgentId: $defaultAgentId
      clearDefaultAgent: $clearDefaultAgent
      isPublic: $isPublic
    ) {
      ok
      message
      corpusGroup {
        id
        title
        slug
        description
        isPublic
        created
        modified
        myPermissions
        creator {
          id
          displayName
        }
        defaultAgent {
          id
          name
        }
        corpora(first: $corporaLimit) {
          totalCount
          edges {
            node {
              id
              title
            }
          }
        }
      }
    }
  }
`;

export const DELETE_CORPUS_GROUP = gql`
  mutation DeleteCorpusGroup($corpusGroupId: ID!) {
    deleteCorpusGroup(corpusGroupId: $corpusGroupId) {
      ok
      message
    }
  }
`;
