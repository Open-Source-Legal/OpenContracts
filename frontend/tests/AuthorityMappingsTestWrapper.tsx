import React, { useEffect } from "react";
import { InMemoryCache } from "@apollo/client";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { ToastContainer } from "react-toastify";
import { backendUserObj } from "../src/graphql/cache";
import { AuthorityMappings } from "../src/components/admin/AuthorityMappings";

interface WrapperProps {
  mocks?: MockedResponse[];
  superuser?: boolean;
}

/**
 * Test wrapper for the global authority-mappings panel (mirrors
 * AuthoritySourcesMonitorTestWrapper). Sets the ``backendUserObj`` superuser
 * reactive var in the BROWSER (via useEffect, reset on unmount for test
 * isolation) so the panel's superuser gate passes; provides the Apollo mocks +
 * a router. Per the project convention the fresh InMemoryCache lives inside the
 * wrapper, and ``addTypename:false`` matches the MockedProvider prop so the
 * typename-free mocks keep matching.
 */
export const AuthorityMappingsTestWrapper: React.FC<WrapperProps> = ({
  mocks = [],
  superuser = true,
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
      <MemoryRouter initialEntries={["/admin/authority-mappings"]}>
        <AuthorityMappings />
        <ToastContainer />
      </MemoryRouter>
    </MockedProvider>
  );
};
