import React from "react";
import { MemoryRouter } from "react-router-dom";
import { Provider } from "jotai";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { relayStylePagination } from "@apollo/client/utilities";

import { MobileSectionsSheet } from "../src/components/knowledge_base/document/layouts/mobile/MobileSectionsSheet";
import { GET_DOCUMENT_ANNOTATION_INDEX } from "../src/graphql/queries";
import {
  DOCUMENT_ANNOTATION_INDEX_LIMIT,
  OC_SECTION_LABEL,
} from "../src/assets/configurations/constants";

const TEST_DOCUMENT_ID = "doc-1";
const TEST_CORPUS_ID = "corpus-1";

/** Minimal shape the harness turns into an OC_SECTION index edge. */
export interface StubSection {
  id: string;
  rawText: string;
  /** 1-based page, rendered verbatim — matches the desktop index. */
  page: number;
}

// Mirror the per-variable keyArgs the production cache derives for the
// `annotations` field (see cache.ts) so the mock isolates by document/label.
const createTestCache = () =>
  new InMemoryCache({
    typePolicies: {
      Query: {
        fields: {
          annotations: relayStylePagination([
            "documentId",
            "corpusId",
            "annotationLabel_Text",
          ]),
        },
      },
      AnnotationType: { keyFields: ["id"] },
    },
  });

/**
 * Test harness for {@link MobileSectionsSheet}. The sheet now loads the
 * document's OC_SECTION index (the same query the desktop "Index" tab uses),
 * so the harness wires a {@link MockedProvider} returning the supplied stub
 * sections as index edges rather than seeding a Jotai atom.
 */
export const MobileSectionsSheetHarness: React.FC<{
  open?: boolean;
  sections?: StubSection[];
  error?: boolean;
  onNavigate?: (annotationId: string) => void;
}> = ({ open = true, sections = [], error = false, onNavigate = () => {} }) => {
  const variables = {
    documentId: TEST_DOCUMENT_ID,
    corpusId: TEST_CORPUS_ID,
    labelText: OC_SECTION_LABEL,
    first: DOCUMENT_ANNOTATION_INDEX_LIMIT,
  };

  const mock: MockedResponse = error
    ? {
        request: { query: GET_DOCUMENT_ANNOTATION_INDEX, variables },
        error: new Error("network failure"),
      }
    : {
        request: { query: GET_DOCUMENT_ANNOTATION_INDEX, variables },
        result: {
          data: {
            annotations: {
              totalCount: sections.length,
              edges: sections.map((s) => ({
                node: {
                  id: s.id,
                  rawText: s.rawText,
                  longDescription: null,
                  page: s.page,
                  parent: null,
                  __typename: "AnnotationType",
                },
                __typename: "AnnotationTypeEdge",
              })),
              __typename: "AnnotationTypeConnection",
            },
          },
        },
      };

  return (
    <MemoryRouter>
      <Provider>
        <MockedProvider
          // Two copies of the mock: the sheet can fire the query twice across
          // an open / refetch cycle, and each MockedProvider mock is consumed
          // by a single matching request.
          mocks={[mock, { ...mock }]}
          cache={createTestCache()}
          addTypename
        >
          <MobileSectionsSheet
            open={open}
            documentId={TEST_DOCUMENT_ID}
            corpusId={TEST_CORPUS_ID}
            onNavigate={onNavigate}
          />
        </MockedProvider>
      </Provider>
    </MemoryRouter>
  );
};
