/**
 * Bare test wrapper for EnrichmentRunner (no job list).
 * Used for prop-only tests that need only the run form.
 */
import React from "react";
import { MockedResponse, MockedProvider } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";

import { EnrichmentRunner } from "../src/components/admin/enrichment/EnrichmentRunner";

/** Renders just the EnrichmentRunner form without EnrichmentJobList. */
export const BareEnrichmentRunnerWrapper: React.FC<{
  corpusId: string;
  mocks?: MockedResponse[];
  runningJobExists?: boolean;
}> = ({ corpusId, mocks = [], runningJobExists = false }) => (
  <MemoryRouter>
    <MockedProvider mocks={mocks} addTypename={false}>
      <EnrichmentRunner
        corpusId={corpusId}
        runningJobExists={runningJobExists}
        compact
      />
    </MockedProvider>
  </MemoryRouter>
);
