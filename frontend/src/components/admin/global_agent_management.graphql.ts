import { gql } from "@apollo/client";

/**
 * Shared GraphQL documents for GlobalAgentManagement. Exported so both the
 * admin view and its Playwright CT tests reference one source of truth — a
 * field rename on the component side will break the mocks at type-check
 * time instead of silently masking a mismatched query.
 *
 * These are intentionally separate from the corpus-scoped agent operations
 * in `src/graphql/{queries,mutations}.ts`: the global form omits `slug` and
 * `corpusId`, and trims the selection set to what the admin list needs.
 *
 * NOTE: `scope` is the `AgentsAgentConfigurationScopeChoices` GraphQL enum
 * (graphene-django derives it from the `AgentConfiguration.scope` model
 * choices). It must be written as the bare enum literal `GLOBAL` — a quoted
 * string `"GLOBAL"` fails query validation with
 * `Argument 'scope' has invalid value "GLOBAL"` (issue #1750).
 */
export const GET_GLOBAL_AGENTS = gql`
  query GetGlobalAgents {
    agentConfigurations(scope: GLOBAL) {
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
            username
          }
          created
          modified
        }
      }
    }
  }
`;

export const CREATE_GLOBAL_AGENT_CONFIGURATION = gql`
  mutation CreateGlobalAgentConfiguration(
    $name: String!
    $description: String!
    $systemInstructions: String!
    $availableTools: [String]
    $permissionRequiredTools: [String]
    $badgeConfig: JSONString
    $avatarUrl: String
    $scope: String!
    $isPublic: Boolean
  ) {
    createAgentConfiguration(
      name: $name
      description: $description
      systemInstructions: $systemInstructions
      availableTools: $availableTools
      permissionRequiredTools: $permissionRequiredTools
      badgeConfig: $badgeConfig
      avatarUrl: $avatarUrl
      scope: $scope
      isPublic: $isPublic
    ) {
      ok
      message
      agent {
        id
        name
        slug
        description
      }
    }
  }
`;

export const UPDATE_GLOBAL_AGENT_CONFIGURATION = gql`
  mutation UpdateGlobalAgentConfiguration(
    $agentId: ID!
    $name: String
    $description: String
    $systemInstructions: String
    $availableTools: [String]
    $permissionRequiredTools: [String]
    $badgeConfig: JSONString
    $avatarUrl: String
    $isActive: Boolean
    $isPublic: Boolean
  ) {
    updateAgentConfiguration(
      agentId: $agentId
      name: $name
      description: $description
      systemInstructions: $systemInstructions
      availableTools: $availableTools
      permissionRequiredTools: $permissionRequiredTools
      badgeConfig: $badgeConfig
      avatarUrl: $avatarUrl
      isActive: $isActive
      isPublic: $isPublic
    ) {
      ok
      message
      agent {
        id
        name
        slug
        description
      }
    }
  }
`;

export const DELETE_GLOBAL_AGENT_CONFIGURATION = gql`
  mutation DeleteGlobalAgentConfiguration($agentId: ID!) {
    deleteAgentConfiguration(agentId: $agentId) {
      ok
      message
    }
  }
`;
