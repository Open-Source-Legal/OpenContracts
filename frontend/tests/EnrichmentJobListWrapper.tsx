/**
 * Test wrapper for EnrichmentJobList.
 *
 * EnrichmentJobList is purely presentational (it takes jobs as props and fires
 * no queries of its own), but it is wrapped in MemoryRouter + MockedProvider
 * here to mirror the production provider stack and stay consistent with the
 * other enrichment CT wrappers. Lives in its own file so Playwright CT's babel
 * transform creates a unique importRef (split-import rule, CLAUDE.md #16).
 */
import React from "react";
import { MockedProvider } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import type { ApolloError } from "@apollo/client";

import { EnrichmentJobList } from "../src/components/admin/enrichment/EnrichmentJobList";
import type { EnrichmentAnalysisRow } from "../src/graphql/mutations";

export const EnrichmentJobListWrapper: React.FC<{
  jobs: EnrichmentAnalysisRow[];
  loading?: boolean;
  error?: ApolloError;
  extraJobs?: EnrichmentAnalysisRow[];
}> = ({ jobs, loading, error, extraJobs }) => (
  <MemoryRouter>
    <MockedProvider mocks={[]} addTypename={false}>
      <div style={{ padding: "1rem", maxWidth: 800 }}>
        <EnrichmentJobList
          jobs={jobs}
          loading={loading}
          error={error}
          extraJobs={extraJobs}
        />
      </div>
    </MockedProvider>
  </MemoryRouter>
);
