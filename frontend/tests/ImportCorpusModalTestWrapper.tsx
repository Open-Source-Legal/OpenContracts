import React, { useEffect } from "react";
import { MockedProvider } from "@apollo/client/testing";
import { ImportCorpusModal } from "../src/components/widgets/modals/ImportCorpusModal";
import { showImportCorpusModal } from "../src/graphql/cache";

/**
 * Playwright CT mounts components in the browser, so `test.beforeEach`
 * callbacks (which run in node) cannot reach the makeVar instance the
 * component reads. Seeding the reactive var synchronously in render gives
 * the modal the exact state production would set via the trigger button.
 */
export const ImportCorpusModalVisibleWrapper: React.FC = () => {
  showImportCorpusModal(true);
  useEffect(() => () => showImportCorpusModal(false), []);
  return (
    <MockedProvider mocks={[]} addTypename={false}>
      <ImportCorpusModal />
    </MockedProvider>
  );
};

export const ImportCorpusModalHiddenWrapper: React.FC = () => {
  showImportCorpusModal(false);
  return (
    <MockedProvider mocks={[]} addTypename={false}>
      <ImportCorpusModal />
    </MockedProvider>
  );
};
