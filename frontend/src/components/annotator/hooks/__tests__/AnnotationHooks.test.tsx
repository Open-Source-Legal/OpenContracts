/**
 * Unit tests for hooks exported from `AnnotationHooks.tsx`.
 *
 * Exercises the CRUD hooks (`useCreateAnnotation`, `useUpdateAnnotation`,
 * `useDeleteAnnotation`, etc.) as well as the thin state wrapper hooks
 * (`usePdfAnnotations`, `useStructuralAnnotations`, `useInitialAnnotations`).
 *
 * Covered behaviors:
 * - State hooks: add / replace / add-doc-type / replace-doc-types
 * - Guard rails: mutations short-circuit without a selected corpus/document
 * - Empty-annotation guard: annotations with no text AND no tokens are dropped
 * - Mutation success path: annotations are added/updated/removed in state
 * - Approve / reject flip the corresponding flag
 * - Relationship-removal logic: the relation is DELETEd when either side
 *   becomes empty, and UPDATEd otherwise
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act } from "../../../../test-utils/renderHook";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { Provider } from "jotai";
import { useHydrateAtoms } from "jotai/utils";
import { MemoryRouter } from "react-router-dom";
import * as React from "react";
import type { ReactNode } from "react";

import {
  usePdfAnnotations,
  useStructuralAnnotations,
  useInitialAnnotations,
  useCreateAnnotation,
  useUpdateAnnotation,
  useDeleteAnnotation,
  useApproveAnnotation,
  useRejectAnnotation,
  useAddDocTypeAnnotation,
  useRemoveRelationship,
  useRemoveAnnotationFromRelationship,
  useDeleteDocTypeAnnotation,
} from "../AnnotationHooks";
import {
  PdfAnnotations,
  ServerSpanAnnotation,
  ServerTokenAnnotation,
  RelationGroup,
  DocTypeAnnotation,
} from "../../types/annotations";
import { pdfAnnotationsAtom } from "../../context/AnnotationAtoms";
import { selectedDocumentAtom } from "../../context/DocumentAtom";
import { corpusStateAtom } from "../../context/CorpusAtom";
import {
  REQUEST_ADD_ANNOTATION,
  REQUEST_DELETE_ANNOTATION,
  REQUEST_UPDATE_ANNOTATION,
  REQUEST_ADD_DOC_TYPE_ANNOTATION,
  REQUEST_REMOVE_RELATIONSHIP,
  REQUEST_REMOVE_RELATIONSHIPS,
  REQUEST_UPDATE_RELATIONS,
  APPROVE_ANNOTATION,
  REJECT_ANNOTATION,
} from "../../../../graphql/mutations";
import { LabelType } from "../../types/enums";
import { PermissionTypes } from "../../../types";
import type { AnnotationLabelType } from "../../../../types/graphql-api";

// ---------- Mock react-toastify so hooks don't touch the DOM container ----------

vi.mock("react-toastify", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));

// ---------- Fixtures ----------

const mockLabel: AnnotationLabelType = {
  id: "label-1",
  text: "Test Label",
  color: "#3B82F6",
  icon: "tag",
  description: "",
  labelType: LabelType.SpanLabel,
};

const mockDocTypeLabel: AnnotationLabelType = {
  id: "doc-label-1",
  text: "Contract",
  color: "#F59E0B",
  icon: "file",
  description: "",
  labelType: LabelType.DocTypeLabel,
};

const mockDocument = {
  id: "doc-123",
  slug: "test-doc",
  title: "Test Document",
  fileType: "application/txt",
  creator: { id: "user-1", slug: "u", email: "u@e.com" },
} as any;

const mockCorpus = {
  id: "corpus-123",
  slug: "test-corpus",
  title: "Test Corpus",
  creator: { id: "user-1", slug: "u", email: "u@e.com" },
} as any;

const makeSpan = (
  id: string,
  start = 0,
  end = 5,
  text = "hello"
): ServerSpanAnnotation =>
  new ServerSpanAnnotation(
    0,
    mockLabel,
    text,
    false,
    { start, end },
    [
      PermissionTypes.CAN_READ,
      PermissionTypes.CAN_UPDATE,
      PermissionTypes.CAN_REMOVE,
    ],
    false,
    false,
    false,
    id
  );

const makeRelation = (
  id: string,
  sourceIds: string[],
  targetIds: string[]
): RelationGroup => new RelationGroup(sourceIds, targetIds, mockLabel, id);

// ---------- Wrapper ----------

interface WrapperOptions {
  mocks?: MockedResponse[];
  withCorpus?: boolean;
  withDocument?: boolean;
  initialAnnotations?: (ServerSpanAnnotation | ServerTokenAnnotation)[];
  initialRelations?: RelationGroup[];
  initialDocTypes?: DocTypeAnnotation[];
}

const buildWrapper = (options: WrapperOptions = {}) => {
  const {
    mocks = [],
    withCorpus = true,
    withDocument = true,
    initialAnnotations = [],
    initialRelations = [],
    initialDocTypes = [],
  } = options;

  const Hydrate = ({ children }: { children: ReactNode }) => {
    useHydrateAtoms([
      [selectedDocumentAtom, withDocument ? mockDocument : null],
      [
        corpusStateAtom,
        {
          selectedCorpus: withCorpus ? mockCorpus : null,
          myPermissions: [],
          spanLabels: [],
          humanSpanLabels: [],
          relationLabels: [],
          docTypeLabels: [],
          humanTokenLabels: [],
          allowComments: true,
          isLoading: false,
        },
      ],
      [
        pdfAnnotationsAtom,
        new PdfAnnotations(
          initialAnnotations,
          initialRelations,
          initialDocTypes
        ),
      ],
    ]);
    return <>{children}</>;
  };

  return ({ children }: { children: ReactNode }) => (
    <MemoryRouter>
      <Provider>
        <Hydrate>
          <MockedProvider mocks={mocks} addTypename={false}>
            {children as any}
          </MockedProvider>
        </Hydrate>
      </Provider>
    </MemoryRouter>
  );
};

// ---------- Tests ----------

describe("AnnotationHooks", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("usePdfAnnotations (state wrapper)", () => {
    it("adds annotations without clobbering existing ones", () => {
      const existing = makeSpan("ann-1");
      const { result } = renderHook(() => usePdfAnnotations(), {
        wrapper: buildWrapper({ initialAnnotations: [existing] }),
      });

      expect(result.current.pdfAnnotations.annotations).toHaveLength(1);

      const newOne = makeSpan("ann-2", 10, 15, "world");
      act(() => {
        result.current.addMultipleAnnotations([newOne]);
      });

      expect(result.current.pdfAnnotations.annotations).toHaveLength(2);
      expect(result.current.pdfAnnotations.annotations[1].id).toBe("ann-2");
      expect(result.current.pdfAnnotations.unsavedChanges).toBe(true);
    });

    it("replaceAnnotations swaps in a fresh array", () => {
      const existing = makeSpan("ann-1");
      const { result } = renderHook(() => usePdfAnnotations(), {
        wrapper: buildWrapper({ initialAnnotations: [existing] }),
      });

      const replacement = makeSpan("ann-99");
      act(() => {
        result.current.replaceAnnotations([replacement]);
      });

      expect(result.current.pdfAnnotations.annotations).toHaveLength(1);
      expect(result.current.pdfAnnotations.annotations[0].id).toBe("ann-99");
    });

    it("replaceRelations swaps relations while preserving annotations/docTypes", () => {
      const existingAnn = makeSpan("ann-1");
      const { result } = renderHook(() => usePdfAnnotations(), {
        wrapper: buildWrapper({ initialAnnotations: [existingAnn] }),
      });

      const rel = makeRelation("rel-1", ["ann-1"], ["ann-2"]);
      act(() => {
        result.current.replaceRelations([rel]);
      });

      expect(result.current.pdfAnnotations.relations).toHaveLength(1);
      expect(result.current.pdfAnnotations.relations[0].id).toBe("rel-1");
      expect(result.current.pdfAnnotations.annotations).toHaveLength(1);
    });

    it("addDocTypeAnnotations appends without clobbering", () => {
      const { result } = renderHook(() => usePdfAnnotations(), {
        wrapper: buildWrapper(),
      });

      const docType = new DocTypeAnnotation(
        mockDocTypeLabel,
        [PermissionTypes.CAN_READ],
        "dt-1"
      );

      act(() => {
        result.current.addDocTypeAnnotations([docType]);
      });

      expect(result.current.pdfAnnotations.docTypes).toHaveLength(1);
      expect(result.current.pdfAnnotations.docTypes[0].id).toBe("dt-1");
    });

    it("replaceDocTypeAnnotations swaps in new doc types", () => {
      const oldDocType = new DocTypeAnnotation(
        mockDocTypeLabel,
        [PermissionTypes.CAN_READ],
        "dt-old"
      );
      const { result } = renderHook(() => usePdfAnnotations(), {
        wrapper: buildWrapper({ initialDocTypes: [oldDocType] }),
      });

      const newDocType = new DocTypeAnnotation(
        mockDocTypeLabel,
        [PermissionTypes.CAN_READ],
        "dt-new"
      );

      act(() => {
        result.current.replaceDocTypeAnnotations([newDocType]);
      });

      expect(result.current.pdfAnnotations.docTypes).toHaveLength(1);
      expect(result.current.pdfAnnotations.docTypes[0].id).toBe("dt-new");
    });
  });

  describe("useStructuralAnnotations + useInitialAnnotations", () => {
    it("exposes the structural annotations atom with a setter", () => {
      const { result } = renderHook(() => useStructuralAnnotations(), {
        wrapper: buildWrapper(),
      });

      expect(result.current.structuralAnnotations).toEqual([]);
      expect(typeof result.current.setStructuralAnnotations).toBe("function");
    });

    it("exposes initial annotations + relations with setters", () => {
      const { result } = renderHook(() => useInitialAnnotations(), {
        wrapper: buildWrapper(),
      });

      expect(result.current.initialAnnotations).toEqual([]);
      expect(result.current.initialRelations).toEqual([]);
      expect(typeof result.current.setInitialAnnotations).toBe("function");
      expect(typeof result.current.setInitialRelations).toBe("function");
    });
  });

  describe("useCreateAnnotation", () => {
    it("short-circuits (no state change, no mutation) without a corpus", async () => {
      // MockedProvider has NO mocks — if the hook fires the mutation
      // anyway, Apollo throws "No more mocked responses" which surfaces
      // through the rendered hook. The real assertion is that state and
      // the mutation side both stay empty.
      const { result } = renderHook(
        () => ({
          create: useCreateAnnotation(),
          state: usePdfAnnotations(),
        }),
        { wrapper: buildWrapper({ withCorpus: false }) }
      );

      const ann = makeSpan("new");
      await act(async () => {
        await result.current.create(ann);
      });

      expect(result.current.state.pdfAnnotations.annotations).toHaveLength(0);
    });

    it("adds the server-returned annotation (with server-assigned id) on a successful mutation", async () => {
      const localAnn = makeSpan("local-tmp-id", 0, 5, "hello");
      const serverAssignedId = "server-generated-id-123";

      const mocks: MockedResponse[] = [
        {
          request: {
            query: REQUEST_ADD_ANNOTATION,
            variables: {
              json: localAnn.json,
              documentId: mockDocument.id,
              corpusId: mockCorpus.id,
              annotationLabelId: mockLabel.id,
              rawText: localAnn.rawText,
              page: localAnn.page,
              annotationType: LabelType.SpanLabel,
            },
          },
          result: {
            data: {
              addAnnotation: {
                ok: true,
                annotation: {
                  id: serverAssignedId,
                  page: 0,
                  rawText: "hello",
                  json: { start: 0, end: 5 },
                  annotationType: LabelType.SpanLabel,
                  annotationLabel: mockLabel,
                  myPermissions: ["CAN_READ", "CAN_UPDATE", "CAN_REMOVE"],
                  isPublic: false,
                  sourceNodeInRelationships: { edges: [] },
                },
              },
            },
          },
        },
      ];

      const { result } = renderHook(
        () => ({
          create: useCreateAnnotation(),
          state: usePdfAnnotations(),
        }),
        { wrapper: buildWrapper({ mocks }) }
      );

      await act(async () => {
        await result.current.create(localAnn);
      });

      expect(result.current.state.pdfAnnotations.annotations).toHaveLength(1);
      // The key contract: the id in state comes from the server response,
      // not the local temporary id that was passed in.
      expect(result.current.state.pdfAnnotations.annotations[0].id).toBe(
        serverAssignedId
      );
    });

    it("drops annotations with neither text nor tokens", async () => {
      const { result } = renderHook(
        () => {
          const create = useCreateAnnotation();
          const state = usePdfAnnotations();
          return { create, state };
        },
        { wrapper: buildWrapper() }
      );

      const empty = new ServerSpanAnnotation(
        0,
        mockLabel,
        "",
        false,
        { start: 0, end: 0 },
        [],
        false,
        false,
        false,
        "empty"
      );

      await act(async () => {
        await result.current.create(empty);
      });

      expect(result.current.state.pdfAnnotations.annotations).toHaveLength(0);
    });

    it("falls back to local-add when mutation throws", async () => {
      const ann = makeSpan("fallback");
      const mocks: MockedResponse[] = [
        {
          request: {
            query: REQUEST_ADD_ANNOTATION,
            variables: {
              json: ann.json,
              documentId: mockDocument.id,
              corpusId: mockCorpus.id,
              annotationLabelId: mockLabel.id,
              rawText: ann.rawText,
              page: ann.page,
              annotationType: LabelType.SpanLabel,
            },
          },
          error: new Error("mutation exploded"),
        },
      ];

      const { result } = renderHook(
        () => {
          const create = useCreateAnnotation();
          const state = usePdfAnnotations();
          return { create, state };
        },
        { wrapper: buildWrapper({ mocks }) }
      );

      await act(async () => {
        await result.current.create(ann);
      });

      // Fallback path added it locally
      expect(result.current.state.pdfAnnotations.annotations).toHaveLength(1);
      expect(result.current.state.pdfAnnotations.annotations[0].id).toBe(
        "fallback"
      );
    });
  });

  describe("useUpdateAnnotation", () => {
    it("replaces the annotation in state on a successful mutation", async () => {
      const existing = makeSpan("ann-1", 0, 5, "hello");
      const mocks: MockedResponse[] = [
        {
          request: {
            query: REQUEST_UPDATE_ANNOTATION,
            variables: {
              id: existing.id,
              json: existing.json,
              rawText: existing.rawText,
              page: existing.page,
              annotationLabel: mockLabel.id,
            },
          },
          result: {
            data: { updateAnnotation: { ok: true, message: "ok" } },
          },
        },
      ];

      const { result } = renderHook(
        () => ({
          update: useUpdateAnnotation(),
          state: usePdfAnnotations(),
        }),
        {
          wrapper: buildWrapper({ mocks, initialAnnotations: [existing] }),
        }
      );

      await act(async () => {
        await result.current.update(existing);
      });

      expect(result.current.state.pdfAnnotations.annotations).toHaveLength(1);
      expect(result.current.state.pdfAnnotations.annotations[0].id).toBe(
        "ann-1"
      );
      expect(result.current.state.pdfAnnotations.unsavedChanges).toBe(true);
    });

    it("updates one annotation in place without dropping siblings", async () => {
      // Regression: earlier versions called replaceAnnotations([updated])
      // which collapsed the full list to the one updated annotation.
      // The updated hook must preserve siblings and swap only the match.
      const sibling = makeSpan("ann-sibling", 100, 105, "world");
      const target = makeSpan("ann-target", 0, 5, "hello");

      const mocks: MockedResponse[] = [
        {
          request: {
            query: REQUEST_UPDATE_ANNOTATION,
            variables: {
              id: target.id,
              json: target.json,
              rawText: target.rawText,
              page: target.page,
              annotationLabel: mockLabel.id,
            },
          },
          result: {
            data: { updateAnnotation: { ok: true, message: "ok" } },
          },
        },
      ];

      const { result } = renderHook(
        () => ({
          update: useUpdateAnnotation(),
          state: usePdfAnnotations(),
        }),
        {
          wrapper: buildWrapper({
            mocks,
            initialAnnotations: [sibling, target],
          }),
        }
      );

      await act(async () => {
        await result.current.update(target);
      });

      const ids = result.current.state.pdfAnnotations.annotations.map(
        (a) => a.id
      );
      expect(ids).toEqual(["ann-sibling", "ann-target"]);
    });
  });

  describe("useDeleteAnnotation", () => {
    it("removes the annotation and the relations where it's the sole source/target", async () => {
      const annA = makeSpan("ann-A");
      const annB = makeSpan("ann-B");
      const rel = makeRelation("rel-1", ["ann-A"], ["ann-B"]); // deleting A empties sources → DELETE

      const mocks: MockedResponse[] = [
        {
          request: {
            query: REQUEST_DELETE_ANNOTATION,
            variables: { annotationId: "ann-A" },
          },
          result: { data: { removeAnnotation: { ok: true } } },
        },
        {
          request: {
            query: REQUEST_REMOVE_RELATIONSHIPS,
            variables: { relationshipIds: ["rel-1"] },
          },
          result: { data: { removeRelationships: { ok: true } } },
        },
      ];

      const { result } = renderHook(
        () => ({
          del: useDeleteAnnotation(),
          state: usePdfAnnotations(),
        }),
        {
          wrapper: buildWrapper({
            mocks,
            initialAnnotations: [annA, annB],
            initialRelations: [rel],
          }),
        }
      );

      await act(async () => {
        await result.current.del("ann-A");
      });

      expect(
        result.current.state.pdfAnnotations.annotations.map((a) => a.id)
      ).toEqual(["ann-B"]);
      expect(result.current.state.pdfAnnotations.relations).toHaveLength(0);
    });

    it("updates (not deletes) a relation when both sides still have annotations", async () => {
      const annA = makeSpan("ann-A");
      const annB = makeSpan("ann-B");
      const annC = makeSpan("ann-C");
      // Deleting ann-A leaves ann-C in sources → UPDATE (not DELETE)
      const rel = makeRelation("rel-1", ["ann-A", "ann-C"], ["ann-B"]);

      const mocks: MockedResponse[] = [
        {
          request: {
            query: REQUEST_DELETE_ANNOTATION,
            variables: { annotationId: "ann-A" },
          },
          result: { data: { removeAnnotation: { ok: true } } },
        },
        {
          request: {
            query: REQUEST_UPDATE_RELATIONS,
            variables: {
              relationships: [
                {
                  id: "rel-1",
                  sourceIds: ["ann-C"],
                  targetIds: ["ann-B"],
                  relationshipLabelId: mockLabel.id,
                  corpusId: mockCorpus.id,
                  documentId: mockDocument.id,
                },
              ],
            },
          },
          result: { data: { updateRelationships: { ok: true } } },
        },
      ];

      const { result } = renderHook(
        () => ({
          del: useDeleteAnnotation(),
          state: usePdfAnnotations(),
        }),
        {
          wrapper: buildWrapper({
            mocks,
            initialAnnotations: [annA, annB, annC],
            initialRelations: [rel],
          }),
        }
      );

      await act(async () => {
        await result.current.del("ann-A");
      });

      // Relation survived (because ann-C is still a source)
      expect(
        result.current.state.pdfAnnotations.annotations.map((a) => a.id).sort()
      ).toEqual(["ann-B", "ann-C"]);
      expect(result.current.state.pdfAnnotations.relations).toHaveLength(1);
    });

    it("short-circuits without a selected corpus/document", async () => {
      const ann = makeSpan("ann-A");
      const { result } = renderHook(
        () => ({
          del: useDeleteAnnotation(),
          state: usePdfAnnotations(),
        }),
        {
          wrapper: buildWrapper({
            withCorpus: false,
            initialAnnotations: [ann],
          }),
        }
      );

      await act(async () => {
        await result.current.del("ann-A");
      });

      // No mutation fired → annotation still present
      expect(result.current.state.pdfAnnotations.annotations).toHaveLength(1);
    });
  });

  describe("useApproveAnnotation + useRejectAnnotation", () => {
    it("useApproveAnnotation sets approved=true on the matching annotation", async () => {
      const ann = makeSpan("ann-A");
      const mocks: MockedResponse[] = [
        {
          request: {
            query: APPROVE_ANNOTATION,
            variables: { annotationId: "ann-A", comment: undefined },
          },
          result: {
            data: {
              approveAnnotation: { ok: true, userFeedback: null },
            },
          },
        },
      ];

      const { result } = renderHook(
        () => ({
          approve: useApproveAnnotation(),
          state: usePdfAnnotations(),
        }),
        { wrapper: buildWrapper({ mocks, initialAnnotations: [ann] }) }
      );

      await act(async () => {
        await result.current.approve("ann-A");
      });

      expect(result.current.state.pdfAnnotations.annotations[0].approved).toBe(
        true
      );
      expect(result.current.state.pdfAnnotations.annotations[0].rejected).toBe(
        false
      );
    });

    it("useRejectAnnotation sets rejected=true on the matching annotation", async () => {
      const ann = makeSpan("ann-A");
      const mocks: MockedResponse[] = [
        {
          request: {
            query: REJECT_ANNOTATION,
            variables: { annotationId: "ann-A", comment: undefined },
          },
          result: {
            data: {
              rejectAnnotation: { ok: true, userFeedback: null },
            },
          },
        },
      ];

      const { result } = renderHook(
        () => ({
          reject: useRejectAnnotation(),
          state: usePdfAnnotations(),
        }),
        { wrapper: buildWrapper({ mocks, initialAnnotations: [ann] }) }
      );

      await act(async () => {
        await result.current.reject("ann-A");
      });

      expect(result.current.state.pdfAnnotations.annotations[0].rejected).toBe(
        true
      );
      expect(result.current.state.pdfAnnotations.annotations[0].approved).toBe(
        false
      );
    });
  });

  describe("useAddDocTypeAnnotation", () => {
    it("short-circuits without a corpus/document", async () => {
      const { result } = renderHook(
        () => ({
          add: useAddDocTypeAnnotation(),
          state: usePdfAnnotations(),
        }),
        { wrapper: buildWrapper({ withCorpus: false }) }
      );

      await act(async () => {
        await result.current.add(mockDocTypeLabel);
      });

      expect(result.current.state.pdfAnnotations.docTypes).toHaveLength(0);
    });

    it("adds a doc-type annotation to state on mutation success", async () => {
      const mocks: MockedResponse[] = [
        {
          request: {
            query: REQUEST_ADD_DOC_TYPE_ANNOTATION,
            variables: {
              documentId: mockDocument.id,
              corpusId: mockCorpus.id,
              annotationLabelId: mockDocTypeLabel.id,
            },
          },
          result: {
            data: {
              addDocTypeAnnotation: {
                ok: true,
                annotation: {
                  id: "server-dt-1",
                  myPermissions: ["READ"],
                  isPublic: false,
                  annotationLabel: mockDocTypeLabel,
                },
              },
            },
          },
        },
      ];

      const { result } = renderHook(
        () => ({
          add: useAddDocTypeAnnotation(),
          state: usePdfAnnotations(),
        }),
        { wrapper: buildWrapper({ mocks }) }
      );

      await act(async () => {
        await result.current.add(mockDocTypeLabel);
      });

      expect(result.current.state.pdfAnnotations.docTypes).toHaveLength(1);
      expect(result.current.state.pdfAnnotations.docTypes[0].id).toBe(
        "server-dt-1"
      );
    });
  });

  describe("useDeleteDocTypeAnnotation", () => {
    it("removes the matching doc-type annotation from state", async () => {
      const docType = new DocTypeAnnotation(
        mockDocTypeLabel,
        [PermissionTypes.CAN_READ],
        "dt-1"
      );
      const mocks: MockedResponse[] = [
        {
          request: {
            query: REQUEST_DELETE_ANNOTATION,
            variables: { annotationId: "dt-1" },
          },
          result: { data: { removeAnnotation: { ok: true } } },
        },
      ];

      const { result } = renderHook(
        () => ({
          del: useDeleteDocTypeAnnotation(),
          state: usePdfAnnotations(),
        }),
        { wrapper: buildWrapper({ mocks, initialDocTypes: [docType] }) }
      );

      await act(async () => {
        await result.current.del("dt-1");
      });

      expect(result.current.state.pdfAnnotations.docTypes).toHaveLength(0);
    });
  });

  describe("useRemoveRelationship", () => {
    it("removes the relation from state on mutation success", async () => {
      const rel = makeRelation("rel-1", ["a"], ["b"]);
      const mocks: MockedResponse[] = [
        {
          request: {
            query: REQUEST_REMOVE_RELATIONSHIP,
            variables: { relationshipId: "rel-1" },
          },
          result: { data: { removeRelationship: { ok: true } } },
        },
      ];

      const { result } = renderHook(
        () => ({
          remove: useRemoveRelationship(),
          state: usePdfAnnotations(),
        }),
        { wrapper: buildWrapper({ mocks, initialRelations: [rel] }) }
      );

      await act(async () => {
        await result.current.remove("rel-1");
      });

      expect(result.current.state.pdfAnnotations.relations).toHaveLength(0);
    });
  });

  describe("useRemoveAnnotationFromRelationship", () => {
    it("DELETEs the relation when the remaining source side becomes empty", async () => {
      const rel = makeRelation("rel-1", ["ann-A"], ["ann-B"]); // removing A → sources empty
      const mocks: MockedResponse[] = [
        {
          request: {
            query: REQUEST_REMOVE_RELATIONSHIP,
            variables: { relationshipId: "rel-1" },
          },
          result: { data: { removeRelationship: { ok: true } } },
        },
      ];

      const { result } = renderHook(
        () => ({
          removeFromRel: useRemoveAnnotationFromRelationship(),
          state: usePdfAnnotations(),
        }),
        { wrapper: buildWrapper({ mocks, initialRelations: [rel] }) }
      );

      await act(async () => {
        await result.current.removeFromRel("ann-A", "rel-1");
      });

      expect(result.current.state.pdfAnnotations.relations).toHaveLength(0);
    });

    it("UPDATEs the relation when both sides still have annotations", async () => {
      const rel = makeRelation("rel-1", ["ann-A", "ann-C"], ["ann-B"]);
      const mocks: MockedResponse[] = [
        {
          request: {
            query: REQUEST_UPDATE_RELATIONS,
            variables: {
              relationships: [
                {
                  id: "rel-1",
                  sourceIds: ["ann-C"],
                  targetIds: ["ann-B"],
                  relationshipLabelId: mockLabel.id,
                  corpusId: mockCorpus.id,
                  documentId: mockDocument.id,
                },
              ],
            },
          },
          result: { data: { updateRelationships: { ok: true } } },
        },
      ];

      const { result } = renderHook(
        () => ({
          removeFromRel: useRemoveAnnotationFromRelationship(),
          state: usePdfAnnotations(),
        }),
        { wrapper: buildWrapper({ mocks, initialRelations: [rel] }) }
      );

      await act(async () => {
        await result.current.removeFromRel("ann-A", "rel-1");
      });

      expect(result.current.state.pdfAnnotations.relations).toHaveLength(1);
      expect(
        result.current.state.pdfAnnotations.relations[0].sourceIds
      ).toEqual(["ann-C"]);
    });

    it("short-circuits without a corpus/document", async () => {
      const rel = makeRelation("rel-1", ["a"], ["b"]);
      const { result } = renderHook(
        () => ({
          removeFromRel: useRemoveAnnotationFromRelationship(),
          state: usePdfAnnotations(),
        }),
        {
          wrapper: buildWrapper({
            withCorpus: false,
            initialRelations: [rel],
          }),
        }
      );

      await act(async () => {
        await result.current.removeFromRel("a", "rel-1");
      });

      // Relation still there (no mutation fired)
      expect(result.current.state.pdfAnnotations.relations).toHaveLength(1);
    });
  });
});
