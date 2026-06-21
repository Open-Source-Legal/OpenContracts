/**
 * Full integration wrapper for EnrichmentRunner + EnrichmentJobList CT tests.
 *
 * Mirrors AdminEnrichment's EnrichmentPanel: a single `useOptimisticRows` hook
 * owns the jobs query plus the optimistic-row lifecycle (prune effect +
 * ACTIVE_STATUSES guard), and feeds EnrichmentRunner.onRan / EnrichmentJobList
 * so tests exercise the real production behaviour.
 */
import React from "react";
import { MockedResponse, MockedProvider } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { ToastContainer } from "react-toastify";

import { EnrichmentRunner } from "../src/components/admin/enrichment/EnrichmentRunner";
import { EnrichmentJobList } from "../src/components/admin/enrichment/EnrichmentJobList";
import { useOptimisticRows } from "../src/components/admin/enrichment/useOptimisticRows";

export interface EnrichmentRunnerWrapperProps {
  corpusId: string;
  mocks?: MockedResponse[];
}

/**
 * Inner panel — mirrors EnrichmentPanel from AdminEnrichment via the shared
 * `useOptimisticRows` hook.
 */
const Panel: React.FC<{ corpusId: string }> = ({ corpusId }) => {
  const { jobs, optimistic, running, loading, error, handleRan } =
    useOptimisticRows(corpusId);

  return (
    <div style={{ padding: "1rem", maxWidth: 800 }}>
      <EnrichmentRunner
        corpusId={corpusId}
        onRan={handleRan}
        runningJobExists={running}
        compact
      />
      <div style={{ marginTop: "1.5rem" }}>
        <EnrichmentJobList
          jobs={jobs}
          loading={loading}
          error={error}
          extraJobs={optimistic}
        />
      </div>
    </div>
  );
};

/**
 * Full wrapper: EnrichmentRunner + EnrichmentJobList with MockedProvider.
 */
export const EnrichmentRunnerWrapperFull: React.FC<
  EnrichmentRunnerWrapperProps
> = ({ corpusId, mocks = [] }) => (
  <MemoryRouter>
    <MockedProvider mocks={mocks} addTypename={false}>
      {/* Single child: MockedProvider uses React.Children.only, so the
          ToastContainer (added so tests can assert react-toastify warning /
          success notifications) and the Panel must share one parent. */}
      <>
        <ToastContainer />
        <Panel corpusId={corpusId} />
      </>
    </MockedProvider>
  </MemoryRouter>
);
