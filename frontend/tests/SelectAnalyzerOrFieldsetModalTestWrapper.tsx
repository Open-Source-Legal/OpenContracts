/**
 * Wrapper for `SelectAnalyzerOrFieldsetModal` Playwright CT tests.
 *
 * Provides a MockedProvider loaded with analyzer and fieldset query mocks.
 * Keeps helper builders out of this file because Playwright CT's babel plugin
 * only wants component exports here — shared mock builders live in
 * `SelectAnalyzerOrFieldsetModalMocks.ts`.
 */
import React, { useState } from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { SelectAnalyzerOrFieldsetModal } from "../src/components/widgets/modals/SelectCorpusAnalyzerOrFieldsetAnalyzer";
import type { CorpusType, DocumentType } from "../src/types/graphql-api";

interface WrapperProps {
  corpus?: CorpusType;
  document?: DocumentType;
  mocks: MockedResponse[];
  startOpen?: boolean;
}

export const SelectAnalyzerOrFieldsetModalTestWrapper: React.FC<
  WrapperProps
> = ({ corpus, document, mocks, startOpen = true }) => {
  const [open, setOpen] = useState(startOpen);

  return (
    <MockedProvider mocks={mocks} addTypename={false}>
      <div style={{ padding: 24 }}>
        <SelectAnalyzerOrFieldsetModal
          corpus={corpus}
          document={document}
          open={open}
          onClose={() => setOpen(false)}
        />
      </div>
    </MockedProvider>
  );
};
