import React, { useEffect } from "react";
import { MockedResponse, MockedProvider } from "@apollo/client/testing";
import { MemoryRouter, useLocation } from "react-router-dom";

import { IntelligencePanel } from "../src/components/corpuses/CorpusHome/intelligence/IntelligencePanel";
import { openedCorpus } from "../src/graphql/cache";
import { CorpusType } from "../src/types/graphql-api";

interface IntelligencePanelCorpusContextTestWrapperProps {
  corpusId: string;
  corpus: CorpusType;
  mocks: MockedResponse[];
}

const LocationProbe: React.FC = () => {
  const location = useLocation();
  return (
    <div data-testid="router-location" style={{ display: "none" }}>
      {location.pathname + location.search}
    </div>
  );
};

/** Browser-side harness for corpus-aware collection-index navigation. */
export const IntelligencePanelCorpusContextTestWrapper: React.FC<
  IntelligencePanelCorpusContextTestWrapperProps
> = ({ corpusId, corpus, mocks }) => {
  useEffect(() => {
    openedCorpus(corpus);
    return () => openedCorpus(null);
  }, [corpus]);

  return (
    <MemoryRouter initialEntries={["/c/corpus-owner/cross-doc100"]}>
      <MockedProvider mocks={mocks} addTypename={false}>
        <IntelligencePanel corpusId={corpusId} />
      </MockedProvider>
      <LocationProbe />
    </MemoryRouter>
  );
};
