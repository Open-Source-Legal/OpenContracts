import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { Provider } from "jotai";
import { MemoryRouter } from "react-router-dom";
import { relayStylePagination } from "@apollo/client/utilities";
import { DocumentAnnotationIndex } from "../src/components/corpuses/DocumentAnnotationIndex";
import { GET_DOCUMENT_ANNOTATION_INDEX } from "../src/graphql/queries";
import { openedCorpus, tocExpandAll } from "../src/graphql/cache";
import {
  DOCUMENT_ANNOTATION_INDEX_LIMIT,
  OC_SECTION_LABEL,
} from "../src/assets/configurations/constants";

// Test IDs
const TEST_DOCUMENT_ID = "doc-1";
const TEST_CORPUS_ID = "corpus-1";

// Mock corpus for navigation context
const mockCorpus = {
  id: TEST_CORPUS_ID,
  slug: "test-corpus",
  creator: { id: "user-1", slug: "test-user" },
};

// Mock annotation index entries
const mockSectionAnnotations = [
  {
    node: {
      id: "annot-1",
      rawText: "Chapter 1: Introduction",
      longDescription:
        "This chapter provides an overview of the document's purpose, scope, and key definitions used throughout.",
      page: 1,
      parent: null,
      __typename: "AnnotationType",
    },
    __typename: "AnnotationTypeEdge",
  },
  {
    node: {
      id: "annot-2",
      rawText: "1.1 Purpose",
      longDescription:
        "Describes the primary purpose and objectives of this agreement between the parties.",
      page: 2,
      parent: { id: "annot-1" },
      __typename: "AnnotationType",
    },
    __typename: "AnnotationTypeEdge",
  },
  {
    node: {
      id: "annot-3",
      rawText: "1.2 Definitions",
      longDescription:
        "Key terms and definitions used throughout the document including *Effective Date*, *Territory*, and *Licensed Materials*.",
      page: 3,
      parent: { id: "annot-1" },
      __typename: "AnnotationType",
    },
    __typename: "AnnotationTypeEdge",
  },
  {
    node: {
      id: "annot-4",
      rawText: "Chapter 2: Terms and Conditions",
      longDescription:
        "Core terms governing the relationship between parties, including payment schedules, deliverables, and timelines.",
      page: 5,
      parent: null,
      __typename: "AnnotationType",
    },
    __typename: "AnnotationTypeEdge",
  },
  {
    node: {
      id: "annot-5",
      rawText: "2.1 Payment Terms",
      longDescription:
        "Details payment amounts, schedules, currencies, and late payment penalties.",
      page: 6,
      parent: { id: "annot-4" },
      __typename: "AnnotationType",
    },
    __typename: "AnnotationTypeEdge",
  },
  {
    node: {
      id: "annot-6",
      rawText: "Chapter 3: Liability",
      longDescription: null,
      page: 10,
      parent: null,
      __typename: "AnnotationType",
    },
    __typename: "AnnotationTypeEdge",
  },
];

// Cache configuration.
// Production cache.ts keys the `annotations` field by alias + filter
// arguments (ContextAwareRelayStylePaginationKeyArgsFunction). Here we use the
// equivalent explicit field-argument keyArgs for per-variable cache isolation
// in tests. The argument names (documentId, corpusId, annotationLabel_Text)
// match the GraphQL field arguments in GET_DOCUMENT_ANNOTATION_INDEX, per
// CLAUDE.md pitfall #15.
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
      AnnotationType: {
        keyFields: ["id"],
      },
    },
  });

export type MockType = "default" | "empty" | "noDescriptions" | "flat";

interface Props {
  mockType?: MockType;
  maxDepth?: number;
  embedded?: boolean;
  filterQuery?: string;
}

export const DocumentAnnotationIndexTestWrapper: React.FC<Props> = ({
  mockType = "default",
  maxDepth = 6,
  embedded = false,
  filterQuery,
}) => {
  // Set up navigation context
  React.useEffect(() => {
    openedCorpus(mockCorpus as any);
    tocExpandAll(false);
    return () => {
      openedCorpus(null);
      tocExpandAll(false);
    };
  }, []);

  const getMocks = (): MockedResponse[] => {
    const variables = {
      documentId: TEST_DOCUMENT_ID,
      corpusId: TEST_CORPUS_ID,
      labelText: OC_SECTION_LABEL,
      first: DOCUMENT_ANNOTATION_INDEX_LIMIT,
    };

    if (mockType === "empty") {
      const emptyMock = {
        request: { query: GET_DOCUMENT_ANNOTATION_INDEX, variables },
        result: {
          data: {
            annotations: {
              edges: [],
              totalCount: 0,
              __typename: "AnnotationTypeConnection",
            },
          },
        },
      };
      return [emptyMock, { ...emptyMock }];
    }

    if (mockType === "noDescriptions") {
      const noDescEntries = mockSectionAnnotations.map((e) => ({
        ...e,
        node: { ...e.node, longDescription: null },
      }));
      const mock = {
        request: { query: GET_DOCUMENT_ANNOTATION_INDEX, variables },
        result: {
          data: {
            annotations: {
              edges: noDescEntries,
              totalCount: noDescEntries.length,
              __typename: "AnnotationTypeConnection",
            },
          },
        },
      };
      return [mock, { ...mock }];
    }

    if (mockType === "flat") {
      // All root-level, no hierarchy
      const flatEntries = mockSectionAnnotations.map((e) => ({
        ...e,
        node: { ...e.node, parent: null },
      }));
      const mock = {
        request: { query: GET_DOCUMENT_ANNOTATION_INDEX, variables },
        result: {
          data: {
            annotations: {
              edges: flatEntries,
              totalCount: flatEntries.length,
              __typename: "AnnotationTypeConnection",
            },
          },
        },
      };
      return [mock, { ...mock }];
    }

    // Default: hierarchical with descriptions
    const defaultMock = {
      request: { query: GET_DOCUMENT_ANNOTATION_INDEX, variables },
      result: {
        data: {
          annotations: {
            edges: mockSectionAnnotations,
            totalCount: mockSectionAnnotations.length,
            __typename: "AnnotationTypeConnection",
          },
        },
      },
    };
    return [defaultMock, { ...defaultMock }];
  };

  return (
    <Provider>
      <MemoryRouter>
        <MockedProvider
          mocks={getMocks()}
          cache={createTestCache()}
          addTypename
        >
          <DocumentAnnotationIndex
            documentId={TEST_DOCUMENT_ID}
            corpusId={TEST_CORPUS_ID}
            maxDepth={maxDepth}
            embedded={embedded}
            filterQuery={filterQuery}
          />
        </MockedProvider>
      </MemoryRouter>
    </Provider>
  );
};
