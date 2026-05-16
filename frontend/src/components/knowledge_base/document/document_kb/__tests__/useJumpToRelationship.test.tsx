/**
 * Unit tests for ``useJumpToRelationship``.
 *
 * Issue #1645: the hook wires the ``?rel=<pk>`` URL param to the doc
 * viewer's relation-selection plumbing. URL carries a raw Django PK
 * while ``RelationGroup.id`` is a Relay global ID, so the hook must
 * compare on numeric IDs — these tests pin that bridge.
 */

import * as React from "react";
import { Provider as JotaiProvider, createStore, useAtomValue } from "jotai";
import { describe, it, expect, beforeEach, afterEach } from "vitest";

import { renderHook, waitFor } from "../../../../../test-utils/renderHook";
import { useJumpToRelationship } from "../useJumpToRelationship";
import { selectedRelationshipId } from "../../../../../graphql/cache";
import {
  pdfAnnotationsAtom,
  structuralRelationshipsAtom,
} from "../../../../annotator/context/AnnotationAtoms";
import {
  selectedRelationsAtom,
  hoveredAnnotationIdAtom,
} from "../../../../annotator/context/UISettingsAtom";
import {
  PdfAnnotations,
  RelationGroup,
} from "../../../../annotator/types/annotations";
import { AnnotationLabelType } from "../../../../../types/graphql-api";

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

  beforeEach(() => {
    store = createStore();
    selectedRelationshipId(null);
  });

  afterEach(() => {
    selectedRelationshipId(null);
  });

  it("is a no-op when ?rel= is unset", () => {
    renderHook(() => useJumpToRelationship(), {
      wrapper: createWrapper(store),
    });
    // Nothing should have been selected.
    expect(store.get(selectedRelationsAtom)).toEqual([]);
    expect(store.get(hoveredAnnotationIdAtom)).toBeNull();
  });

  it("does not match when relId is set but no relations are loaded yet", async () => {
    selectedRelationshipId(String(RELAY_PK));
    renderHook(() => useJumpToRelationship(), {
      wrapper: createWrapper(store),
    });
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

    renderHook(() => useJumpToRelationship(), {
      wrapper: createWrapper(store),
    });

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

    renderHook(() => useJumpToRelationship(), {
      wrapper: createWrapper(store),
    });

    await waitFor(() => store.get(selectedRelationsAtom).length === 1);
    expect(store.get(selectedRelationsAtom)).toHaveLength(1);
  });

  it("falls back gracefully when relId is non-numeric", () => {
    store.set(structuralRelationshipsAtom, [
      makeRelationGroup(RELAY_GLOBAL_ID),
    ]);
    selectedRelationshipId("not-a-number");

    renderHook(() => useJumpToRelationship(), {
      wrapper: createWrapper(store),
    });

    expect(store.get(selectedRelationsAtom)).toEqual([]);
  });

  it("clears the selected relation AND hover indicator when rel= is unset", async () => {
    // First apply a selection, then clear.
    store.set(structuralRelationshipsAtom, [
      makeRelationGroup(RELAY_GLOBAL_ID),
    ]);
    selectedRelationshipId(String(RELAY_PK));

    const { rerender } = renderHook(() => useJumpToRelationship(), {
      wrapper: createWrapper(store),
    });
    await waitFor(() => store.get(selectedRelationsAtom).length === 1);

    // Pre-seed a hover id to verify the hook clears it.
    store.set(hoveredAnnotationIdAtom, "some-ann");

    selectedRelationshipId(null);
    rerender();

    await waitFor(() => store.get(selectedRelationsAtom).length === 0);
    expect(store.get(selectedRelationsAtom)).toEqual([]);
    expect(store.get(hoveredAnnotationIdAtom)).toBeNull();
  });

  it("does not re-apply selection on every allRelations mutation", async () => {
    // The lastAppliedRef guard prevents the hook from fighting user-driven
    // selection changes once the URL deep-link has been honoured.
    store.set(structuralRelationshipsAtom, [
      makeRelationGroup(RELAY_GLOBAL_ID),
    ]);
    selectedRelationshipId(String(RELAY_PK));

    const { rerender } = renderHook(() => useJumpToRelationship(), {
      wrapper: createWrapper(store),
    });
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

// Silence unused-import warnings — these are used as type assertions only.
void useAtomValue;
void PdfAnnotations;
