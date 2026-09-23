import React, { useMemo, useState } from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { createStore, Provider, useAtomValue } from "jotai";
import { MemoryRouter } from "react-router-dom";
import { AnnotationVersionReviewPanel } from "../src/components/knowledge_base/document/AnnotationVersionReviewPanel";
import { DocumentVersionSelector } from "../src/components/documents/DocumentVersionSelector";
import { corpusStateAtom } from "../src/components/annotator/context/CorpusAtom";
import { selectedDocumentAtom } from "../src/components/annotator/context/DocumentAtom";
import { pendingAnnotationReviewAtom } from "../src/components/annotator/context/AnnotationReviewAtom";
import { pdfAnnotationsAtom } from "../src/components/annotator/context/AnnotationAtoms";
import {
  useCreateAnnotation,
  usePdfAnnotations,
} from "../src/components/annotator/hooks/AnnotationHooks";
import {
  DocTypeAnnotation,
  PdfAnnotations,
  ServerSpanAnnotation,
} from "../src/components/annotator/types/annotations";
import {
  AnnotationLabelType,
  CorpusType,
  DocumentType,
  LabelType,
} from "../src/types/graphql-api";
import {
  AnnotationReviewRow,
  CARRY_FORWARD_ANNOTATION,
  DROP_STALE_ANNOTATION,
  GET_ANNOTATION_REVIEW_STATUS,
  GET_ANNOTATION_VERSION_REVIEW,
  PENDING_VERSION_STATES,
} from "../src/graphql/annotationVersionReview";
import { GET_CORPUS_VERSIONS } from "../src/graphql/queries";

const label = {
  __typename: "AnnotationLabelType",
  id: "label",
  text: "Obligation",
  color: "#345678",
  icon: "",
  description: "",
  labelType: LabelType.SpanLabel,
} as AnnotationLabelType;

const carriedText = (text: string, id: string, start = 14) =>
  new ServerSpanAnnotation(
    0,
    label,
    text,
    false,
    { start, end: start + text.length, text },
    [],
    false,
    false,
    false,
    id
  );

/** Stands in for the viewer: its saved annotations, plus a selection once placing. */
const docLabel = {
  ...label,
  id: "doc-label",
  text: "Services Agreement",
  labelType: LabelType.DocTypeLabel,
} as AnnotationLabelType;

function Viewer() {
  const pending = useAtomValue(pendingAnnotationReviewAtom);
  const create = useCreateAnnotation();
  const { pdfAnnotations } = usePdfAnnotations();
  return (
    <>
      {pending && (
        <button
          onClick={() =>
            void create(carriedText("Notify the new owner.", "selection", 28))
          }
        >
          Select corrected passage
        </button>
      )}
      <ul aria-label="Saved annotations">
        {pdfAnnotations.annotations.map((annotation) => (
          <li key={annotation.id}>{annotation.rawText}</li>
        ))}
      </ul>
    </>
  );
}

