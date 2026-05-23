import React, { useEffect } from "react";
import { Provider, useSetAtom } from "jotai";

import { MobileFindSheet } from "../src/components/knowledge_base/document/layouts/mobile/MobileFindSheet";
import { textSearchStateAtom } from "../src/components/annotator/context/DocumentAtom";

/**
 * Seeds the text-search atom so {@link MobileFindSheet}'s populated-matches
 * path (status line, prev/next stepping) can be exercised without mounting
 * the full document text-search machinery.
 */
const MatchSeeder: React.FC<{ matchCount: number }> = ({ matchCount }) => {
  const setTextSearchState = useSetAtom(textSearchStateAtom);
  useEffect(() => {
    setTextSearchState({
      matches: Array.from({ length: matchCount }, () => ({})),
      selectedIndex: 0,
    } as unknown as { matches: never[]; selectedIndex: number });
  }, [matchCount, setTextSearchState]);
  return null;
};

/**
 * Test harness for {@link MobileFindSheet}. Each mount gets an isolated Jotai
 * store so seeded search state does not leak between tests.
 */
export const MobileFindSheetHarness: React.FC<{
  open?: boolean;
  matchCount?: number;
}> = ({ open = true, matchCount = 0 }) => (
  <Provider>
    <MatchSeeder matchCount={matchCount} />
    <MobileFindSheet open={open} />
  </Provider>
);
