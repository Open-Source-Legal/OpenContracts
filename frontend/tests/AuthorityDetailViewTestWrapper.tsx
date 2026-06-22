import React, { useState } from "react";
import { InMemoryCache } from "@apollo/client";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { ToastContainer } from "react-toastify";
import { AuthorityDetailView } from "../src/components/admin/authority/AuthorityDetailView";

interface WrapperProps {
  mocks?: MockedResponse[];
  prefix?: string;
}

/**
 * Test wrapper that mounts the single-authority detail view DIRECTLY (rather than
 * via the console → registry → click path) so the heavy editable surface — header
 * edit/save, alias add/remove/save, the shared KeyEquivalence create/edit/delete
 * table, and the danger-zone delete — can be exercised with only the detail query
 * + mutation mocks (no registry stats/list noise).
 *
 * ``onClose`` flips a visible ``detail-closed`` marker and ``onChanged`` bumps a
 * visible counter, so tests can assert the component drove those callbacks
 * (delete / back) without crossing functions over the CT Node↔browser boundary.
 */
export const AuthorityDetailViewTestWrapper: React.FC<WrapperProps> = ({
  mocks = [],
  prefix = "usc-15",
}) => {
  const [closed, setClosed] = useState(false);
  const [changes, setChanges] = useState(0);

  return (
    <MockedProvider
      mocks={mocks}
      addTypename={false}
      cache={new InMemoryCache({ addTypename: false })}
    >
      <MemoryRouter>
        {closed ? (
          <div data-testid="detail-closed">closed</div>
        ) : (
          <AuthorityDetailView
            prefix={prefix}
            onClose={() => setClosed(true)}
            onChanged={() => setChanges((c) => c + 1)}
          />
        )}
        <div data-testid="detail-change-count">{changes}</div>
        <ToastContainer />
      </MemoryRouter>
    </MockedProvider>
  );
};
