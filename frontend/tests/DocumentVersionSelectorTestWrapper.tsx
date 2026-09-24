import React from "react";
import { MockedProvider } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { MemoryRouter, useLocation } from "react-router-dom";
import { GET_ANNOTATION_REVIEW_STATUS } from "../src/graphql/annotationVersionReview";

function CurrentLocation() {
  const location = useLocation();
  return (
    <output aria-label="Current route">
      {location.pathname}
      {location.search}
    </output>
  );
}

export function DocumentVersionSelectorTestWrapper({
  children,
  mocks = [],
  initialRoute = "/d/testuser/test-corpus/test-doc",
}: {
  children: React.ReactNode;
  mocks?: any[];
  initialRoute?: string;
}) {
  const cache = new InMemoryCache({ addTypename: false });
  const statusMock = {
    request: {
      query: GET_ANNOTATION_REVIEW_STATUS,
      variables: mocks[0]?.request.variables,
    },
    result: {
      data: {
        document: {
          id: mocks[0]?.request.variables.documentId,
          isCurrent: true,
          parent: null,
          annotationsNeedingReview: 0,
        },
      },
    },
  };
  return (
    <MemoryRouter initialEntries={[initialRoute]}>
      <MockedProvider
        mocks={[...mocks, statusMock]}
        cache={cache}
        addTypename={false}
      >
        <>
          {children}
          <CurrentLocation />
        </>
      </MockedProvider>
    </MemoryRouter>
  );
}
