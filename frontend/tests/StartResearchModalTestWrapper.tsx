import React from "react";
import { MockedProvider } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { Provider } from "jotai";
import { MemoryRouter } from "react-router-dom";
import { toGlobalId } from "../src/utils/idValidation";
import { StartResearchModal } from "../src/components/widgets/modals/StartResearchModal";

export const CORPUS_ID = toGlobalId("CorpusType", 1);

/**
 * Mounts StartResearchModal open, with the ApolloProvider (for the
 * START_RESEARCH_REPORT mutation hook) and a Router (for useNavigate). No
 * mutation mocks are supplied: this is a render/smoke wrapper and the test does
 * not submit, so the useMutation hook only needs an Apollo context to exist.
 */
export const StartResearchModalTestWrapper: React.FC = () => (
  <Provider>
    <MemoryRouter>
      <MockedProvider
        mocks={[]}
        cache={new InMemoryCache({ addTypename: false })}
        addTypename={false}
      >
        <StartResearchModal corpusId={CORPUS_ID} open onClose={() => {}} />
      </MockedProvider>
    </MemoryRouter>
  </Provider>
);
