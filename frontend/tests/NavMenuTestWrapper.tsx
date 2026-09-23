import React, { useState, useEffect } from "react";
import { MockedProvider } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { MemoryRouter, useLocation } from "react-router-dom";
import { Provider as JotaiProvider } from "jotai";
import { Auth0Provider } from "@auth0/auth0-react";
import {
  backendUserObj,
  userObj,
  authToken,
  authStatusVar,
  showExportModal,
} from "../src/graphql/cache";
import { NavMenu } from "../src/components/layout/NavMenu";

// Mock users for testing - exported for test file type references
export interface MockUserType {
  id: string;
  username: string;
  name?: string;
  email: string;
  isSuperuser: boolean;
}

interface NavMenuTestWrapperProps {
  initialPath?: string;
  mockUser?: MockUserType | null;
  showLocation?: boolean;
}

function CurrentLocation() {
  return <output aria-label="Current path">{useLocation().pathname}</output>;
}

// Create a minimal cache
const createCache = () => new InMemoryCache();

/**
 * Test wrapper for NavMenu component tests.
 * Provides Apollo MockedProvider, MemoryRouter, and Auth0Provider context.
 *
 * Note: useWindowDimensions hook reads from window.innerWidth,
 * so viewport size is controlled via page.setViewportSize() in tests.
 */
export const NavMenuTestWrapper: React.FC<NavMenuTestWrapperProps> = ({
  initialPath = "/",
  mockUser = null,
  showLocation = false,
}) => {
  // Track when auth state is ready
  const [isReady, setIsReady] = useState(false);

  // Set up Apollo cache state before first render
  useEffect(() => {
    userObj(mockUser);
    backendUserObj(mockUser);
    authToken(mockUser ? "mock-token" : "");
    authStatusVar(mockUser ? "AUTHENTICATED" : "ANONYMOUS");
    showExportModal(false);
    // Small delay to ensure reactive vars propagate
    const timer = setTimeout(() => setIsReady(true), 10);
    return () => clearTimeout(timer);
  }, [mockUser]);

  // Don't render NavMenu until auth state is set
  if (!isReady) {
    return <div data-testid="loading">Loading...</div>;
  }

  return (
    <Auth0Provider
      domain="test.auth0.com"
      clientId="test-client-id"
      authorizationParams={{ redirect_uri: window.location.origin }}
    >
      <MemoryRouter initialEntries={[initialPath]}>
        {showLocation && <CurrentLocation />}
        <JotaiProvider>
          <MockedProvider mocks={[]} cache={createCache()} addTypename={false}>
            <NavMenu />
          </MockedProvider>
        </JotaiProvider>
      </MemoryRouter>
    </Auth0Provider>
  );
};
