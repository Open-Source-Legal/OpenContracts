import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { DiscoverMapPanel } from "../src/components/maps/DiscoverMapPanel";
import {
  MAP_DEFAULT_CENTER,
  MAP_DEFAULT_ZOOM,
} from "../src/assets/configurations/constants";

/**
 * Test wrapper for {@link DiscoverMapPanel} — the Discover-specific data unit
 * that wires `globalGeographicAnnotations` into the reusable map.
 *
 * Mounting the panel directly (rather than the whole DiscoverSearchResults
 * view) keeps the test fast and deterministic: it exercises the real query →
 * AnnotationMap data flow without dragging in the heavy `@os-legal/ui` view
 * shell. AnnotationMap needs a Router (`useNavigate`); the panel needs Apollo,
 * so it mounts inside MockedProvider (which supplies its own default cache).
 *
 * Per CLAUDE.md pitfall #16, the `.ct.tsx` imports this wrapper component in
 * its own import statement.
 */
export const DiscoverMapPanelTestWrapper: React.FC<{
  mocks?: MockedResponse[];
}> = ({ mocks }) => {
  return (
    <MockedProvider mocks={mocks ?? []} addTypename={false}>
      <MemoryRouter>
        <DiscoverMapPanel
          initialView={{
            center: [...MAP_DEFAULT_CENTER] as [number, number],
            zoom: MAP_DEFAULT_ZOOM,
          }}
        />
      </MemoryRouter>
    </MockedProvider>
  );
};
