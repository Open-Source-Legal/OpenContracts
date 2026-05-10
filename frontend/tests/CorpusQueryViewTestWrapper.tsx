import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { Provider } from "jotai";
import { MemoryRouter } from "react-router-dom";
import {
  GET_CORPUS_ARTICLE,
  GET_CORPUS_CONVERSATIONS,
  GET_CORPUS_STATS,
  GET_BADGES,
} from "../src/graphql/queries";
import { CorpusQueryView } from "../src/views/CorpusQueryView";
import { showQueryViewState } from "../src/graphql/cache";
import { CorpusType } from "../src/types/graphql-api";

interface Props {
  opened_corpus: CorpusType | null;
  initialQueryViewState?: "ASK" | "VIEW" | "DETAILS";
  canUpdate?: boolean;
}

const noop = () => {};

const baseStats = {
  totalDocs: 0,
  totalAnnotations: 0,
  totalAnalyses: 0,
  totalExtracts: 0,
  totalThreads: 0,
};

const buildBaseMocks = (corpusId: string | undefined): MockedResponse[] => {
  if (!corpusId) return [];
  return [
    {
      request: {
        query: GET_CORPUS_ARTICLE,
        variables: { corpusId, title: "Readme.CAML" },
      },
      result: {
        data: {
          documents: { edges: [], __typename: "DocumentTypeConnection" },
        },
      },
    },
    {
      request: {
        query: GET_CORPUS_CONVERSATIONS,
        variables: { corpusId },
      },
      result: {
        data: {
          conversations: {
            edges: [],
            pageInfo: {
              hasNextPage: false,
              hasPreviousPage: false,
              startCursor: null,
              endCursor: null,
              __typename: "PageInfo",
            },
            __typename: "ConversationTypeConnection",
          },
        },
      },
    },
    {
      request: {
        query: GET_CORPUS_STATS,
        variables: { corpusId },
      },
      result: {
        data: {
          corpusStats: {
            totalDocs: 0,
            totalAnnotations: 0,
            totalAnalyses: 0,
            totalExtracts: 0,
            totalThreads: 0,
            __typename: "CorpusStatsType",
          },
        },
      },
    },
    {
      request: {
        query: GET_BADGES,
        variables: { corpusId },
      },
      result: {
        data: {
          badges: { edges: [], __typename: "BadgeTypeConnection" },
        },
      },
    },
  ];
};

/**
 * Thin wrapper that mounts CorpusQueryView with just enough Apollo / Jotai /
 * Router context to exercise the navigation-header and null-corpus branches.
 *
 * The component's heavy children (CorpusHome, CorpusChat) may attempt extra
 * queries this wrapper doesn't mock; they fail silently and don't tear down
 * the parent — assertions therefore target structural elements (the
 * navigation header text, the "No corpus selected" placeholder) that render
 * before any inner-component data settles.
 */
export const CorpusQueryViewTestWrapper: React.FC<Props> = ({
  opened_corpus,
  initialQueryViewState = "ASK",
  canUpdate = false,
}) => {
  // Seed the reactive var on mount so CorpusQueryView reads the requested
  // state. `initialQueryViewState` is a fixed test prop that never changes
  // during a single mount, so this effectively runs once per `mount()`.
  React.useEffect(() => {
    showQueryViewState(initialQueryViewState);
  }, [initialQueryViewState]);

  const cache = new InMemoryCache({
    typePolicies: {
      Query: {
        fields: {
          documents: { merge: false },
          conversations: { merge: false },
          badges: { merge: false },
        },
      },
    },
  });

  const mocks = buildBaseMocks(opened_corpus?.id);

  return (
    <Provider>
      <MemoryRouter initialEntries={["/c/test/corpus"]}>
        <MockedProvider mocks={mocks} cache={cache} addTypename>
          <div style={{ width: 1200, height: 800, display: "flex" }}>
            <CorpusQueryView
              opened_corpus={opened_corpus}
              setShowDescriptionEditor={noop}
              setShowArticleEditor={noop}
              onNavigate={noop}
              onBack={noop}
              canUpdate={canUpdate}
              stats={baseStats}
              statsLoading={false}
              onOpenMobileMenu={noop}
              onSourceNavigate={noop}
              onModeToggle={noop}
              isPowerUserMode={true}
            />
          </div>
        </MockedProvider>
      </MemoryRouter>
    </Provider>
  );
};