export function AnnotationVersionReviewTestWrapper({
  readOnly = false,
  rejectPlacement = false,
  historical = false,
}: {
  readOnly?: boolean;
  rejectPlacement?: boolean;
  /** View the superseded version, whose document label was already approved. */
  historical?: boolean;
}) {
  const [lastPlacement, setLastPlacement] = useState("");
  const setup = useMemo(() => {
    const store = createStore();
    store.set(selectedDocumentAtom, {
      id: "new",
      fileType: "text/plain",
    } as DocumentType);
    store.set(corpusStateAtom, {
      ...store.get(corpusStateAtom),
      selectedCorpus: { id: "corpus" } as CorpusType,
    });
    // The version-up already carried the one unique exact match.
    store.set(
      pdfAnnotationsAtom,
      new PdfAnnotations(
        [carriedText("Pay promptly.", "carried-0")],
        [],
        [new DocTypeAnnotation(docLabel, [], "doc-label", "REAPPROVED")]
      )
    );
    const successorOf = (row: AnnotationReviewRow, rawText: string) => ({
      ...row.annotation,
      id: `carried-${row.annotation.id.slice(-1)}`,
      rawText,
      structural: false,
      myPermissions: ["read_annotation", "update_annotation"],
      linkUrl: null,
    });
    const rows: AnnotationReviewRow[] = [
      "Pay promptly.",
      "Notify the owner.",
      "Removed clause.",
    ].map((rawText, index) => ({
      __typename: "AnnotationVersionReview",
      annotation: {
        __typename: "AnnotationType",
        id: `old-${index}`,
        page: 0,
        rawText,
        json: { start: 0, end: rawText.length, text: rawText },
        annotationLabel: label,
        annotationType: LabelType.SpanLabel,
      },
      state: index === 0 ? "AUTO" : "STALE",
      successor: null,
      reviewedBy: null,
      reviewedAt: null,
    }));
    rows[0].successor = successorOf(rows[0], "Pay promptly.");
    const decide = (variables: Record<string, unknown>, drop: boolean) => {
      const row = rows.find(
        (row) => row.annotation.id === variables.annotationId
      )!;
      const manual = Boolean(variables.placement);
      if (manual) setLastPlacement(JSON.stringify(variables));
      if (manual && rejectPlacement)
        return {
          errors: [
            { message: "The document changed. Reload before reviewing." },
          ],
        };
      row.state = drop ? "DROPPED" : manual ? "CORRECTED" : "REAPPROVED";
      row.reviewedBy = { slug: "reviewer" };
      row.reviewedAt = "2026-09-17T12:00:00Z";
      row.successor = drop
        ? null
        : successorOf(
            row,
            manual ? "Notify the new owner." : row.annotation.rawText
          );
      return {
        data: {
          [drop ? "dropStaleAnnotation" : "carryForwardAnnotation"]: { ...row },
        },
      };
    };
    const variables = { documentId: "new", corpusId: "corpus" };
    const mocks: MockedResponse[] = [
      {
        request: { query: GET_ANNOTATION_REVIEW_STATUS, variables },
        maxUsageCount: Infinity,
        result: () => ({
          data: {
            document: {
              __typename: "DocumentType",
              id: "new",
              isCurrent: !historical,
              parent: { id: "old" },
              annotationsNeedingReview: rows.filter((row) =>
                PENDING_VERSION_STATES.has(row.state)
              ).length,
            },
          },
        }),
      },
      {
        request: { query: GET_ANNOTATION_VERSION_REVIEW, variables },
        maxUsageCount: Infinity,
        result: () => ({
          data: { annotationVersionReview: rows.map((row) => ({ ...row })) },
        }),
      },
      {
        request: { query: CARRY_FORWARD_ANNOTATION },
        variableMatcher: () => true,
        maxUsageCount: Infinity,
        result: (variables) => decide(variables, false),
      },
      {
        request: { query: DROP_STALE_ANNOTATION },
        variableMatcher: () => true,
        maxUsageCount: Infinity,
        result: (variables) => decide(variables, true),
      },
      {
        request: { query: GET_CORPUS_VERSIONS, variables },
        result: {
          data: {
            document: {
              __typename: "DocumentType",
              id: "new",
              corpusVersions: [1, 2].map((number) => ({
                versionNumber: number,
                documentId: number === 1 ? "old" : "new",
                documentSlug: `contract-${number}`,
                isCurrent: number === 2,
                created: "2026-09-17T12:00:00Z",
              })),
            },
          },
        },
      },
    ];
    return { store, mocks };
  }, [rejectPlacement, historical]);
  return (
    <MemoryRouter>
      <Provider store={setup.store}>
        <MockedProvider mocks={setup.mocks} addTypename={false}>
          <>
            <DocumentVersionSelector documentId="new" corpusId="corpus" />
            <AnnotationVersionReviewPanel
              documentId="new"
              corpusId="corpus"
              readOnly={readOnly}
              onPlace={() => undefined}
            />
            <Viewer />
            <output aria-label="Submitted placement">{lastPlacement}</output>
          </>
        </MockedProvider>
      </Provider>
    </MemoryRouter>
  );
}
