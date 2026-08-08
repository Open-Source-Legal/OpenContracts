import React from "react";
import { MemoryRouter } from "react-router-dom";
import { MockedProvider } from "@apollo/client/testing";
import { Provider as JotaiProvider, createStore } from "jotai";

import { MarkdownDocumentViewer } from "../src/components/knowledge_base/document/document_kb/MarkdownDocumentViewer";
import { docTextAtom } from "../src/components/annotator/context/DocumentAtom";

interface MarkdownDocumentViewerTestWrapperProps {
  /** Document body seeded into ``docTextAtom`` — the same atom the real
   *  viewer reads, so the test exercises the production data path. */
  docText: string;
  canEdit?: boolean;
}

/**
 * Wrapper for ``MarkdownDocumentViewer``.
 *
 * Only the rendered branch is mounted here. Switching to Raw mounts
 * ``TxtAnnotatorWrapper``, which needs the full annotator context (corpus
 * state, selection atoms, label sets); that path is covered by the
 * TxtAnnotator suite and verified end-to-end in the live walkthrough, so
 * reproducing its scaffolding here would test the harness rather than this
 * component.
 */
export const MarkdownDocumentViewerTestWrapper: React.FC<
  MarkdownDocumentViewerTestWrapperProps
> = ({ docText, canEdit = false }) => {
  const store = createStore();
  store.set(docTextAtom, docText);

  return (
    <MemoryRouter initialEntries={["/"]}>
      <MockedProvider mocks={[]} addTypename={false}>
        <JotaiProvider store={store}>
          <div
            style={{ width: "100%", height: "520px", background: "#fff" }}
            data-testid="markdown-viewer-host"
          >
            <MarkdownDocumentViewer canEdit={canEdit} />
          </div>
        </JotaiProvider>
      </MockedProvider>
    </MemoryRouter>
  );
};
