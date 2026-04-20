import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { Provider as JotaiProvider } from "jotai";
import { ToastContainer } from "react-toastify";
import {
  CreateCorpusActionModal,
  CorpusActionData,
} from "../src/components/corpuses/CreateCorpusActionModal";

interface Props {
  mocks: ReadonlyArray<MockedResponse>;
  corpusId: string;
  open?: boolean;
  onClose?: () => void;
  onSuccess?: () => void;
  actionToEdit?: CorpusActionData | null;
}

/**
 * Wrapper for CreateCorpusActionModal CT tests.
 *
 * The modal queries fieldsets, analyzers, agent configurations and the
 * trigger-appropriate available tools (moderation or document) on mount,
 * so callers must supply the matching mocks.
 */
export const CreateCorpusActionModalTestWrapper: React.FC<Props> = ({
  mocks,
  corpusId,
  open = true,
  onClose = () => {},
  onSuccess = () => {},
  actionToEdit = null,
}) => {
  // Per CLAUDE.md pitfall #8, keep cache inside the wrapper so Playwright's
  // per-test serialization never crosses an Apollo cache instance.
  const cache = new InMemoryCache({ addTypename: false });
  return (
    <JotaiProvider>
      <MockedProvider mocks={mocks} addTypename={false} cache={cache}>
        <div style={{ width: "100vw", height: "100vh" }}>
          <CreateCorpusActionModal
            corpusId={corpusId}
            open={open}
            onClose={onClose}
            onSuccess={onSuccess}
            actionToEdit={actionToEdit}
          />
          <ToastContainer />
        </div>
      </MockedProvider>
    </JotaiProvider>
  );
};
