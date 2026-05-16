import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { Provider as JotaiProvider } from "jotai";
import { MemoryRouter } from "react-router-dom";
import { MotionConfig } from "framer-motion";
import { CorpusChat } from "../src/components/corpuses/CorpusChat";
import { authToken, userObj } from "../src/graphql/cache";
import { relayStylePagination } from "@apollo/client/utilities";

// Module-level init: the WebSocket effect in CorpusChat needs authToken/userObj
// populated *before* the first render. Calling these in the component body is a
// side-effect-in-render that fires on every re-render (and in StrictMode, twice
// on mount). Priming them once at module load is equivalent, safer, and fires
// exactly before the first render of any test using this wrapper.
authToken("test-auth-token");
userObj({
  id: "test-user",
  email: "test@example.com",
  username: "testuser",
});

const createTestCache = () =>
  new InMemoryCache({
    typePolicies: {
      Query: {
        fields: {
          conversations: relayStylePagination(["corpusId", "conversationType"]),
          chatMessages: {
            keyArgs: ["conversationId"],
            merge(_existing = [], incoming: unknown[]) {
              return incoming;
            },
          },
        },
      },
    },
  });

interface Props {
  mocks: ReadonlyArray<MockedResponse>;
  corpusId: string;
  /** Set to true to start in the new-chat view rather than the conversation list */
  forceNewChat?: boolean;
  initialQuery?: string;
  onNavigateHome?: () => void;
  onMessageSelect?: (id: string) => void;
  /** Notified when the inner conversation/list view-mode toggles. */
  onViewModeChange?: (isInConversation: boolean) => void;
  /** Hide the filter-bar Back button in the conversation-list view. */
  hideListBackButton?: boolean;
}

export const CorpusChatTestWrapper: React.FC<Props> = ({
  mocks,
  corpusId,
  forceNewChat = false,
  initialQuery,
  onNavigateHome,
  onMessageSelect = () => {},
  onViewModeChange,
  hideListBackButton,
}) => {
  return (
    <MemoryRouter initialEntries={["/"]}>
      <JotaiProvider>
        <MockedProvider mocks={mocks} cache={createTestCache()} addTypename>
          <MotionConfig reducedMotion="always">
            <div style={{ height: "600px", width: "400px", display: "flex" }}>
              <CorpusChat
                corpusId={corpusId}
                showLoad={false}
                setShowLoad={() => {}}
                onMessageSelect={onMessageSelect}
                forceNewChat={forceNewChat}
                initialQuery={initialQuery}
                onNavigateHome={onNavigateHome}
                onViewModeChange={onViewModeChange}
                hideListBackButton={hideListBackButton}
              />
            </div>
          </MotionConfig>
        </MockedProvider>
      </JotaiProvider>
    </MemoryRouter>
  );
};
