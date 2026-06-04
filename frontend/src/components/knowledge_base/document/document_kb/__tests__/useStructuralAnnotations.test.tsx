import { renderHook, waitFor } from "../../../../../test-utils/renderHook";
// ``render`` here is from @testing-library/react; ``waitFor`` deliberately
// uses the project's act-wrapped variant. The library's own ``waitFor`` does
// not flush React 18 updates from useEffect chains under the
// ``IS_REACT_ACT_ENVIRONMENT`` flag, so atom updates triggered by
// ``useLazyQuery`` never reach the rendered probe and the predicate spins
// against stale state. See ``test-utils/renderHook.tsx`` for the rationale.
import { render } from "@testing-library/react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { Provider, useAtomValue } from "jotai";
import * as React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import { useStructuralAnnotations } from "../useStructuralAnnotations";
import { GET_DOCUMENT_STRUCTURAL_ANNOTATIONS } from "../../../../../graphql/queries";
import {
  structuralAnnotationsAtom,
  structuralAnnotationsLoadedAtom,
  structuralRelationshipsAtom,
} from "../../../../annotator/context/AnnotationAtoms";
import {
  selectedAnnotationIds,
  showStructuralAnnotations,
} from "../../../../../graphql/cache";

// Bypass the heavy annotation-conversion path — the hook just feeds whatever
// the converter returns into atoms, so a passthrough is enough for assertions.
vi.mock("../../../../../utils/transform", () => ({
  convertToServerAnnotation: (annotation: { id: string }) => ({
    id: annotation.id,
    rawText: "stub",
  }),
}));

vi.mock("../helpers", () => ({
  relationToGroup: (rel: { id: string }, _force?: boolean) => ({
    id: rel.id,
    sourceIds: [],
    targetIds: [],
    structural: true,
  }),
}));

const baseLabel = {
  id: "lbl",
  text: "Label",
  color: "#000",
  icon: "",
  description: "",
  labelType: "TOKEN_LABEL",
};

const annotation = (id: string) => ({
  id,
  page: 0,
  parent: null,
  annotationLabel: baseLabel,
  annotationType: "TOKEN_LABEL",
  rawText: "",
  json: {},
  myPermissions: [],
  structural: true,
  contentModalities: [],
});

const relationship = (id: string) => ({
  id,
  structural: true,
  relationshipLabel: { ...baseLabel, labelType: "RELATIONSHIP_LABEL" },
  sourceAnnotations: { edges: [{ node: { id: "src" } }] },
  targetAnnotations: { edges: [{ node: { id: "tgt" } }] },
});

const makeMock = (
  documentId: string,
  annotationIds: string[] | undefined,
  annotations: ReturnType<typeof annotation>[],
  relationships: ReturnType<typeof relationship>[]
): MockedResponse => ({
  request: {
    query: GET_DOCUMENT_STRUCTURAL_ANNOTATIONS,
    variables: { documentId, ...(annotationIds ? { annotationIds } : {}) },
  },
  result: {
    data: {
      document: {
        id: documentId,
        allStructuralAnnotations: annotations,
        allStructuralRelationships: relationships,
      },
    },
  },
});

interface WrapperProps {
  mocks: MockedResponse[];
  children: React.ReactNode;
}

const wrap = ({ mocks, children }: WrapperProps) => (
  <MockedProvider mocks={mocks} addTypename={false}>
    <Provider>{children}</Provider>
  </MockedProvider>
);

const StructuralProbe: React.FC<{ documentId: string }> = ({ documentId }) => {
  useStructuralAnnotations(documentId);
  const anns = useAtomValue(structuralAnnotationsAtom);
  const rels = useAtomValue(structuralRelationshipsAtom);
  const loaded = useAtomValue(structuralAnnotationsLoadedAtom);
  return (
    <div>
      <span data-testid="anns">{anns.map((a) => a.id).join(",")}</span>
      <span data-testid="rels">{rels.map((r) => r.id).join(",")}</span>
      <span data-testid="loaded">{loaded ? "1" : "0"}</span>
    </div>
  );
};

