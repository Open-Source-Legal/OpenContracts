import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { CorpusMapView } from "../src/components/corpuses/CorpusMapView";
import { CorpusType } from "../src/types/graphql-api";
import { corpusMapPin } from "../src/graphql/cache";

/** Relay global id used by the corpus-scoped geo query mocks in the .ct file. */
export const CORPUS_MAP_TEST_CORPUS_ID = "Q29ycHVzVHlwZToxMjM=";

/**
 * Test wrapper for {@link CorpusMapView} (issue #1821).
 *
 * Mounting the view directly (rather than the whole CorpusHome) keeps the test
 * fast: it exercises the real corpus geo query → AnnotationMap data flow.
 * CorpusMapView needs Apollo (the query) and a Router (useNavigate/useLocation),
 * so it mounts inside MockedProvider + MemoryRouter. The deep-link place is
 * seeded into the `corpusMapPin` reactive var the same way CentralRouteManager
 * Phase 2 would, so the focus is applied on first paint.
 *
 * The map needs a definite-height ancestor for its height:100% to resolve, so
 * the view is wrapped in a fixed-size flex box (mirroring the real corpus
 * layout that gives CorpusHome its height).
 *
 * Per CLAUDE.md pitfall #16, the `.ct.tsx` imports this component in its own
 * import statement, separate from the exported constant / helper imports.
 */
export const CorpusMapViewTestWrapper: React.FC<{
  mocks?: MockedResponse[];
  /** Deep-linked place name (seeds `corpusMapPin`); null for the default view. */
  focusPin?: string | null;
}> = ({ mocks, focusPin = null }) => {
  // Seed the URL-driven reactive var synchronously before render so the map's
  // deep-link focus is in place on first paint (and reset between tests).
  corpusMapPin(focusPin);

  const corpus = { id: CORPUS_MAP_TEST_CORPUS_ID } as unknown as CorpusType;

  return (
    <MockedProvider mocks={mocks ?? []} addTypename={false}>
      <MemoryRouter>
        <div style={{ height: "640px", width: "960px", display: "flex" }}>
          <CorpusMapView corpus={corpus} onBack={() => {}} />
        </div>
      </MemoryRouter>
    </MockedProvider>
  );
};
