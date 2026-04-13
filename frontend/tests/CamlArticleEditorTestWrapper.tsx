/**
 * Test wrapper for CamlArticleEditor.
 *
 * Provides MockedProvider with GraphQL mocks for the article query
 * and upload mutation. Wraps in MemoryRouter and Jotai Provider.
 */
import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { relayStylePagination } from "@apollo/client/utilities";
import { MemoryRouter } from "react-router-dom";
import { Provider } from "jotai";

import { CamlArticleEditor } from "../src/components/corpuses/CamlArticleEditor";
import { GET_CORPUS_ARTICLE, GET_EXTRACTS } from "../src/graphql/queries";

const SAMPLE_CAML_CONTENT = `---
version: "1.0"

hero:
  title:
    - "Test Article"
---

::: chapter {#intro}
## Hello World

This is a test article.
:::
`;

/** Mock: no existing article (new article flow) */
const noArticleMock: MockedResponse = {
  request: {
    query: GET_CORPUS_ARTICLE,
    variables: { corpusId: "test-corpus-1", title: "Readme.CAML" },
  },
  result: {
    data: {
      documents: {
        edges: [],
        __typename: "DocumentTypeConnection",
      },
    },
  },
};

/** Mock: existing article */
const existingArticleMock: MockedResponse = {
  request: {
    query: GET_CORPUS_ARTICLE,
    variables: { corpusId: "test-corpus-1", title: "Readme.CAML" },
  },
  result: {
    data: {
      documents: {
        edges: [
          {
            node: {
              id: "doc-article-1",
              title: "Readme.CAML",
              txtExtractFile: null, // Will be overridden by route mock
              modified: "2024-01-15T12:00:00Z",
              creator: {
                email: "test@example.com",
                __typename: "UserType",
              },
              __typename: "DocumentType",
            },
            __typename: "DocumentTypeEdge",
          },
        ],
        __typename: "DocumentTypeConnection",
      },
    },
  },
};

/** Mock: corpus extracts for the extract picker dropdown */
const extractsMock: MockedResponse = {
  request: {
    query: GET_EXTRACTS,
    variables: { corpusId: "test-corpus-1", corpusAction_Isnull: true },
  },
  result: {
    data: {
      extracts: {
        edges: [
          {
            node: {
              id: "extract-1",
              name: "Contract Key Terms",
              corpus: {
                id: "test-corpus-1",
                title: "Test Corpus",
                __typename: "CorpusType",
              },
              fieldset: {
                id: "fs-1",
                name: "Key Terms",
                inUse: true,
                fullColumnList: [{ id: "col-1", __typename: "ColumnType" }],
                __typename: "FieldsetType",
              },
              fullDocumentList: [{ id: "doc-1", __typename: "DocumentType" }],
              creator: {
                id: "user-1",
                username: "testuser",
                slug: "testuser",
                __typename: "UserType",
              },
              created: "2024-01-01T00:00:00Z",
              started: "2024-01-01T00:01:00Z",
              finished: "2024-01-01T00:02:00Z",
              error: null,
              myPermissions: ["read"],
              __typename: "ExtractType",
            },
            __typename: "ExtractTypeEdge",
          },
          {
            node: {
              id: "extract-2",
              name: "Compliance Tracker",
              corpus: {
                id: "test-corpus-1",
                title: "Test Corpus",
                __typename: "CorpusType",
              },
              fieldset: {
                id: "fs-2",
                name: "Compliance Fields",
                inUse: true,
                fullColumnList: [{ id: "col-2", __typename: "ColumnType" }],
                __typename: "FieldsetType",
              },
              fullDocumentList: [{ id: "doc-1", __typename: "DocumentType" }],
              creator: {
                id: "user-1",
                username: "testuser",
                slug: "testuser",
                __typename: "UserType",
              },
              created: "2024-01-02T00:00:00Z",
              started: "2024-01-02T00:01:00Z",
              finished: "2024-01-02T00:02:00Z",
              error: null,
              myPermissions: ["read"],
              __typename: "ExtractType",
            },
            __typename: "ExtractTypeEdge",
          },
          {
            node: {
              id: "extract-3",
              name: "Risk Assessment",
              corpus: {
                id: "test-corpus-1",
                title: "Test Corpus",
                __typename: "CorpusType",
              },
              fieldset: {
                id: "fs-3",
                name: "Risk Fields",
                inUse: true,
                fullColumnList: [{ id: "col-3", __typename: "ColumnType" }],
                __typename: "FieldsetType",
              },
              fullDocumentList: [{ id: "doc-1", __typename: "DocumentType" }],
              creator: {
                id: "user-1",
                username: "testuser",
                slug: "testuser",
                __typename: "UserType",
              },
              created: "2024-01-03T00:00:00Z",
              started: "2024-01-03T00:01:00Z",
              finished: "2024-01-03T00:02:00Z",
              error: null,
              myPermissions: ["read"],
              __typename: "ExtractType",
            },
            __typename: "ExtractTypeEdge",
          },
        ],
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
          __typename: "PageInfo",
        },
        __typename: "ExtractTypeConnection",
      },
    },
  },
};

function createTestCache() {
  return new InMemoryCache({
    typePolicies: {
      Query: {
        fields: {
          documents: relayStylePagination(["inCorpusWithId", "title"]),
        },
      },
      DocumentType: { keyFields: ["id"] },
    },
  });
}

export interface CamlArticleEditorTestWrapperProps {
  hasExistingArticle?: boolean;
  isOpen?: boolean;
  extraMocks?: MockedResponse[];
}

export const CamlArticleEditorTestWrapper: React.FC<
  CamlArticleEditorTestWrapperProps
> = ({ hasExistingArticle = false, isOpen = true, extraMocks = [] }) => {
  const baseMock = hasExistingArticle ? existingArticleMock : noArticleMock;
  // Apollo MockedProvider consumes each mock once per matching request.
  // The editor fires the article query on mount and again on save/refetch
  // cycles, while the extract picker dropdown triggers GET_EXTRACTS on open.
  // Four article mocks cover: initial load + up to 3 save-then-refetch cycles.
  // Three extract mocks cover: initial picker open + up to 2 re-opens.
  const allMocks = [
    baseMock,
    baseMock,
    baseMock,
    baseMock,
    extractsMock,
    extractsMock,
    extractsMock,
    ...extraMocks,
  ];

  return (
    <Provider>
      <MemoryRouter>
        <MockedProvider mocks={allMocks} cache={createTestCache()} addTypename>
          <CamlArticleEditor
            corpusId="test-corpus-1"
            isOpen={isOpen}
            onClose={() => {}}
            onUpdate={() => {}}
          />
        </MockedProvider>
      </MemoryRouter>
    </Provider>
  );
};

export { SAMPLE_CAML_CONTENT };
