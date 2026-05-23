// tests/MobileDocumentKnowledgeBase.harness.tsx
//
// Harness for the mobile-layout integration tests. Mounts the *real*
// DocumentKnowledgeBase through the shared DocumentKnowledgeBaseTestWrapper so
// that — at a sub-768px viewport — it renders MobileDocumentLayout end-to-end.
//
// This file is bundled into the browser by Playwright CT, so it must NOT
// import the GraphQL mock fixtures directly: tests/mocks/DocumentKnowledgeBase
// .mocks.ts uses Node's `path`/`__dirname` (to resolve the test PDF/PAWLs from
// disk) and bundling that into the browser throws `__dirname is not defined`.
// The mocks are therefore built on the Node side in
// MobileDocumentKnowledgeBase.ct.tsx and threaded in as serialised props.
//
// CRITICAL — Playwright CT split-import rule (CLAUDE.md pitfall #16):
// the JSX-component import (DocumentKnowledgeBaseTestWrapper) MUST stay in its
// own import statement, separate from the helper/value imports below it.

import { DocumentKnowledgeBaseTestWrapper } from "./DocumentKnowledgeBaseTestWrapper";

import React from "react";
import type { MockedResponse } from "@apollo/client/testing";

export interface MobileDKBProps {
  /** GraphQL mock set, assembled Node-side (see the .ct.tsx file). */
  mocks: ReadonlyArray<MockedResponse>;
  documentId: string;
  corpusId: string;
}

/**
 * Mounts the real DocumentKnowledgeBase for a processed PDF document. At the
 * 390px viewport the integration tests run under, DocumentKnowledgeBase renders
 * MobileDocumentLayout (its `isMobile = width < 768` switch).
 */
export const MobileDKB: React.FC<MobileDKBProps> = ({
  mocks,
  documentId,
  corpusId,
}) => (
  <DocumentKnowledgeBaseTestWrapper
    mocks={mocks}
    documentId={documentId}
    corpusId={corpusId}
  />
);

export default MobileDKB;
