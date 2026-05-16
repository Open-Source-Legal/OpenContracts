/**
 * Test helper for building the five `MockedResponse` objects that
 * `useUnifiedMentionSearch` fires in parallel for a single fragment.
 *
 * The hook (frontend/src/components/threads/hooks/useUnifiedMentionSearch.ts)
 * dispatches one query per resource category (users, corpuses, documents,
 * annotations, agents) after a 300ms debounce and once the fragment has at
 * least `MENTION_SEARCH_MIN_CHARS` characters. The Apollo `MockedProvider`
 * needs an exact match per query+variables — so even when only the agent
 * results are interesting, the other four categories must resolve to empty
 * edges or the mock will throw "no more mocked responses".
 *
 * Shared by ChatTray.ct.tsx and CorpusChat.ct.tsx (Task 11). Keep this helper
 * here so both surfaces stay in lockstep — if the hook ever fans out to a new
 * category, this is the only file that needs to grow.
 */
import { MockedResponse } from "@apollo/client/testing";
import {
  SEARCH_USERS_FOR_MENTION,
  SEARCH_CORPUSES_FOR_MENTION,
  SEARCH_DOCUMENTS_FOR_MENTION,
  SEARCH_ANNOTATIONS_FOR_MENTION,
  SEARCH_AGENTS_FOR_MENTION,
} from "../../src/graphql/queries";

export interface MentionAgentNode {
  id: string;
  name: string;
  slug: string;
  description: string;
  scope: "GLOBAL" | "CORPUS";
  mentionFormat: string | null;
  corpus: { id: string; slug: string; title: string } | null;
}

/**
 * Build the five MockedResponses that `useUnifiedMentionSearch` fires in
 * parallel for a single fragment. Only agent results carry data; users,
 * corpuses, documents, and annotations resolve to empty edges so the picker
 * surfaces agent-only suggestions.
 */
export function buildMentionSearchMocks(
  fragment: string,
  corpusId: string | undefined,
  agentNodes: MentionAgentNode[]
): MockedResponse[] {
  return [
    {
      request: {
        query: SEARCH_USERS_FOR_MENTION,
        variables: { textSearch: fragment },
      },
      result: {
        data: { searchUsersForMention: { edges: [] } },
      },
    },
    {
      request: {
        query: SEARCH_CORPUSES_FOR_MENTION,
        variables: { textSearch: fragment },
      },
      result: {
        data: { searchCorpusesForMention: { edges: [] } },
      },
    },
    {
      request: {
        query: SEARCH_DOCUMENTS_FOR_MENTION,
        variables: { textSearch: fragment, corpusId },
      },
      result: {
        data: { searchDocumentsForMention: { edges: [] } },
      },
    },
    {
      request: {
        query: SEARCH_ANNOTATIONS_FOR_MENTION,
        variables: { textSearch: fragment, corpusId },
      },
      result: {
        data: { searchAnnotationsForMention: { edges: [] } },
      },
    },
    {
      request: {
        query: SEARCH_AGENTS_FOR_MENTION,
        variables: { textSearch: fragment, corpusId },
      },
      result: {
        data: {
          searchAgentsForMention: {
            __typename: "AgentConfigurationTypeConnection",
            edges: agentNodes.map((node) => ({
              __typename: "AgentConfigurationTypeEdge",
              node: { __typename: "AgentConfigurationType", ...node },
            })),
          },
        },
      },
    },
  ];
}
