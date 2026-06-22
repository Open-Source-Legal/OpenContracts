import React, { useEffect } from "react";
import { InMemoryCache } from "@apollo/client";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { ToastContainer } from "react-toastify";
import { backendUserObj } from "../src/graphql/cache";
import { AuthorityConsole } from "../src/components/admin/authority/AuthorityConsole";

interface WrapperProps {
  mocks?: MockedResponse[];
  superuser?: boolean;
  /** Initial console sub-route, e.g. "/admin/authority/registry/usc-15". */
  initialPath?: string;
}

/**
 * Test wrapper for the unified Authority Console (mirrors
 * AuthorityMappingsTestWrapper). Sets the ``backendUserObj`` superuser reactive
 * var in the BROWSER via useEffect (reset on unmount for test isolation) so the
 * console's authority-admin gate passes; provides the Apollo mocks + a router.
 * The console parses ``location.pathname`` itself, so it is rendered directly
 * under MemoryRouter (no <Routes> needed) and in-component navigate() updates
 * the active tab / selected authority.
 */
export const AuthorityConsoleTestWrapper: React.FC<WrapperProps> = ({
  mocks = [],
  superuser = true,
  initialPath = "/admin/authority/registry",
}) => {
  useEffect(() => {
    backendUserObj({ isSuperuser: superuser } as any);
    return () => {
      backendUserObj(null);
    };
  }, [superuser]);

  return (
    <MockedProvider
      mocks={mocks}
      addTypename={false}
      cache={new InMemoryCache({ addTypename: false })}
    >
      <MemoryRouter initialEntries={[initialPath]}>
        <AuthorityConsole />
        <ToastContainer />
      </MemoryRouter>
    </MockedProvider>
  );
};
