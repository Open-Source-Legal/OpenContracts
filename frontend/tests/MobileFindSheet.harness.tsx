import React, { useEffect } from "react";
import { Provider, useSetAtom } from "jotai";

import { MobileFindSheet } from "../src/components/knowledge_base/document/layouts/mobile/MobileFindSheet";
import { textSearchStateAtom } from "../src/components/annotator/context/DocumentAtom";
import type {
  TextSearchSpanResult,
  TextSearchTokenResult,
} from "../src/components/types";

/**
 * Builds a synthetic token-style match (the PDF path). Each match gets a unique
 * id, a non-null React `fullContext` (so the result row has a snippet to
 * render) and page bounds the row meta line formats as "Page N".
 */
const makeTokenMatch = (id: number): TextSearchTokenResult => ({
  id,
  tokens: {},
  fullContext: React.createElement(
    "span",
    null,
    "fixture match ",
    React.createElement("mark", { key: "m" }, "clause"),
    ` #${id + 1}`
  ),
  start_page: 0,
  end_page: 0,
});

/**
 * Builds a synthetic span-style match (the TXT path). Carries a `text`
 * fallback the row uses when `fullContext` is null.
 */
const makeSpanMatch = (id: number): TextSearchSpanResult => ({
  id,
  start_index: id * 10,
  end_index: id * 10 + 6,
  fullContext: React.createElement(
    "span",
    null,
    "span match ",
    React.createElement("mark", { key: "m" }, "clause"),
    ` #${id + 1}`
  ),
  text: `span match clause #${id + 1}`,
});

/**
 * Seeds the text-search atom so {@link MobileFindSheet}'s populated-matches
 * path (status line, prev/next stepping, the new results list) can be
 * exercised without mounting the full document text-search machinery.
 */
const MatchSeeder: React.FC<{
  matchCount: number;
  matchType: "token" | "span";
}> = ({ matchCount, matchType }) => {
  const setTextSearchState = useSetAtom(textSearchStateAtom);
  useEffect(() => {
    const matches = Array.from({ length: matchCount }, (_, i) =>
      matchType === "token" ? makeTokenMatch(i) : makeSpanMatch(i)
    );
    setTextSearchState({
      matches: matches as (TextSearchTokenResult | TextSearchSpanResult)[],
      selectedIndex: 0,
    });
  }, [matchCount, matchType, setTextSearchState]);
  return null;
};

/**
 * Test harness for {@link MobileFindSheet}. Each mount gets an isolated Jotai
 * store so seeded search state does not leak between tests.
 */
export const MobileFindSheetHarness: React.FC<{
  open?: boolean;
  matchCount?: number;
  matchType?: "token" | "span";
  onClose?: () => void;
}> = ({ open = true, matchCount = 0, matchType = "token", onClose }) => (
  <Provider>
    <MatchSeeder matchCount={matchCount} matchType={matchType} />
    <MobileFindSheet open={open} onClose={onClose} />
  </Provider>
);
