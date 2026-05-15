import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { Provider } from "jotai";
import { MemoryRouter } from "react-router-dom";
import { relayStylePagination } from "@apollo/client/utilities";
import { DocumentTableOfContents } from "../src/components/corpuses/DocumentTableOfContents";
import {
  GET_CORPUS_DOCUMENT_TOC_EDGES,
  GET_CORPUS_DOCUMENTS_FOR_TOC,
  GET_DOCUMENT_ANNOTATION_INDEX,
} from "../src/graphql/queries";
import { openedCorpus, tocExpandAll } from "../src/graphql/cache";
import {
  DOCUMENT_RELATIONSHIP_TOC_LIMIT,
  CORPUS_DOCUMENTS_TOC_LIMIT,
  DOCUMENT_ANNOTATION_INDEX_LIMIT,
  OC_SECTION_LABEL,
  DOCUMENT_RELATIONSHIP_TYPE_RELATIONSHIP,
  DOCUMENT_RELATIONSHIP_LABEL_PARENT,
} from "../src/assets/configurations/constants";

// Test corpus ID
const TEST_CORPUS_ID = "corpus-1";

// Mock corpus for navigation
const mockCorpus = {
  id: TEST_CORPUS_ID,
  slug: "test-corpus",
  creator: { id: "user-1", slug: "test-user" },
};

// Mock documents for the corpus (used by GET_CORPUS_DOCUMENTS_FOR_TOC).
// The TOC document query was slimmed down to omit `icon` and `creator` —
// the TOC derives icons from `fileType` and never displays creator info.
const mockCorpusDocuments = [
  {
    node: {
      id: "doc-1",
      title: "Parent Document",
      description: "A parent document for testing hierarchy",
      slug: "parent-document",
      fileType: "application/pdf",
      __typename: "DocumentType",
    },
    __typename: "DocumentTypeEdge",
  },
  {
    node: {
      id: "doc-2",
      title: "Child Document 1",
      description: "First child document",
      slug: "child-document-1",
      fileType: "application/pdf",
      __typename: "DocumentType",
    },
    __typename: "DocumentTypeEdge",
  },
  {
    node: {
      id: "doc-3",
      title: "Child Document 2",
      description: "Second child document",
      slug: "child-document-2",
      fileType: "application/pdf",
      __typename: "DocumentType",
    },
    __typename: "DocumentTypeEdge",
  },
];

// Mock relationships for testing.
// The TOC relationship query was slimmed down to GET_CORPUS_DOCUMENT_TOC_EDGES,
// which only fetches the relationship id + source/target document ids. Server-side
// filters keep the result set restricted to "parent"-labeled RELATIONSHIP rows,
// so the relationship rows themselves carry no relationshipType / label fields.
const mockParentRelationships = [
  {
    node: {
      id: "rel-1",
      sourceDocument: {
        id: "doc-2",
        __typename: "DocumentType",
      },
      targetDocument: {
        id: "doc-1",
        __typename: "DocumentType",
      },
      __typename: "DocumentRelationshipType",
    },
    __typename: "DocumentRelationshipTypeEdge",
  },
  {
    node: {
      id: "rel-2",
      sourceDocument: {
        id: "doc-3",
        __typename: "DocumentType",
      },
      targetDocument: {
        id: "doc-1",
        __typename: "DocumentType",
      },
      __typename: "DocumentRelationshipType",
    },
    __typename: "DocumentRelationshipTypeEdge",
  },
];

// Deep hierarchy documents (TOC document query: no icon/creator fields).
const mockDeepHierarchyDocuments = [
  {
    node: {
      id: "doc-root",
      title: "Root Document",
      description: null,
      slug: "root-doc",
      fileType: "application/pdf",
      __typename: "DocumentType",
    },
    __typename: "DocumentTypeEdge",
  },
  {
    node: {
      id: "doc-level1",
      title: "Level 1 Document",
      description: null,
      slug: "level-1",
      fileType: "application/pdf",
      __typename: "DocumentType",
    },
    __typename: "DocumentTypeEdge",
  },
  {
    node: {
      id: "doc-level2",
      title: "Level 2 Document",
      description: null,
      slug: "level-2",
      fileType: "application/pdf",
      __typename: "DocumentType",
    },
    __typename: "DocumentTypeEdge",
  },
  {
    node: {
      id: "doc-level3",
      title: "Level 3 Document",
      description: null,
      slug: "level-3",
      fileType: "application/pdf",
      __typename: "DocumentType",
    },
    __typename: "DocumentTypeEdge",
  },
  {
    node: {
      id: "doc-level4",
      title: "Level 4 Document",
      description: null,
      slug: "level-4",
      fileType: "application/pdf",
      __typename: "DocumentType",
    },
    __typename: "DocumentTypeEdge",
  },
];

