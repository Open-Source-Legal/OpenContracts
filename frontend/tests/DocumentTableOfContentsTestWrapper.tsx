import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { Provider } from "jotai";
import { MemoryRouter } from "react-router-dom";
import { relayStylePagination } from "@apollo/client/utilities";
import { DocumentTableOfContents } from "../src/components/corpuses/DocumentTableOfContents";
import {
  GET_DOCUMENT_RELATIONSHIPS,
  GET_CORPUS_DOCUMENTS_FOR_TOC,
  GET_DOCUMENT_ANNOTATION_INDEX,
} from "../src/graphql/queries";
import { openedCorpus, tocExpandAll } from "../src/graphql/cache";
import {
  DOCUMENT_RELATIONSHIP_TOC_LIMIT,
  CORPUS_DOCUMENTS_TOC_LIMIT,
  DOCUMENT_ANNOTATION_INDEX_LIMIT,
  OC_SECTION_LABEL,
} from "../src/assets/configurations/constants";

// Test corpus ID
const TEST_CORPUS_ID = "corpus-1";

// Mock corpus for navigation
const mockCorpus = {
  id: TEST_CORPUS_ID,
  slug: "test-corpus",
  creator: { id: "user-1", slug: "test-user" },
};

// Mock documents for the corpus (used by GET_CORPUS_DOCUMENTS_FOR_TOC)
const mockCorpusDocuments = [
  {
    node: {
      id: "doc-1",
      title: "Parent Document",
      description: "A parent document for testing hierarchy",
      slug: "parent-document",
      icon: null,
      fileType: "application/pdf",
      creator: { slug: "test-user" },
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
      icon: null,
      fileType: "application/pdf",
      creator: { slug: "test-user" },
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
      icon: null,
      fileType: "application/pdf",
      creator: { slug: "test-user" },
      __typename: "DocumentType",
    },
    __typename: "DocumentTypeEdge",
  },
];

// Mock relationships for testing
const mockParentRelationships = [
  {
    node: {
      id: "rel-1",
      relationshipType: "RELATIONSHIP",
      data: null,
      sourceDocument: {
        id: "doc-2",
        title: "Child Document 1",
        icon: null,
        slug: "child-document-1",
        creator: { slug: "test-user" },
      },
      targetDocument: {
        id: "doc-1",
        title: "Parent Document",
        icon: null,
        slug: "parent-document",
        creator: { slug: "test-user" },
      },
      annotationLabel: {
        id: "label-1",
        text: "parent",
        color: "#3b82f6",
        icon: null,
      },
      corpus: { id: TEST_CORPUS_ID },
      creator: { id: "user-1", username: "testuser" },
      created: "2025-01-01T00:00:00Z",
      modified: "2025-01-01T00:00:00Z",
      myPermissions: ["read"],
      __typename: "DocumentRelationshipType",
    },
    __typename: "DocumentRelationshipTypeEdge",
  },
  {
    node: {
      id: "rel-2",
      relationshipType: "RELATIONSHIP",
      data: null,
      sourceDocument: {
        id: "doc-3",
        title: "Child Document 2",
        icon: null,
        slug: "child-document-2",
        creator: { slug: "test-user" },
      },
      targetDocument: {
        id: "doc-1",
        title: "Parent Document",
        icon: null,
        slug: "parent-document",
        creator: { slug: "test-user" },
      },
      annotationLabel: {
        id: "label-1",
        text: "parent",
        color: "#3b82f6",
        icon: null,
      },
      corpus: { id: TEST_CORPUS_ID },
      creator: { id: "user-1", username: "testuser" },
      created: "2025-01-01T00:00:00Z",
      modified: "2025-01-01T00:00:00Z",
      myPermissions: ["read"],
      __typename: "DocumentRelationshipType",
    },
    __typename: "DocumentRelationshipTypeEdge",
  },
];

