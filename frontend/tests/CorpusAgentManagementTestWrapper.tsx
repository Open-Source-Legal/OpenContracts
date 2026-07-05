import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { Provider as JotaiProvider } from "jotai";
import { ToastContainer } from "react-toastify";
import { CorpusAgentManagement } from "../src/components/corpuses/CorpusAgentManagement";
import { GET_LLM_PROVIDERS } from "../src/graphql/queries";

interface Props {
  mocks: ReadonlyArray<MockedResponse>;
  corpusId: string;
  canUpdate?: boolean;
  corpusPreferredLlm?: string | null;
}

// The component fires this (when canUpdate) to power the Preferred LLM
// picker's chip list. Appended AFTER the test-supplied mocks so a test that
// cares about specific provider data can declare its own mock (matched
// first); everything else gets a harmless empty-providers fallback instead of
// a "no more mocked responses" console error.
const defaultLlmProvidersMock: MockedResponse = {
  request: { query: GET_LLM_PROVIDERS },
  result: { data: { pipelineComponents: { llmProviders: [] } } },
};

/**
 * Wrapper for CorpusAgentManagement CT tests.
 *
 * The component fetches GET_CORPUS_AGENTS, GET_AVAILABLE_TOOLS, and (when
 * `canUpdate`) GET_LLM_PROVIDERS on mount; `canUpdate=false` short-circuits to
 * a permissioning notice and skips all three.
 */
export const CorpusAgentManagementTestWrapper: React.FC<Props> = ({
  mocks,
  corpusId,
  canUpdate = true,
  corpusPreferredLlm,
}) => {
  // Defined inside the wrapper so Playwright CT's per-test serialization
  // never reaches an Apollo cache instance — see CLAUDE.md pitfall #8.
  const cache = new InMemoryCache({ addTypename: false });
  return (
    <JotaiProvider>
      <MockedProvider
        mocks={[...mocks, defaultLlmProvidersMock]}
        addTypename={false}
        cache={cache}
      >
        <div style={{ width: "100vw", padding: 16 }}>
          <CorpusAgentManagement
            corpusId={corpusId}
            canUpdate={canUpdate}
            corpusPreferredLlm={corpusPreferredLlm}
          />
          <ToastContainer />
        </div>
      </MockedProvider>
    </JotaiProvider>
  );
};
