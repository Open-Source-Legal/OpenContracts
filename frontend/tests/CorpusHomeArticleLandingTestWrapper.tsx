/**
 * Test wrapper for CorpusHome showing article as landing view.
 *
 * Mocks the corpus article query to return a Readme.CAML document
 * so that CorpusHome renders the CAML article as the default landing
 * with floating controls.
 */
import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { relayStylePagination } from "@apollo/client/utilities";
import { MemoryRouter } from "react-router-dom";
import { Provider } from "jotai";

import { CorpusHome } from "../src/components/corpuses/CorpusHome";
import {
  GET_CORPUS_ARTICLE,
  GET_CORPUS_WITH_HISTORY,
} from "../src/graphql/queries";
import { CorpusType } from "../src/types/graphql-api";
import { corpusDetailView } from "../src/graphql/cache";

const MOCK_CORPUS: CorpusType = {
  id: "Q29ycHVzVHlwZTox",
  title: "Supply Chain Analysis",
  description: "A corpus of supply chain agreements",
  icon: "",
  isPublic: false,
  slug: "supply-chain-analysis",
  creator: {
    id: "user-1",
    email: "test@example.com",
    slug: "test-user",
  },
} as CorpusType;

/** Mock: article exists with a txtExtractFile URL */
const articleExistsMock: MockedResponse = {
  request: {
    query: GET_CORPUS_ARTICLE,
    variables: { corpusId: MOCK_CORPUS.id, title: "Readme.CAML" },
  },
  result: {
    data: {
      documents: {
        edges: [
          {
            node: {
              id: "doc-readme-1",
              title: "Readme.CAML",
              txtExtractFile: "blob:caml-content",
              modified: "2024-03-15T10:30:00Z",
              creator: {
                email: "author@example.com",
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

/** Mock: no article exists */
const articleEmptyMock: MockedResponse = {
  request: {
    query: GET_CORPUS_ARTICLE,
    variables: { corpusId: MOCK_CORPUS.id, title: "Readme.CAML" },
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

/** Mock: corpus with history (minimal, needed if CorpusLandingView renders) */
const corpusWithHistoryMock: MockedResponse = {
  request: {
    query: GET_CORPUS_WITH_HISTORY,
    variables: { id: MOCK_CORPUS.id },
  },
  result: {
    data: {
      corpus: {
        id: MOCK_CORPUS.id,
        slug: "supply-chain-analysis",
        title: "Supply Chain Analysis",
        description: "A corpus of supply chain agreements",
        descriptionPreview: "A corpus of supply chain agreements",
        icon: "",
        created: "2024-01-01T00:00:00Z",
        modified: "2024-03-15T10:30:00Z",
        isPublic: false,
        myPermissions: [],
        documentCount: 42,
        license: "",
        licenseLink: "",
        creator: {
          id: "user-1",
          email: "test@example.com",
          slug: "test-user",
          __typename: "UserType",
        },
        labelSet: null,
        descriptionRevisions: [],
        __typename: "CorpusType",
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
      CorpusType: { keyFields: ["id"] },
    },
  });
}

export interface CorpusHomeArticleLandingTestWrapperProps {
  hasArticle?: boolean;
}

export const CorpusHomeArticleLandingTestWrapper: React.FC<
  CorpusHomeArticleLandingTestWrapperProps
> = ({ hasArticle = true }) => {
  // Ensure we start on the landing view
  corpusDetailView("landing");

  const articleMock = hasArticle ? articleExistsMock : articleEmptyMock;

  // Duplicate mocks for potential refetches (cache-and-network policy)
  const mocks: MockedResponse[] = [
    articleMock,
    { ...articleMock },
    corpusWithHistoryMock,
    { ...corpusWithHistoryMock },
  ];

  return (
    <Provider>
      <MemoryRouter>
        <MockedProvider mocks={mocks} cache={createTestCache()} addTypename>
          <CorpusHome
            corpus={MOCK_CORPUS}
            onEditDescription={() => {}}
            onEditArticle={() => {}}
            stats={{
              totalDocs: 42,
              totalAnnotations: 1280,
              totalAnalyses: 5,
              totalExtracts: 3,
              totalThreads: 12,
            }}
            statsLoading={false}
          />
        </MockedProvider>
      </MemoryRouter>
    </Provider>
  );
};
