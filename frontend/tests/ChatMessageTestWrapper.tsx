import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { Provider as JotaiProvider } from "jotai";
import { MemoryRouter } from "react-router-dom";
import { MotionConfig } from "framer-motion";
import { authToken, userObj } from "../src/graphql/cache";
import { relayStylePagination } from "@apollo/client/utilities";

interface ChatMessageTestWrapperProps {
  mocks?: MockedResponse[];
  children: React.ReactNode;
}

// Create a minimal cache with necessary field policies
const createCache = () =>
  new InMemoryCache({
    typePolicies: {
      Query: {
        fields: {
          annotations: relayStylePagination(),
          documents: relayStylePagination(),
          corpuses: relayStylePagination(),
        },
      },
    },
  });

export const ChatMessageTestWrapper: React.FC<ChatMessageTestWrapperProps> = ({
  mocks = [],
  children,
}) => {
  // Ensure auth token and user are available before ChatMessage mounts
  authToken("test-auth-token");
  userObj({
    id: "test-user",
    email: "test@example.com",
    username: "testuser",
  });

  return (
    <MemoryRouter initialEntries={["/"]}>
      <JotaiProvider>
        <MockedProvider mocks={mocks} cache={createCache()} addTypename={true}>
          <MotionConfig reducedMotion="always">{children}</MotionConfig>
        </MockedProvider>
      </JotaiProvider>
    </MemoryRouter>
  );
};
