import React, { useEffect } from "react";
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

  return (
    <MockedProvider mocks={mocks} addTypename={false}>
      <MemoryRouter initialEntries={["/admin/ingestion"]}>
        <IngestionMonitor />
        <ToastContainer />
      </MemoryRouter>
    </MockedProvider>
  );
};
