import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { CorpusMapToggle } from "../src/components/corpuses/CorpusHome/CorpusMapToggle";

/** Relay global id used by the corpus-scoped geo query mocks in the .ct file. */
export const CORPUS_MAP_TOGGLE_TEST_CORPUS_ID = "Q29ycHVzVHlwZTo0NTY=";

/**
 * Test wrapper for {@link CorpusMapToggle} (issue #1821).
 *
 * The toggle is a passive badge that only needs Apollo (it issues the shared
 * `geographicAnnotationsForCorpus` count query via `useQuery`); it has no router
 * or Jotai dependency, so MockedProvider alone is sufficient. Mounting it on its
 * own keeps the badge-state assertions (loaded / empty / loading) fast and free
 * of the full CorpusLandingView render.
 *
 * Per CLAUDE.md pitfall #16, the `.ct.tsx` imports this component in its own
 * import statement, separate from the exported constant import.
 */
export const CorpusMapToggleTestWrapper: React.FC<{
  mocks?: MockedResponse[];
}> = ({ mocks }) => (
  <MockedProvider mocks={mocks ?? []} addTypename={false}>
    <CorpusMapToggle
      corpusId={CORPUS_MAP_TOGGLE_TEST_CORPUS_ID}
      onClick={() => {}}
    />
  </MockedProvider>
);
