import React from "react";
import { InMemoryCache } from "@apollo/client";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { ToastContainer } from "react-toastify";
import { PacksTab } from "../src/components/admin/authority/PacksTab";
import { AuthorityPackCorpus } from "../src/graphql/queries";

interface WrapperProps {
  mocks?: MockedResponse[];
  /**
   * Left undefined (the default) to exercise the "no corpus-ZIP-importer
   * bridge" configuration. AuthorityConsole always supplies this callback, so
   * that unbridged branch can only be reached by mounting PacksTab directly,
   * without the console shell.
   */
  onImportCorpus?: (corpusId: string, corpus: AuthorityPackCorpus) => void;
}

/**
 * Minimal test wrapper that mounts the Authority Packs tab directly, without
 * the surrounding AuthorityConsole shell (no router, no other tabs' GraphQL
 * queries). Neither PacksTab nor PackPreflightModal read routing state or the
 * ``backendUserObj`` reactive var, so only Apollo + toast context are needed.
 */
export const PacksTabTestWrapper: React.FC<WrapperProps> = ({
  mocks = [],
  onImportCorpus,
}) => (
  <MockedProvider
    mocks={mocks}
    addTypename={false}
    cache={new InMemoryCache({ addTypename: false })}
  >
    {/*
      MockedProvider only renders its `children` prop correctly when it is a
      single element; passing PacksTab and ToastContainer as two siblings
      renders nothing at all (no error, no console output). Wrap them in one
      element.
    */}
    <div>
      <PacksTab onImportCorpus={onImportCorpus} />
      <ToastContainer />
    </div>
  </MockedProvider>
);