// Deep hierarchy relationships (5 levels: Root -> Level1 -> Level2 -> Level3 -> Level4).
// Uses the lean GET_CORPUS_DOCUMENT_TOC_EDGES shape — only IDs are returned.
const mockDeepHierarchy = [
  // Level1 -> Root
  {
    node: {
      id: "rel-deep-1",
      sourceDocument: { id: "doc-level1", __typename: "DocumentType" },
      targetDocument: { id: "doc-root", __typename: "DocumentType" },
      __typename: "DocumentRelationshipType",
    },
    __typename: "DocumentRelationshipTypeEdge",
  },
  // Level2 -> Level1
  {
    node: {
      id: "rel-deep-2",
      sourceDocument: { id: "doc-level2", __typename: "DocumentType" },
      targetDocument: { id: "doc-level1", __typename: "DocumentType" },
      __typename: "DocumentRelationshipType",
    },
    __typename: "DocumentRelationshipTypeEdge",
  },
  // Level3 -> Level2
  {
    node: {
      id: "rel-deep-3",
      sourceDocument: { id: "doc-level3", __typename: "DocumentType" },
      targetDocument: { id: "doc-level2", __typename: "DocumentType" },
      __typename: "DocumentRelationshipType",
    },
    __typename: "DocumentRelationshipTypeEdge",
  },
  // Level4 -> Level3
  {
    node: {
      id: "rel-deep-4",
      sourceDocument: { id: "doc-level4", __typename: "DocumentType" },
      targetDocument: { id: "doc-level3", __typename: "DocumentType" },
      __typename: "DocumentRelationshipType",
    },
    __typename: "DocumentRelationshipTypeEdge",
  },
];

// Sections for Parent Document (doc-1)
const parentDocSections = [
  {
    node: {
      id: "annot-p1",
      rawText: "1. Introduction",
      longDescription: "Overview of the agreement structure and purpose.",
      page: 1,
      parent: null,
      __typename: "AnnotationType" as const,
    },
    __typename: "AnnotationTypeEdge" as const,
  },
  {
    node: {
      id: "annot-p2",
      rawText: "1.1 Scope",
      longDescription: null,
      page: 2,
      parent: { id: "annot-p1" },
      __typename: "AnnotationType" as const,
    },
    __typename: "AnnotationTypeEdge" as const,
  },
  {
    node: {
      id: "annot-p3",
      rawText: "2. Terms and Conditions",
      longDescription: "Core terms governing the relationship between parties.",
      page: 4,
      parent: null,
      __typename: "AnnotationType" as const,
    },
    __typename: "AnnotationTypeEdge" as const,
  },
];

// Sections for Child Document 1 (doc-2)
const child1DocSections = [
  {
    node: {
      id: "annot-c1",
      rawText: "A. Definitions",
      longDescription: null,
      page: 1,
      parent: null,
      __typename: "AnnotationType" as const,
    },
    __typename: "AnnotationTypeEdge" as const,
  },
  {
    node: {
      id: "annot-c2",
      rawText: "B. Obligations",
      longDescription: null,
      page: 3,
      parent: null,
      __typename: "AnnotationType" as const,
    },
    __typename: "AnnotationTypeEdge" as const,
  },
];

// Sections for Child Document 2 (doc-3)
const child2DocSections = [
  {
    node: {
      id: "annot-d1",
      rawText: "I. Liability",
      longDescription: null,
      page: 1,
      parent: null,
      __typename: "AnnotationType" as const,
    },
    __typename: "AnnotationTypeEdge" as const,
  },
];

// Helper: create an annotation index mock with specific entries
const annotationIndexMockWithEntries = (
  documentId: string,
  entries: typeof parentDocSections
): MockedResponse => ({
  request: {
    query: GET_DOCUMENT_ANNOTATION_INDEX,
    variables: {
      documentId,
      corpusId: TEST_CORPUS_ID,
      labelText: OC_SECTION_LABEL,
      first: DOCUMENT_ANNOTATION_INDEX_LIMIT,
    },
  },
  result: {
    data: {
      annotations: {
        edges: entries,
        totalCount: entries.length,
        __typename: "AnnotationTypeConnection",
      },
    },
  },
});

// Helper: create an empty annotation index mock for a given document ID
const emptyAnnotationIndexMock = (documentId: string): MockedResponse => ({
  request: {
    query: GET_DOCUMENT_ANNOTATION_INDEX,
    variables: {
      documentId,
      corpusId: TEST_CORPUS_ID,
      labelText: OC_SECTION_LABEL,
      first: DOCUMENT_ANNOTATION_INDEX_LIMIT,
    },
  },
  result: {
    data: {
      annotations: {
        edges: [],
        totalCount: 0,
        __typename: "AnnotationTypeConnection",
      },
    },
  },
});

