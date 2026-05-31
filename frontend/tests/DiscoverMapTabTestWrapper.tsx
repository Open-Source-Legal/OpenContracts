import React from "react";
import { MockedResponse } from "@apollo/client/testing";
import { MockedProvider } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { DiscoverSearchResults } from "../src/views/DiscoverSearchResults";

/**
 * Test wrapper for the Discover "Map" tab.
 *
 * Boots the DiscoverSearchResults view at `/discover?type=map` so the Map tab
 * is active on mount (the view reads the active tab from the `type` query
 * param). Provides Apollo mocks (for `globalGeographicAnnotations`)
 * and a router (the view uses `useSearchParams` / `useNavigate`). The
 * InMemoryCache stays inside MockedProvider (CLAUDE.md pitfall #8).
 *
 * Per CLAUDE.md pitfall #16, the `.ct.tsx` imports this wrapper component in
 * its own import statement.
 */
export const DiscoverMapTabTestWrapper: React.FC<{
  mocks?: MockedResponse[];
}> = ({ mocks }) => {
  return (
    <MockedProvider mocks={mocks ?? []} addTypename={false}>
      <MemoryRouter initialEntries={["/discover?type=map"]}>
        <DiscoverSearchResults />
      </MemoryRouter>
    </MockedProvider>
  );
};
