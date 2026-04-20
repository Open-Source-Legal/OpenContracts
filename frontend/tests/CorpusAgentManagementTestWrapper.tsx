import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { Provider as JotaiProvider } from "jotai";
import { ToastContainer } from "react-toastify";
import { CorpusAgentManagement } from "../src/components/corpuses/CorpusAgentManagement";

interface Props {
  mocks: ReadonlyArray<MockedResponse>;
  corpusId: string;
  canUpdate?: boolean;
}

/**
 * Wrapper for CorpusAgentManagement CT tests.
 *
 * The component fetches GET_CORPUS_AGENTS and GET_AVAILABLE_TOOLS on mount;
 * `canUpdate=false` short-circuits to a permissioning notice and skips both.
 */
export const CorpusAgentManagementTestWrapper: React.FC<Props> = ({
  mocks,
  corpusId,
  canUpdate = true,
}) => {
  // Defined inside the wrapper so Playwright CT's per-test serialization
  // never reaches an Apollo cache instance — see CLAUDE.md pitfall #8.
  const cache = new InMemoryCache({ addTypename: false });
  return (
    <JotaiProvider>
      <MockedProvider mocks={mocks} addTypename={false} cache={cache}>
        <div style={{ width: "100vw", padding: 16 }}>
          <CorpusAgentManagement corpusId={corpusId} canUpdate={canUpdate} />
          <ToastContainer />
        </div>
      </MockedProvider>
    </JotaiProvider>
  );
};
