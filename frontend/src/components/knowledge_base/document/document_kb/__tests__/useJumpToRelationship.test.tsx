/**
 * Unit tests for ``useJumpToRelationship``.
 *
 * Issue #1645: the hook wires the ``?rel=<pk>`` URL param to the doc
 * viewer's relation-selection plumbing. URL carries a raw Django PK
 * while ``RelationGroup.id`` is a Relay global ID, so the hook must
 * compare on numeric IDs — these tests pin that bridge.
 */

import * as React from "react";
import { Provider as JotaiProvider, createStore } from "jotai";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

// useJumpToRelationship reads ``annotationElementRefs`` from
// ``useAnnotationRefs`` to drive scrollIntoView. The default test does not
// have a virtualised PDF mounted, so we surface a controllable refs map.
// ``annotationRefsForTests`` is mutated by individual tests below.
const annotationRefsForTests: {
  current: Record<string, { scrollIntoView: ReturnType<typeof vi.fn> } | null>;
} = { current: {} };

vi.mock("../../../../annotator/hooks/useAnnotationRefs", () => ({
  useAnnotationRefs: () => ({
    annotationElementRefs: annotationRefsForTests,
  }),
}));

import { renderHook, waitFor } from "../../../../../test-utils/renderHook";
import { useJumpToRelationship } from "../useJumpToRelationship";
import { selectedRelationshipId } from "../../../../../graphql/cache";
import { structuralRelationshipsAtom } from "../../../../annotator/context/AnnotationAtoms";
import {
  selectedRelationsAtom,
  hoveredAnnotationIdAtom,
} from "../../../../annotator/context/UISettingsAtom";
import { RelationGroup } from "../../../../annotator/types/annotations";
import { AnnotationLabelType } from "../../../../../types/graphql-api";
import { JUMP_TO_RELATIONSHIP_SCROLL_RETRY_MS } from "../../../../../assets/configurations/constants";

const RELAY_PK = 42;
// btoa("Relationship:42") — what the GraphQL query actually returns.
const RELAY_GLOBAL_ID = btoa(`Relationship:${RELAY_PK}`);

const baseLabel: AnnotationLabelType = {
  id: "lbl",
  text: "rel-label",
  color: "#000",
  icon: "",
  description: "",
  labelType: "RELATIONSHIP_LABEL" as AnnotationLabelType["labelType"],
};

function makeRelationGroup(id: string): RelationGroup {
  return new RelationGroup(["ann-1"], ["ann-2", "ann-3"], baseLabel, id, true);
}

function createWrapper(store: ReturnType<typeof createStore>) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <JotaiProvider store={store}>{children}</JotaiProvider>;
  };
}

