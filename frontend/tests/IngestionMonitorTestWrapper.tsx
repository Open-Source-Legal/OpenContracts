import React, { useEffect } from "react";
import { InMemoryCache } from "@apollo/client";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { ToastContainer } from "react-toastify";
import { backendUserObj } from "../src/graphql/cache";
import { IngestionMonitor } from "../src/components/admin/IngestionMonitor";

interface WrapperProps {
  mocks?: MockedResponse[];
  superuser?: boolean;
}

export const IngestionMonitorTestWrapper: React.FC<WrapperProps> = ({
  mocks = [],
  superuser = true,
}) => {
  useEffect(() => {
    backendUserObj({ isSuperuser: superuser } as any);
    return () => {
      backendUserObj(null);
    };
  }, [superuser]);

  // Fresh cache per mount so InMemoryCache type policies never bleed between
  // tests (kept inside the wrapper per the project test-wrapper convention).
  // addTypename:false must match the MockedProvider prop — otherwise the cache
  // injects __typename into the queries and the typename-free mocks no longer
  // match.
  return (
    <MockedProvider
      mocks={mocks}
      addTypename={false}
      cache={new InMemoryCache({ addTypename: false })}
    >
      <MemoryRouter initialEntries={["/admin/ingestion"]}>
        <IngestionMonitor />
        <ToastContainer />
      </MemoryRouter>
    </MockedProvider>
  );
};
