import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { Provider } from "jotai";
import { CorpusVoteWidget } from "../src/components/corpuses/CorpusVoteWidget";
import {
  UPVOTE_CORPUS,
  DOWNVOTE_CORPUS,
  REMOVE_CORPUS_VOTE,
} from "../src/graphql/mutations";
import { backendUserObj } from "../src/graphql/cache";

/**
 * Shape of the per-mutation response the wrapper uses to seed Apollo mocks.
 * Mirrors the live ``voteCorpus`` / ``removeCorpusVote`` payload so the
 * widget's optimistic-revert path is exercised end-to-end.
 */
interface VoteResponse {
  ok: boolean;
  message?: string;
  obj: {
    id: string;
    upvoteCount: number;
    downvoteCount: number;
    score: number;
    myVote: "UPVOTE" | "DOWNVOTE" | null;
  };
}

interface WrapperProps {
  corpusId?: string;
  initialScore?: number;
  initialMyVote?: "UPVOTE" | "DOWNVOTE" | null;
  /** Backend creator id — pass to make the viewer the owner (self-vote block). */
  creatorId?: string;
  /** Backend viewer id seeded onto ``backendUserObj``. */
  viewerId?: string;
  /** Override the success response for the upvote mutation. */
  upvoteResponse?: VoteResponse;
  /** Override the success response for the downvote mutation. */
  downvoteResponse?: VoteResponse;
  /** Override the success response for the removeCorpusVote mutation. */
  removeResponse?: VoteResponse;
  testId?: string;
}

const defaultResponse = (
  id: string,
  vote: "UPVOTE" | "DOWNVOTE" | null,
  score: number
): VoteResponse => ({
  ok: true,
  message: "ok",
  obj: {
    id,
    upvoteCount: vote === "UPVOTE" ? Math.max(score, 0) : 0,
    downvoteCount: vote === "DOWNVOTE" ? Math.max(-score, 0) : 0,
    score,
    myVote: vote,
    // @ts-expect-error - injected at runtime so MockedProvider (with the
    // default ``addTypename: true``) matches the synthetic ``__typename``
    // it adds to every selection set.
    __typename: "CorpusType",
  },
});

export const CorpusVoteWidgetTestWrapper: React.FC<WrapperProps> = ({
  corpusId = "corpus-1",
  initialScore = 0,
  initialMyVote = null,
  creatorId,
  viewerId = "viewer-1",
  upvoteResponse,
  downvoteResponse,
  removeResponse,
  testId = "vote-widget",
}) => {
  // Seed the backend user — the widget reads ``backendUserObj`` to decide
  // whether the viewer is the corpus creator (self-vote block).
  React.useEffect(() => {
    backendUserObj({ id: viewerId, email: `${viewerId}@example.com` } as any);
    return () => {
      backendUserObj(null);
    };
  }, [viewerId]);

  // Keep mutations in-flight long enough for the test to observe the
  // optimistic UI before ``onCompleted`` clears it.  Without this delay
  // the assertion races the mutation's resolved-state revert.
  const MOCK_DELAY_MS = 1_500;

  const mocks: MockedResponse[] = [
    {
      request: { query: UPVOTE_CORPUS, variables: { corpusId } },
      delay: MOCK_DELAY_MS,
      result: {
        data: {
          voteCorpus:
            upvoteResponse ??
            defaultResponse(corpusId, "UPVOTE", initialScore + 1),
        },
      },
    },
    {
      request: { query: DOWNVOTE_CORPUS, variables: { corpusId } },
      delay: MOCK_DELAY_MS,
      result: {
        data: {
          voteCorpus:
            downvoteResponse ??
            defaultResponse(corpusId, "DOWNVOTE", initialScore - 1),
        },
      },
    },
    {
      request: { query: REMOVE_CORPUS_VOTE, variables: { corpusId } },
      delay: MOCK_DELAY_MS,
      result: {
        data: {
          removeCorpusVote:
            removeResponse ?? defaultResponse(corpusId, null, initialScore - 1),
        },
      },
    },
  ];

  const cache = new InMemoryCache({
    typePolicies: { CorpusType: { keyFields: ["id"] } },
  });

  return (
    <Provider>
      <MockedProvider mocks={mocks} cache={cache}>
        <div style={{ padding: 24 }}>
          <CorpusVoteWidget
            corpusId={corpusId}
            score={initialScore}
            myVote={initialMyVote}
            creatorId={creatorId}
            testId={testId}
          />
        </div>
      </MockedProvider>
    </Provider>
  );
};
