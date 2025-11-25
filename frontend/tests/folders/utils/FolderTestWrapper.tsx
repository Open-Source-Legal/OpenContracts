import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { Provider as JotaiProvider } from "jotai";
import { MemoryRouter } from "react-router-dom";
import { InMemoryCache } from "@apollo/client";

interface FolderTestWrapperProps {
  children: React.ReactNode;
  mocks?: MockedResponse[];
  initialRoute?: string;
}

/**
 * Test wrapper that provides all necessary context for folder components
 * - Apollo MockedProvider for GraphQL
 * - Jotai Provider for state management
 * - MemoryRouter for routing
 */
export function FolderTestWrapper({
  children,
  mocks = [],
  initialRoute = "/",
}: FolderTestWrapperProps) {
  // Create cache inside wrapper to avoid serialization issues
  const cache = new InMemoryCache({
    addTypename: false,
  });

  return (
    <MemoryRouter initialEntries={[initialRoute]}>
      <MockedProvider mocks={mocks} cache={cache} addTypename={false}>
        <JotaiProvider>{children}</JotaiProvider>
      </MockedProvider>
    </MemoryRouter>
  );
}
