import React from "react";
import { MockedProvider } from "@apollo/client/testing";
import { Provider as JotaiProvider, createStore } from "jotai";
import { showBulkImportModal } from "../../src/graphql/cache";
import { folderCorpusIdAtom } from "../../src/atoms/folderAtoms";

/**
 * Test wrapper for BulkImportModal that provides:
 * - JotaiProvider with folderCorpusIdAtom set
 * - MockedProvider for GraphQL
 * - Sets showBulkImportModal reactive var to true on mount
 */
export const BulkImportTestWrapper: React.FC<{
  children: React.ReactNode;
}> = ({ children }) => {
  React.useEffect(() => {
    showBulkImportModal(true);
    return () => {
      showBulkImportModal(false);
    };
  }, []);

  const store = React.useMemo(() => {
    const s = createStore();
    s.set(folderCorpusIdAtom, "test-corpus-id");
    return s;
  }, []);

  return (
    <JotaiProvider store={store}>
      <MockedProvider mocks={[]} addTypename={false}>
        {children}
      </MockedProvider>
    </JotaiProvider>
  );
};
