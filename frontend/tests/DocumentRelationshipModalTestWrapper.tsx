import React, { useEffect } from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { Provider, useSetAtom } from "jotai";
import { relayStylePagination } from "@apollo/client/utilities";
import { DocumentRelationshipModal } from "../src/components/documents/DocumentRelationshipModal";
import { GET_DOCUMENTS } from "../src/graphql/queries";
import { openedCorpus } from "../src/graphql/cache";
import { corpusStateAtom } from "../src/components/annotator/context/CorpusAtom";
import { DOCUMENT_PICKER_SEARCH_LIMIT } from "../src/assets/configurations/constants";
import { AnnotationLabelType, LabelType } from "../src/types/graphql-api";

// Test corpus ID
export const TEST_CORPUS_ID = "corpus-1";

// Resolve corpus id for mock + prop: undefined → TEST_CORPUS_ID, null → "" (triggers No-Corpus error), string → as-is.
const resolveCorpusId = (override: string | null | undefined) =>
  override === undefined ? TEST_CORPUS_ID : override ?? "";

// Mock corpus for corpus state
const mockCorpusWithLabelset = {
  id: TEST_CORPUS_ID,
  slug: "test-corpus",
  title: "Test Corpus",
  isPublic: false,
  creator: { id: "user-1", slug: "test-user" },
  labelSet: {
    id: "labelset-1",
    title: "Test Labelset",
    allAnnotationLabels: [],
  },
};

const mockCorpusNoLabelset = {
  id: TEST_CORPUS_ID,
  slug: "test-corpus",
  title: "Test Corpus",
  isPublic: false,
  creator: { id: "user-1", slug: "test-user" },
  labelSet: null,
};

// Mock documents for source and target
export const mockRelationshipDocuments = [
  {
    node: {
      id: "doc-1",
      title: "Source Document 1",
      description: "First source document",
      icon: null,
      slug: "source-document-1",
      pdfFile: "/files/doc1.pdf",
      fileType: "pdf",
      pageCount: 10,
      created: "2025-01-01T00:00:00Z",
      modified: "2025-01-01T00:00:00Z",
      isPublic: false,
      myPermissions: ["read"],
      creator: { id: "user-1", slug: "test-user" },
      __typename: "DocumentType",
    },
    __typename: "DocumentTypeEdge",
  },
  {
    node: {
      id: "doc-2",
      title: "Target Document 1",
      description: "First target document",
      icon: null,
      slug: "target-document-1",
      pdfFile: "/files/doc2.pdf",
      fileType: "pdf",
      pageCount: 5,
      created: "2025-01-01T00:00:00Z",
      modified: "2025-01-01T00:00:00Z",
      isPublic: false,
      myPermissions: ["read"],
      creator: { id: "user-1", slug: "test-user" },
      __typename: "DocumentType",
    },
    __typename: "DocumentTypeEdge",
  },
  {
    node: {
      id: "doc-3",
      title: "Target Document 2",
      description: "Second target document",
      icon: null,
      slug: "target-document-2",
      pdfFile: "/files/doc3.pdf",
      fileType: "pdf",
      pageCount: 8,
      created: "2025-01-01T00:00:00Z",
      modified: "2025-01-01T00:00:00Z",
      isPublic: false,
      myPermissions: ["read"],
      creator: { id: "user-1", slug: "test-user" },
      __typename: "DocumentType",
    },
    __typename: "DocumentTypeEdge",
  },
];

// Cache configuration
const createTestCache = () =>
  new InMemoryCache({
    typePolicies: {
      Query: {
        fields: {
          documents: relayStylePagination(),
        },
      },
      DocumentType: {
        keyFields: ["id"],
      },
    },
  });

interface Props {
  open?: boolean;
  onClose?: () => void;
  onSuccess?: () => void;
  initialSourceIds?: string[];
  initialTargetIds?: string[];
  /** Optional pre-populated relationship labels (useful to test label picker) */
  relationLabels?: AnnotationLabelType[];
  /** When true, use a corpus without a labelset (to surface warning). */
  withoutLabelset?: boolean;
  /** Optional corpusId override (used to test missing corpus context). */
  corpusIdOverride?: string | null;
  /** Additional Apollo mocks to append to the default GET_DOCUMENTS mocks. */
  extraMocks?: MockedResponse[];
}

// Inner component that sets up Jotai atoms
const ModalWithState: React.FC<Props> = ({
  open = true,
  onClose = () => {},
  onSuccess = () => {},
  initialSourceIds = ["doc-1"],
  initialTargetIds = [],
  relationLabels = [],
  withoutLabelset = false,
  corpusIdOverride,
}) => {
  const setCorpusState = useSetAtom(corpusStateAtom);
  const corpus = withoutLabelset
    ? mockCorpusNoLabelset
    : mockCorpusWithLabelset;

  useEffect(() => {
    openedCorpus(corpus as any);
    setCorpusState({
      selectedCorpus: corpus as any,
      myPermissions: [],
      spanLabels: [],
      humanSpanLabels: [],
      relationLabels,
      docTypeLabels: [],
      humanTokenLabels: [],
      allowComments: true,
      isLoading: false,
    });

    return () => {
      openedCorpus(null);
    };
  }, [setCorpusState, withoutLabelset, relationLabels]);

  return (
    <DocumentRelationshipModal
      open={open}
      onClose={onClose}
      corpusId={resolveCorpusId(corpusIdOverride)}
      initialSourceIds={initialSourceIds}
      initialTargetIds={initialTargetIds}
      onSuccess={onSuccess}
    />
  );
};

export const DocumentRelationshipModalTestWrapper: React.FC<Props> = (
  props
) => {
  const { extraMocks = [] } = props;

  // Build mocks. MockedProvider consumes each mock once, so the initial query
  // plus any refetch both need their own entry. Invoke the factory twice to
  // ensure each entry is an independent object literal (no shared references).
  const getMocks = (): MockedResponse[] => {
    const buildDocumentsMock = (): MockedResponse => ({
      request: {
        query: GET_DOCUMENTS,
        variables: {
          inCorpusWithId: resolveCorpusId(props.corpusIdOverride),
          textSearch: undefined,
          limit: DOCUMENT_PICKER_SEARCH_LIMIT,
          annotateDocLabels: false,
          includeMetadata: false,
          includeCaml: false,
        },
      },
      result: {
        data: {
          documents: {
            edges: mockRelationshipDocuments,
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

    return [buildDocumentsMock(), buildDocumentsMock(), ...extraMocks];
  };

  return (
    <Provider>
      <MockedProvider mocks={getMocks()} cache={createTestCache()} addTypename>
        <ModalWithState {...props} />
      </MockedProvider>
    </Provider>
  );
};

export function makeMockRelationLabel(
  overrides: Partial<AnnotationLabelType> = {}
): AnnotationLabelType {
  return {
    id: "label-1",
    text: "references",
    description: "Document references another",
    color: "#14b8a6",
    // `icon` is `?: string` on AnnotationLabelType (no `null` in the type),
    // so leave it undefined for fixtures that don't need an icon.
    labelType: LabelType.RelationshipLabel,
    myPermissions: [],
    isPublic: false,
    readonly: false,
    created: "2025-01-01T00:00:00Z",
    modified: "2025-01-01T00:00:00Z",
    __typename: "AnnotationLabelType",
    ...overrides,
  } as AnnotationLabelType;
}
