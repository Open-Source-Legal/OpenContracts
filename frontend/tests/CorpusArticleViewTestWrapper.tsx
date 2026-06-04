/**
 * Test wrapper for CorpusArticleView.
 *
 * Provides MockedProvider for the GET_CORPUS_ARTICLE query.
 * Also intercepts fetch() for the txtExtractFile URL to return
 * mock CAML content without a real server.
 */
import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { relayStylePagination } from "@apollo/client/utilities";
import { MemoryRouter } from "react-router-dom";
import { Provider } from "jotai";

import { CorpusArticleView } from "../src/components/corpuses/CorpusHome/CorpusArticleView";
import { GET_CORPUS_ARTICLE } from "../src/graphql/queries";
import { CorpusType } from "../src/types/graphql-api";

const MOCK_CORPUS: CorpusType = {
  id: "Q29ycHVzVHlwZTox",
  title: "Supply Chain Analysis",
  description: "A corpus of supply chain agreements",
  icon: "briefcase",
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
    variables: {
      corpusId: MOCK_CORPUS.id,
      title: "Readme.CAML",
    },
  },
  result: {
    data: {
      documents: {
        edges: [
          {
            node: {
              id: "doc-readme-1",
              title: "Readme.CAML",
              txtExtractFile: "/media/test/readme.caml",
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

/** Mock: no article in corpus */
const noArticleMock: MockedResponse = {
  request: {
    query: GET_CORPUS_ARTICLE,
    variables: {
      corpusId: MOCK_CORPUS.id,
      title: "Readme.CAML",
    },
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

export interface CorpusArticleViewTestWrapperProps {
  hasArticle?: boolean;
  corpus?: CorpusType;
  showDocumentsButton?: boolean;
  withModeToggle?: boolean;
  isPowerUserMode?: boolean;
  /** When true, wires an onOpenMobileMenu handler so the mobile menu button
   *  renders. Clicking it reveals a visible marker the test can assert on
   *  (CT can't pass spies through mount). */
  withMobileMenu?: boolean;
}

export const CorpusArticleViewTestWrapper: React.FC<
  CorpusArticleViewTestWrapperProps
> = ({
  hasArticle = true,
  corpus = MOCK_CORPUS,
  showDocumentsButton,
  withModeToggle = false,
  isPowerUserMode = false,
  withMobileMenu = false,
}) => {
  const mock = hasArticle ? articleExistsMock : noArticleMock;
  const [menuOpened, setMenuOpened] = React.useState(false);

  return (
    <Provider>
      <MemoryRouter>
        <MockedProvider
          mocks={[mock, mock]}
          cache={createTestCache()}
          addTypename
        >
          <>
            <CorpusArticleView
              corpus={corpus}
              onBack={() => {}}
              onEditArticle={() => {}}
              showDocumentsButton={showDocumentsButton}
              onModeToggle={withModeToggle ? () => {} : undefined}
              isPowerUserMode={isPowerUserMode}
              onOpenMobileMenu={
                withMobileMenu ? () => setMenuOpened(true) : undefined
              }
              testId="test-corpus-article"
            />
            {menuOpened && (
              <div data-testid="mobile-menu-opened">menu opened</div>
            )}
          </>
        </MockedProvider>
      </MemoryRouter>
    </Provider>
  );
};

export { MOCK_CORPUS };
