/**
 * Test wrapper for the AdminEnrichment page.
 *
 * Mirrors IngestionMonitorTestWrapper: seeds the `backendUserObj` reactive var
 * (which drives the superuser access gate) in a useEffect and tears it down on
 * unmount. A fresh InMemoryCache per mount keeps type policies from bleeding
 * between tests. Lives in its own file for the Playwright CT split-import rule
 * (CLAUDE.md #16).
 */
import React, { useEffect } from "react";
import { InMemoryCache } from "@apollo/client";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";

import { backendUserObj } from "../src/graphql/cache";
import { AdminEnrichment } from "../src/components/admin/AdminEnrichment";

interface WrapperProps {
  mocks?: MockedResponse[];
  /**
   * Seeded current user. `null` simulates the not-yet-resolved state
   * (`currentUser === null` → the page renders nothing).
   */
  user?: { isSuperuser: boolean } | null;
}

export const AdminEnrichmentWrapper: React.FC<WrapperProps> = ({
  mocks = [],
  user = { isSuperuser: true },
}) => {
  useEffect(() => {
    backendUserObj(user as any);
    return () => {
      backendUserObj(null);
    };
  }, [user]);

  return (
    <MockedProvider
      mocks={mocks}
      addTypename={false}
      cache={new InMemoryCache({ addTypename: false })}
    >
      <MemoryRouter initialEntries={["/admin/enrichment"]}>
        <AdminEnrichment />
      </MemoryRouter>
    </MockedProvider>
  );
};