// Deep hierarchy documents
const mockDeepHierarchyDocuments = [
  {
    node: {
      id: "doc-root",
      title: "Root Document",
      slug: "root-doc",
      icon: null,
      fileType: "application/pdf",
      creator: { slug: "test-user" },
      __typename: "DocumentType",
    },
    __typename: "DocumentTypeEdge",
  },
  {
    node: {
      id: "doc-level1",
      title: "Level 1 Document",
      slug: "level-1",
      icon: null,
      fileType: "application/pdf",
      creator: { slug: "test-user" },
      __typename: "DocumentType",
    },
    __typename: "DocumentTypeEdge",
  },
  {
    node: {
      id: "doc-level2",
      title: "Level 2 Document",
      slug: "level-2",
      icon: null,
      fileType: "application/pdf",
      creator: { slug: "test-user" },
      __typename: "DocumentType",
    },
    __typename: "DocumentTypeEdge",
  },
  {
    node: {
      id: "doc-level3",
      title: "Level 3 Document",
      slug: "level-3",
      icon: null,
      fileType: "application/pdf",
      creator: { slug: "test-user" },
      __typename: "DocumentType",
    },
    __typename: "DocumentTypeEdge",
  },
  {
    node: {
      id: "doc-level4",
      title: "Level 4 Document",
      slug: "level-4",
      icon: null,
      fileType: "application/pdf",
      creator: { slug: "test-user" },
      __typename: "DocumentType",
    },
    __typename: "DocumentTypeEdge",
  },
];