// Cache configuration.
// NOTE: keyArgs must match GraphQL FIELD ARGUMENT names, not variable names.
// The lean TOC edges query uses `corpusId`, `relationshipType`, and
// `annotationLabelText` as field arguments on `documentRelationships`, so the
// pagination key must include all three to isolate TOC results from any other
// `documentRelationships` cache entries.
const createTestCache = () =>
  new InMemoryCache({
    typePolicies: {
      Query: {
        fields: {
          documentRelationships: relayStylePagination([
            "corpusId",
            "documentId",
            "relationshipType",
            "annotationLabelText",
          ]),
          documents: relayStylePagination(["inCorpusWithId"]),
          annotations: relayStylePagination([
            "documentId",
            "corpusId",
            "annotationLabel_Text",
          ]),
        },
      },
      DocumentRelationshipType: {
        keyFields: ["id"],
      },
      DocumentType: {
        keyFields: ["id"],
      },
      AnnotationType: {
        keyFields: ["id"],
      },
    },
  });

interface Props {
  mockType?:
    | "default"
    | "empty"
    | "singleStandalone"
    | "noParentRelationships"
    | "deepHierarchy"
    | "hybrid";
  maxDepth?: number;
}

export const DocumentTableOfContentsTestWrapper: React.FC<Props> = ({
  mockType = "default",
  maxDepth = 4,
}) => {
  // Set up the opened corpus for navigation and reset tocExpandAll
  React.useEffect(() => {
    openedCorpus(mockCorpus as any);
    tocExpandAll(false); // Ensure clean state for tests
    return () => {
      openedCorpus(null);
      tocExpandAll(false);
    };
  }, []);

  // Build mocks based on mockType
  const getMocks = (): MockedResponse[] => {
    // The lean TOC edges query supplies the relationship_type / label filters
    // server-side; they must match the variables the component sends exactly,
    // since MockedProvider matches mocks by deep-equal variable comparison.
    const relationshipsVariables = {
      corpusId: TEST_CORPUS_ID,
      first: DOCUMENT_RELATIONSHIP_TOC_LIMIT,
      relationshipType: DOCUMENT_RELATIONSHIP_TYPE_RELATIONSHIP,
      annotationLabelText: DOCUMENT_RELATIONSHIP_LABEL_PARENT,
    };

    const documentsVariables = {
      corpusId: TEST_CORPUS_ID,
      first: CORPUS_DOCUMENTS_TOC_LIMIT,
    };

    // Helper to create documents mock
    const createDocumentsMock = (docs: typeof mockCorpusDocuments) => ({
      request: {
        query: GET_CORPUS_DOCUMENTS_FOR_TOC,
        variables: documentsVariables,
      },
      result: {
        data: {
          documents: {
            edges: docs,
            totalCount: docs.length,
            pageInfo: {
              hasNextPage: false,
              hasPreviousPage: false,
              startCursor: null,
              endCursor: null,
            },
            __typename: "DocumentTypeConnection",
          },
        },
      },
    });

    if (mockType === "empty") {
      // Empty corpus - no documents
      const emptyRelationshipsMock = {
        request: {
          query: GET_CORPUS_DOCUMENT_TOC_EDGES,
          variables: relationshipsVariables,
        },
        result: {
          data: {
            documentRelationships: {
              edges: [],
              totalCount: 0,
              pageInfo: {
                hasNextPage: false,
              },
              __typename: "DocumentRelationshipTypeConnection",
            },
          },
        },
      };
      const emptyDocumentsMock = createDocumentsMock([]);
      return [
        emptyRelationshipsMock,
        { ...emptyRelationshipsMock },
        emptyDocumentsMock,
        { ...emptyDocumentsMock },
      ];
    }

    // Build annotation index mocks — populated for "hybrid", empty otherwise
    const buildAnnotationIndexMocks = (): MockedResponse[] => {
      if (mockType === "hybrid") {
        // Each document gets its own section entries
        const pairs: [string, typeof parentDocSections][] = [
          ["doc-1", parentDocSections],
          ["doc-2", child1DocSections],
          ["doc-3", child2DocSections],
        ];
        return pairs.flatMap(([id, entries]) => {
          const mock = annotationIndexMockWithEntries(id, entries);
          return [mock, { ...mock }];
        });
      }

      // All other types get empty annotation index mocks
      const getDocumentIds = (): string[] => {
        if (mockType === "singleStandalone") return ["doc-single"];
        if (mockType === "noParentRelationships") return ["doc-a", "doc-b"];
        if (mockType === "deepHierarchy")
          return [
            "doc-root",
            "doc-level1",
            "doc-level2",
            "doc-level3",
            "doc-level4",
          ];
        return ["doc-1", "doc-2", "doc-3"]; // default
      };
      return getDocumentIds().flatMap((id) => {
        const mock = emptyAnnotationIndexMock(id);
        return [mock, { ...mock }];
      });
    };
    const annotationIndexMocks = buildAnnotationIndexMocks();

    if (mockType === "singleStandalone") {
      const emptyRelationshipsMock = {
        request: {
          query: GET_CORPUS_DOCUMENT_TOC_EDGES,
          variables: relationshipsVariables,
        },
        result: {
          data: {
            documentRelationships: {
              edges: [],
              totalCount: 0,
              pageInfo: {
                hasNextPage: false,
              },
              __typename: "DocumentRelationshipTypeConnection",
            },
          },
        },
      };
      const singleDocumentMock = createDocumentsMock([
        {
          node: {
            id: "doc-single",
            title: "Single Standalone Document",
            description: "Only document in this corpus",
            slug: "single-standalone-document",
            fileType: "application/pdf",
            __typename: "DocumentType",
          },
          __typename: "DocumentTypeEdge",
        },
      ]);
      return [
        emptyRelationshipsMock,
        { ...emptyRelationshipsMock },
        singleDocumentMock,
        { ...singleDocumentMock },
        ...annotationIndexMocks,
      ];
    }

    if (mockType === "noParentRelationships") {
      // Documents exist but no parent relationships - shows docs as standalone root items
      const noParentRelsMock = {
        request: {
          query: GET_CORPUS_DOCUMENT_TOC_EDGES,
          variables: relationshipsVariables,
        },
        result: {
          data: {
            // The lean TOC edges query already applies server-side filters for
            // relationshipType="RELATIONSHIP" + annotationLabelText="parent",
            // so non-parent relationships (e.g. NOTES) never come back to the
            // client. The mock therefore returns an empty edge list, and the
            // two documents render as standalone root items via
            // GET_CORPUS_DOCUMENTS_FOR_TOC.
            documentRelationships: {
              edges: [],
              totalCount: 0,
              pageInfo: {
                hasNextPage: false,
              },
              __typename: "DocumentRelationshipTypeConnection",
            },
          },
        },
      };
      // Documents for noParentRelationships - these will show as standalone root items
      const standaloneDocsMock = createDocumentsMock([
        {
          node: {
            id: "doc-a",
            title: "Doc A",
            description: null,
            slug: "doc-a",
            fileType: "application/pdf",
            __typename: "DocumentType",
          },
          __typename: "DocumentTypeEdge",
        },
        {
          node: {
            id: "doc-b",
            title: "Doc B",
            description: null,
            slug: "doc-b",
            fileType: "application/pdf",
            __typename: "DocumentType",
          },
          __typename: "DocumentTypeEdge",
        },
      ]);
      return [
        noParentRelsMock,
        { ...noParentRelsMock },
        standaloneDocsMock,
        { ...standaloneDocsMock },
        ...annotationIndexMocks,
      ];
    }

    // Select appropriate mock data for relationships and documents
    // "hybrid" uses the same parent/child structure as "default"
    const relationshipsMockData =
      mockType === "deepHierarchy"
        ? mockDeepHierarchy
        : mockParentRelationships;

    const documentsMockData =
      mockType === "deepHierarchy"
        ? mockDeepHierarchyDocuments
        : mockCorpusDocuments;

    // Return duplicate mocks for cache-and-network fetch policy
    const relationshipsMock = {
      request: {
        query: GET_CORPUS_DOCUMENT_TOC_EDGES,
        variables: relationshipsVariables,
      },
      result: {
        data: {
          documentRelationships: {
            edges: relationshipsMockData,
            totalCount: relationshipsMockData.length,
            pageInfo: {
              hasNextPage: false,
            },
            __typename: "DocumentRelationshipTypeConnection",
          },
        },
      },
    };

    const documentsMock = createDocumentsMock(documentsMockData);

    return [
      relationshipsMock,
      { ...relationshipsMock },
      documentsMock,
      { ...documentsMock },
      ...annotationIndexMocks,
    ];
  };

  return (
    <Provider>
      <MemoryRouter>
        <MockedProvider
          mocks={getMocks()}
          cache={createTestCache()}
          addTypename
        >
          <DocumentTableOfContents
            corpusId={TEST_CORPUS_ID}
            maxDepth={maxDepth}
          />
        </MockedProvider>
      </MemoryRouter>
    </Provider>
  );
};
