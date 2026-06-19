/**
 * Full integration wrapper for EnrichmentRunner + EnrichmentJobList CT tests.
 *
 * Mirrors AdminEnrichment's EnrichmentPanel: EnrichmentRunner.onRan feeds
 * optimistic rows into EnrichmentJobList.extraJobs.  Also mirrors the pruning
 * effect and ACTIVE_STATUSES guard introduced in the Fix-A / Fix-B patches so
 * tests exercise the real behaviour.
 */
import React, { useEffect, useState } from "react";
import { MockedResponse, MockedProvider } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";

import { EnrichmentRunner } from "../src/components/admin/enrichment/EnrichmentRunner";
import { EnrichmentJobList } from "../src/components/admin/enrichment/EnrichmentJobList";
import {
  useEnrichmentJobs,
  ACTIVE_STATUSES,
} from "../src/components/admin/enrichment/useEnrichmentJobs";

import type { EnrichmentAnalysisRow } from "../src/graphql/mutations";

export interface EnrichmentRunnerWrapperProps {
  corpusId: string;
  mocks?: MockedResponse[];
}

/**
 * Inner panel — mirrors EnrichmentPanel from AdminEnrichment, including the
 * Fix-A pruning effect and Fix-B ACTIVE_STATUSES guard.  Extracted so all
 * hooks are called unconditionally (no conditional hook calls).
 */
const Panel: React.FC<{ corpusId: string }> = ({ corpusId }) => {
  const { jobs, refetch } = useEnrichmentJobs(corpusId);
  const [extraJobs, setExtraJobs] = useState<EnrichmentAnalysisRow[]>([]);

  // Fix-A: prune optimistic rows that have been superseded by a real refetch.
  useEffect(() => {
    if (!extraJobs.length) return;
    const ids = new Set(jobs.map((j) => j.id));
    if (extraJobs.some((o) => ids.has(o.id))) {
      setExtraJobs((prev) => prev.filter((o) => !ids.has(o.id)));
    }
  }, [jobs]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fix-B: check both fetched and optimistic rows against ACTIVE_STATUSES
  // (imported from the hook so the wrapper can't drift from production).
  const runningJobExists = [...jobs, ...extraJobs].some((j) =>
    ACTIVE_STATUSES.includes(j.status ?? "")
  );

  return (
    <div style={{ padding: "1rem", maxWidth: 800 }}>
      <EnrichmentRunner
        corpusId={corpusId}
        onRan={(rows) => {
          setExtraJobs((prev) => [...rows, ...prev]);
          refetch();
        }}
        runningJobExists={runningJobExists}
        compact
      />
      <div style={{ marginTop: "1.5rem" }}>
        <EnrichmentJobList corpusId={corpusId} extraJobs={extraJobs} />
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
      <Panel corpusId={corpusId} />
    </MockedProvider>
  </MemoryRouter>
);