// Deep hierarchy relationships (5 levels: Root -> Level1 -> Level2 -> Level3 -> Level4)
const mockDeepHierarchy = [
  // Level1 -> Root
  {
    node: {
      id: "rel-deep-1",
      relationshipType: "RELATIONSHIP",
      data: null,
      sourceDocument: {
        id: "doc-level1",
        title: "Level 1 Document",
        icon: null,
        slug: "level-1",
        creator: { slug: "test-user" },
      },
      targetDocument: {
        id: "doc-root",
        title: "Root Document",
        icon: null,
        slug: "root-doc",
        creator: { slug: "test-user" },
      },
      annotationLabel: {
        id: "label-1",
        text: "parent",
        color: "#3b82f6",
        icon: null,
      },
      corpus: { id: TEST_CORPUS_ID },
      creator: { id: "user-1", username: "testuser" },
      created: "2025-01-01T00:00:00Z",
      modified: "2025-01-01T00:00:00Z",
      myPermissions: ["read"],
      __typename: "DocumentRelationshipType",
    },
    __typename: "DocumentRelationshipTypeEdge",
  },
  // Level2 -> Level1
  {
    node: {
      id: "rel-deep-2",
      relationshipType: "RELATIONSHIP",
      data: null,
      sourceDocument: {
        id: "doc-level2",
        title: "Level 2 Document",
        icon: null,
        slug: "level-2",
        creator: { slug: "test-user" },
      },
      targetDocument: {
        id: "doc-level1",
        title: "Level 1 Document",
        icon: null,
        slug: "level-1",
        creator: { slug: "test-user" },
      },
      annotationLabel: {
        id: "label-1",
        text: "parent",
        color: "#3b82f6",
        icon: null,
      },
      corpus: { id: TEST_CORPUS_ID },
      creator: { id: "user-1", username: "testuser" },
      created: "2025-01-01T00:00:00Z",
      modified: "2025-01-01T00:00:00Z",
      myPermissions: ["read"],
      __typename: "DocumentRelationshipType",
    },
    __typename: "DocumentRelationshipTypeEdge",
  },
  // Level3 -> Level2
  {
    node: {
      id: "rel-deep-3",
      relationshipType: "RELATIONSHIP",
      data: null,
      sourceDocument: {
        id: "doc-level3",
        title: "Level 3 Document",
        icon: null,
        slug: "level-3",
        creator: { slug: "test-user" },
      },
      targetDocument: {
        id: "doc-level2",
        title: "Level 2 Document",
        icon: null,
        slug: "level-2",
        creator: { slug: "test-user" },
      },
      annotationLabel: {
        id: "label-1",
        text: "parent",
        color: "#3b82f6",
        icon: null,
      },
      corpus: { id: TEST_CORPUS_ID },
      creator: { id: "user-1", username: "testuser" },
      created: "2025-01-01T00:00:00Z",
      modified: "2025-01-01T00:00:00Z",
      myPermissions: ["read"],
      __typename: "DocumentRelationshipType",
    },
    __typename: "DocumentRelationshipTypeEdge",
  },
  // Level4 -> Level3
  {
    node: {
      id: "rel-deep-4",
      relationshipType: "RELATIONSHIP",
      data: null,
      sourceDocument: {
        id: "doc-level4",
        title: "Level 4 Document",
        icon: null,
        slug: "level-4",
        creator: { slug: "test-user" },
      },
      targetDocument: {
        id: "doc-level3",
        title: "Level 3 Document",
        icon: null,
        slug: "level-3",
        creator: { slug: "test-user" },
      },
      annotationLabel: {
        id: "label-1",
        text: "parent",
        color: "#3b82f6",
        icon: null,
      },
      corpus: { id: TEST_CORPUS_ID },
      creator: { id: "user-1", username: "testuser" },
      created: "2025-01-01T00:00:00Z",
      modified: "2025-01-01T00:00:00Z",
      myPermissions: ["read"],
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

// Cache configuration
const createTestCache = () =>
  new InMemoryCache({
    typePolicies: {
      Query: {
        fields: {
          documentRelationships: relayStylePagination([
            "corpusId",
            "documentId",
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
    const relationshipsVariables = {
      corpusId: TEST_CORPUS_ID,
      first: DOCUMENT_RELATIONSHIP_TOC_LIMIT,
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
          query: GET_DOCUMENT_RELATIONSHIPS,
          variables: relationshipsVariables,
        },
        result: {
          data: {
            documentRelationships: {
              edges: [],
              totalCount: 0,
              pageInfo: {
                hasNextPage: false,
                hasPreviousPage: false,
                startCursor: null,
                endCursor: null,
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
          query: GET_DOCUMENT_RELATIONSHIPS,
          variables: relationshipsVariables,
        },
        result: {
          data: {
            documentRelationships: {
              edges: [],
              totalCount: 0,
              pageInfo: {
                hasNextPage: false,
                hasPreviousPage: false,
                startCursor: null,
                endCursor: null,
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
            icon: null,
            fileType: "application/pdf",
            creator: { slug: "test-user" },
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
          query: GET_DOCUMENT_RELATIONSHIPS,
          variables: relationshipsVariables,
        },
        result: {
          data: {
            documentRelationships: {
              edges: [
                {
                  node: {
                    id: "rel-other",
                    relationshipType: "NOTES", // Not a parent relationship
                    data: null,
                    sourceDocument: {
                      id: "doc-a",
                      title: "Doc A",
                      icon: null,
                      slug: "doc-a",
                      creator: { slug: "test-user" },
                    },
                    targetDocument: {
                      id: "doc-b",
                      title: "Doc B",
                      icon: null,
                      slug: "doc-b",
                      creator: { slug: "test-user" },
                    },
                    annotationLabel: null,
                    corpus: { id: TEST_CORPUS_ID },
                    creator: { id: "user-1", username: "testuser" },
                    created: "2025-01-01T00:00:00Z",
                    modified: "2025-01-01T00:00:00Z",
                    myPermissions: ["read"],
                    __typename: "DocumentRelationshipType",
                  },
                  __typename: "DocumentRelationshipTypeEdge",
                },
              ],
              totalCount: 1,
              pageInfo: {
                hasNextPage: false,
                hasPreviousPage: false,
                startCursor: null,
                endCursor: null,
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
            slug: "doc-a",
            icon: null,
            fileType: "application/pdf",
            creator: { slug: "test-user" },
            __typename: "DocumentType",
          },
          __typename: "DocumentTypeEdge",
        },
        {
          node: {
            id: "doc-b",
            title: "Doc B",
            slug: "doc-b",
            icon: null,
            fileType: "application/pdf",
            creator: { slug: "test-user" },
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
        query: GET_DOCUMENT_RELATIONSHIPS,
        variables: relationshipsVariables,
      },
      result: {
        data: {
          documentRelationships: {
            edges: relationshipsMockData,
            totalCount: relationshipsMockData.length,
            pageInfo: {
              hasNextPage: false,
              hasPreviousPage: false,
              startCursor: null,
              endCursor: null,
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
