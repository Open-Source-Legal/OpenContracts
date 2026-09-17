import React, { useMemo, useState } from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { createStore, Provider, useAtomValue } from "jotai";
import { MemoryRouter } from "react-router-dom";
import { AnnotationVersionReviewPanel } from "../src/components/knowledge_base/document/AnnotationVersionReviewPanel";
import { DocumentVersionSelector } from "../src/components/documents/DocumentVersionSelector";
import { corpusStateAtom } from "../src/components/annotator/context/CorpusAtom";
import { selectedDocumentAtom } from "../src/components/annotator/context/DocumentAtom";
import { pendingAnnotationReviewAtom } from "../src/components/annotator/context/AnnotationReviewAtom";
import {
  useCreateAnnotation,
  usePdfAnnotations,
} from "../src/components/annotator/hooks/AnnotationHooks";
import { ServerSpanAnnotation } from "../src/components/annotator/types/annotations";
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

function ViewerSelection() {
  const pending = useAtomValue(pendingAnnotationReviewAtom);
  const create = useCreateAnnotation();
  const { pdfAnnotations } = usePdfAnnotations();
  return (
    <>
      {pending && (
        <button
          onClick={() =>
            void create(
              new ServerSpanAnnotation(
                0,
                label,
                "Notify the new owner.",
                false,
                { start: 28, end: 49, text: "Notify the new owner." },
                [],
                false,
                false
              )
            )
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
}: {
  readOnly?: boolean;
  rejectPlacement?: boolean;
}) {
  const [placed, setPlaced] = useState(false);
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
        versionState: "STALE",
      },
      state: "STALE",
      successor: null,
      reviewedBy: null,
      reviewedAt: null,
      proposedPlacement:
        index === 0
          ? {
              json: { start: 14, end: 27, text: rawText },
              raw_text: rawText,
              page: 0,
            }
          : null,
    }));
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
      row.proposedPlacement = null;
      row.reviewedBy = { slug: "reviewer" };
      row.reviewedAt = "2026-09-17T12:00:00Z";
      if (!drop)
        row.successor = {
          ...row.annotation,
          id: `successor-${row.annotation.id}`,
          rawText: manual ? "Notify the new owner." : row.annotation.rawText,
          structural: false,
          myPermissions: ["read_annotation", "update_annotation"],
          linkUrl: null,
        };
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
              isCurrent: true,
              parent: { id: "old" },
              staleAnnotationCount: rows.filter((row) => row.state === "STALE")
                .length,
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
  }, [rejectPlacement]);
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
              onPlace={() => setPlaced(true)}
            />
            {placed && <ViewerSelection />}
            <output aria-label="Submitted placement">{lastPlacement}</output>
          </>
        </MockedProvider>
      </Provider>
    </MemoryRouter>
  );
}
