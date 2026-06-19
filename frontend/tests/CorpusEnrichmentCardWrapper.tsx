/**
 * Test wrapper for CorpusEnrichmentCard CT tests.
 *
 * Lives in its own file (separate from the .ct.tsx) so Playwright CT's babel
 * transform creates a unique importRef for the JSX component, and so the
 * useEnrichmentJobs -> get_websockets import chain is evaluated through the
 * Vite transform (importing the hook directly from a .ct.tsx Node loader
 * triggers "exports is not defined").
 */
import React from "react";
import { MockedResponse, MockedProvider } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";

import { CorpusEnrichmentCard } from "../src/components/corpuses/CorpusHome/intelligence/CorpusEnrichmentCard";

export interface CorpusEnrichmentCardWrapperProps {
  corpusId: string;
  canUpdate: boolean;
  mocks?: MockedResponse[];
}

export const CorpusEnrichmentCardWrapper: React.FC<
  CorpusEnrichmentCardWrapperProps
> = ({ corpusId, canUpdate, mocks = [] }) => (
  <MockedProvider mocks={mocks} addTypename={false}>
    <MemoryRouter>
      <div style={{ padding: "1rem", maxWidth: 480 }}>
        <CorpusEnrichmentCard corpusId={corpusId} canUpdate={canUpdate} />
      </div>
    </MemoryRouter>
  </MockedProvider>
);