describe("useJumpToRelationship", () => {
  let store: ReturnType<typeof createStore>;
  const cleanups: Array<() => void> = [];

  function renderJumpHook() {
    const result = renderHook(() => useJumpToRelationship(), {
      wrapper: createWrapper(store),
    });
    cleanups.push(result.unmount);
    return result;
  }

  beforeEach(() => {
    store = createStore();
    selectedRelationshipId(null);
    annotationRefsForTests.current = {};
  });

  afterEach(() => {
    // Unmount any hook instances before resetting the reactive var, so a
    // pending effect on the OLD store doesn't re-fire against the NEW
    // store's atom state in the next test (causes shared-spy double-counts).
    while (cleanups.length > 0) {
      const dispose = cleanups.pop();
      dispose?.();
    }
    selectedRelationshipId(null);
    annotationRefsForTests.current = {};
  });

  it("is a no-op when ?rel= is unset", () => {
    renderJumpHook();
    // Nothing should have been selected.
    expect(store.get(selectedRelationsAtom)).toEqual([]);
    expect(store.get(hoveredAnnotationIdAtom)).toBeNull();
  });

  it("does not match when relId is set but no relations are loaded yet", async () => {
    selectedRelationshipId(String(RELAY_PK));
    renderJumpHook();
    // Falling out cleanly — selection stays empty.
    expect(store.get(selectedRelationsAtom)).toEqual([]);
  });

  it("matches a RelationGroup whose Relay global ID decodes to the URL PK", async () => {
    // Seed the upstream atom that ``allRelationsAtom`` reads from. The hook
    // resolves the URL PK against the numeric portion of the Relay ID.
    store.set(structuralRelationshipsAtom, [
      makeRelationGroup(RELAY_GLOBAL_ID),
    ]);
    selectedRelationshipId(String(RELAY_PK));

    renderJumpHook();

    await waitFor(() => store.get(selectedRelationsAtom).length === 1);
    const selected = store.get(selectedRelationsAtom);
    expect(selected).toHaveLength(1);
    expect(selected[0].id).toBe(RELAY_GLOBAL_ID);
  });

  it("does NOT match a raw-PK string against a Relay-encoded RelationGroup.id (regression)", async () => {
    // This is the bug fixed in this PR: a naive ``r.id === relId`` compare
    // would silently fail because the raw PK ("42") never equals the Relay
    // global ID ("UmVsYXRpb25zaGlwOjQy"). The hook must decode the latter.
    // If anyone re-introduces the bug, this test fails because nothing is
    // selected even though the URL is set.
    store.set(structuralRelationshipsAtom, [
      makeRelationGroup(RELAY_GLOBAL_ID),
    ]);
    selectedRelationshipId(String(RELAY_PK));

    renderJumpHook();

    await waitFor(() => store.get(selectedRelationsAtom).length === 1);
    expect(store.get(selectedRelationsAtom)).toHaveLength(1);
  });

  it("falls back gracefully when relId is non-numeric", () => {
    store.set(structuralRelationshipsAtom, [
      makeRelationGroup(RELAY_GLOBAL_ID),
    ]);
    selectedRelationshipId("not-a-number");

    renderJumpHook();

    expect(store.get(selectedRelationsAtom)).toEqual([]);
  });

  it("clears the selected relation AND hover indicator when rel= is unset", async () => {
    // First apply a selection, then clear.
    store.set(structuralRelationshipsAtom, [
      makeRelationGroup(RELAY_GLOBAL_ID),
    ]);
    selectedRelationshipId(String(RELAY_PK));

    const { rerender } = renderJumpHook();
    await waitFor(() => store.get(selectedRelationsAtom).length === 1);

    // Pre-seed a hover id to verify the hook clears it.
    store.set(hoveredAnnotationIdAtom, "some-ann");

    selectedRelationshipId(null);
    rerender();

    await waitFor(() => store.get(selectedRelationsAtom).length === 0);
    expect(store.get(selectedRelationsAtom)).toEqual([]);
    expect(store.get(hoveredAnnotationIdAtom)).toBeNull();
  });

  it("calls scrollIntoView and sets hover on the source annotation when refs are ready", async () => {
    // Seed the refs map BEFORE the hook runs so tryScroll succeeds on the
    // first pass — exercises the happy-path branch of the effect.
    const scrollSpy = vi.fn();
    annotationRefsForTests.current = {
      "ann-1": { scrollIntoView: scrollSpy },
    };
    store.set(structuralRelationshipsAtom, [
      makeRelationGroup(RELAY_GLOBAL_ID),
    ]);
    selectedRelationshipId(String(RELAY_PK));

    renderJumpHook();

    await waitFor(() => scrollSpy.mock.calls.length > 0);
    expect(scrollSpy).toHaveBeenCalledWith({
      behavior: "smooth",
      block: "center",
    });
    expect(store.get(hoveredAnnotationIdAtom)).toBe("ann-1");
  });

  it("falls back to a target annotation ref when the source ref is not mounted", async () => {
    // Source ann-1 is not in the refs map; first target ann-2 is. Hook
    // should pick ann-2 to scroll but still set hover to the source.
    const scrollSpy = vi.fn();
    annotationRefsForTests.current = {
      "ann-2": { scrollIntoView: scrollSpy },
    };
    store.set(structuralRelationshipsAtom, [
      makeRelationGroup(RELAY_GLOBAL_ID),
    ]);
    selectedRelationshipId(String(RELAY_PK));

    renderJumpHook();

    await waitFor(() => scrollSpy.mock.calls.length > 0);
    expect(scrollSpy).toHaveBeenCalledTimes(1);
    expect(store.get(hoveredAnnotationIdAtom)).toBe("ann-1");
  });

  it("retries scrollIntoView after JUMP_TO_RELATIONSHIP_SCROLL_RETRY_MS when refs aren't ready", async () => {
    // No refs yet → tryScroll returns false → setTimeout schedules a retry.
    // Populating refs before the timer fires lets the retry succeed.
    vi.useFakeTimers();
    try {
      const scrollSpy = vi.fn();
      store.set(structuralRelationshipsAtom, [
        makeRelationGroup(RELAY_GLOBAL_ID),
      ]);
      selectedRelationshipId(String(RELAY_PK));

      renderJumpHook();

      // Refs map populates AFTER the effect runs but BEFORE the retry timer.
      annotationRefsForTests.current = {
        "ann-1": { scrollIntoView: scrollSpy },
      };
      // Advance just past the retry interval to trigger the fallback.
      vi.advanceTimersByTime(JUMP_TO_RELATIONSHIP_SCROLL_RETRY_MS + 1);

      expect(scrollSpy).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("treats a RelationGroup with a malformed global id as a non-match (catch branch)", async () => {
    // ``getNumericIdFromGlobalId`` throws on non-base64 ids. The hook must
    // swallow that and continue scanning rather than blowing up the effect.
    store.set(structuralRelationshipsAtom, [
      makeRelationGroup("not-a-valid-relay-id"),
      makeRelationGroup(RELAY_GLOBAL_ID),
    ]);
    selectedRelationshipId(String(RELAY_PK));

    renderJumpHook();

    await waitFor(() => store.get(selectedRelationsAtom).length === 1);
    expect(store.get(selectedRelationsAtom)[0].id).toBe(RELAY_GLOBAL_ID);
  });

  it("does not re-apply selection on every allRelations mutation", async () => {
    // The lastAppliedRef guard prevents the hook from fighting user-driven
    // selection changes once the URL deep-link has been honoured.
    store.set(structuralRelationshipsAtom, [
      makeRelationGroup(RELAY_GLOBAL_ID),
    ]);
    selectedRelationshipId(String(RELAY_PK));

    const { rerender } = renderJumpHook();
    await waitFor(() => store.get(selectedRelationsAtom).length === 1);

    // Simulate user clearing the selection through unrelated UI.
    store.set(selectedRelationsAtom, []);
    // Push an unrelated mutation (new relation appears) — the hook must
    // NOT re-select the URL-driven relation because lastAppliedRef matches.
    store.set(structuralRelationshipsAtom, [
      makeRelationGroup(RELAY_GLOBAL_ID),
      makeRelationGroup(btoa("Relationship:99")),
    ]);
    rerender();

    // Give the effect a tick to run.
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(store.get(selectedRelationsAtom)).toEqual([]);
  });
});
