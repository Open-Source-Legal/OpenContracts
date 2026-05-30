import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
// Split-import rule (CLAUDE.md #16): JSX-component imports stay in their own
// statement, separate from the helper/var import below.
import { CorpusCategoryManagement } from "../src/components/admin/corpus_categories/CorpusCategoryManagement";
import { backendUserObj } from "../src/graphql/cache";
import { UserType } from "../src/types/graphql-api";

export const CorpusCategoryManagementTestWrapper: React.FC<{
  mocks: MockedResponse[];
  isSuperuser?: boolean;
}> = ({ mocks, isSuperuser = true }) => {
  // The component gates on the backendUserObj reactive var. Seed it so the
  // panel renders as the corresponding user role.
  const seedUser: UserType = {
    id: "user-1",
    username: "admin",
    email: "admin@test.com",
    isSuperuser,
  };
  backendUserObj(seedUser);

  return (
    <MockedProvider mocks={mocks} addTypename={false}>
      <MemoryRouter>
        <CorpusCategoryManagement />
      </MemoryRouter>
    </MockedProvider>
  );
};
