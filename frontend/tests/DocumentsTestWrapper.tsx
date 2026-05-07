import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { relayStylePagination } from "@apollo/client/utilities";
import { MemoryRouter } from "react-router-dom";
import { Provider as JotaiProvider } from "jotai";
import { Documents } from "../src/views/Documents";

interface DocumentsTestWrapperProps {
  mocks: MockedResponse[];
  withRelayCache?: boolean;
}

export const DocumentsTestWrapper: React.FC<DocumentsTestWrapperProps> = ({
  mocks,
  withRelayCache = false,
}) => {
  // Defining the cache inside the wrapper avoids Playwright CT trying to
  // serialize a recursive InMemoryCache instance through the test boundary.
  const cache = withRelayCache
    ? new InMemoryCache({
        typePolicies: {
          Query: {
            fields: {
              documents: relayStylePagination([
                "inCorpusWithId",
                "inFolderId",
                "textSearch",
                "hasLabelWithId",
                "hasAnnotationsWithIds",
                "includeCaml",
                "title",
              ]),
            },
          },
        },
        addTypename: false,
      })
    : undefined;

  return (
    <MockedProvider mocks={mocks} cache={cache} addTypename={false}>
      <MemoryRouter>
        <JotaiProvider>
          <Documents />
        </JotaiProvider>
      </MemoryRouter>
    </MockedProvider>
  );
};