describe("useStructuralAnnotations", () => {
  beforeEach(() => {
    showStructuralAnnotations(false);
    selectedAnnotationIds([]);
  });

  it("does not fire any fetch when toggled off and no deep-link is present", async () => {
    const mocks: MockedResponse[] = [];
    const Wrapper: React.FC<{ children?: React.ReactNode }> = ({ children }) =>
      wrap({ mocks, children });
    // If the hook throws while toggled off, ``renderHook`` itself would
    // surface the error synchronously — so simply mounting without throwing
    // is enough to prove the no-fire contract.
    renderHook(() => useStructuralAnnotations("doc-A"), { wrapper: Wrapper });

    await new Promise((r) => setTimeout(r, 0));
  });

  it("fetches all structural annotations once the user toggles structural visibility on", async () => {
    showStructuralAnnotations(true);

    const mocks = [
      makeMock(
        "doc-A",
        undefined,
        [annotation("ann-1"), annotation("ann-2")],
        [relationship("rel-1")]
      ),
    ];

    const utils = render(
      <MockedProvider mocks={mocks} addTypename={false}>
        <Provider>
          <StructuralProbe documentId="doc-A" />
        </Provider>
      </MockedProvider>
    );

    await waitFor(() =>
      expect(utils.getByTestId("loaded").textContent).toBe("1")
    );
    expect(utils.getByTestId("anns").textContent).toBe("ann-1,ann-2");
    expect(utils.getByTestId("rels").textContent).toBe("rel-1");
  });

  it("fetches targeted annotations when a deep-link selects ids and structural set is unloaded", async () => {
    selectedAnnotationIds(["ann-99"]);

    const mocks = [
      makeMock(
        "doc-B",
        ["ann-99"],
        [annotation("ann-99")],
        [relationship("rel-99")]
      ),
    ];

    const utils = render(
      <MockedProvider mocks={mocks} addTypename={false}>
        <Provider>
          <StructuralProbe documentId="doc-B" />
        </Provider>
      </MockedProvider>
    );

    await waitFor(() =>
      expect(utils.getByTestId("anns").textContent).toBe("ann-99")
    );
    // Targeted fetch should NOT mark the structural set as fully loaded.
    expect(utils.getByTestId("loaded").textContent).toBe("0");
    expect(utils.getByTestId("rels").textContent).toBe("rel-99");
  });

  it("reports loading on the very first render of a pending deep-link, before the targeted fetch is dispatched", async () => {
    // Cold-cache structural deep-link: an id is selected before anything has
    // loaded. The targeted fetch is dispatched by an effect that runs *after*
    // the first render, so on that first render Apollo's lazy-query result is
    // still `{ called: false, loading: false }`. The hook must nonetheless
    // report loading immediately, otherwise the consuming not-found guard
    // (MobileAnnotationDetail) flashes "no longer available" for one frame.
    selectedAnnotationIds(["ann-77"]);

    const mocks = [
      makeMock(
        "doc-C",
        ["ann-77"],
        [annotation("ann-77")],
        [relationship("rel-77")]
      ),
    ];

    const loadingByRender: boolean[] = [];
    const LoadingProbe: React.FC<{ documentId: string }> = ({ documentId }) => {
      const { loading } = useStructuralAnnotations(documentId);
      loadingByRender.push(loading);
      return <span data-testid="loading">{loading ? "1" : "0"}</span>;
    };

    const utils = render(
      <MockedProvider mocks={mocks} addTypename={false}>
        <Provider>
          <LoadingProbe documentId="doc-C" />
        </Provider>
      </MockedProvider>
    );

    // The discriminating assertion: the first render — captured before any
    // effect runs — must already report loading.
    expect(loadingByRender[0]).toBe(true);

    // Once the targeted fetch settles, loading drops back to false so a
    // genuinely-missing annotation can still surface the not-found state.
    await waitFor(() =>
      expect(utils.getByTestId("loading").textContent).toBe("0")
    );
  });

  it("clears all three atoms when the documentId changes", async () => {
    showStructuralAnnotations(true);

    const mocksA = makeMock(
      "doc-A",
      undefined,
      [annotation("first")],
      [relationship("rel-A")]
    );
    const mocksB = makeMock(
      "doc-B",
      undefined,
      [annotation("second")],
      [relationship("rel-B")]
    );

    const Wrapper = ({ documentId }: { documentId: string }) => (
      <MockedProvider mocks={[mocksA, mocksB]} addTypename={false}>
        <Provider>
          <StructuralProbe documentId={documentId} />
        </Provider>
      </MockedProvider>
    );

    const { rerender, getByTestId } = render(<Wrapper documentId="doc-A" />);
    await waitFor(() => expect(getByTestId("anns").textContent).toBe("first"));

    // Swapping documentId must reset everything before refetching.
    rerender(<Wrapper documentId="doc-B" />);
    await waitFor(() => expect(getByTestId("anns").textContent).toBe("second"));
  });
});
