/**
 * Regression tests for DocumentAnnotationIndex deep-linking behavior.
 *
 * Bug context:
 *   The corpus home page renders a Table of Contents whose leaves are
 *   structural annotations (e.g. "Subchapter I. Formation, p. 2"). Clicking
 *   one is supposed to deep-link into the corresponding document with the
 *   annotation pre-selected.
 *
 *   The component originally overloaded a single `embedded` prop for two
 *   meanings: "render without an outer container" AND "we are already on
 *   the document page". The corpus-home call site needed the visual flavor
 *   but absolutely was NOT on a document page. The click handler took the
 *   wrong branch and rewrote `?ann=<id>` onto the corpus URL, so nothing
 *   happened. These tests pin the new contract: visual layout (`embedded`)
 *   and click routing (`onDocumentPage`) are independent.
 */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { MockedProvider } from "@apollo/client/testing";
import { describe, it, expect, vi, beforeEach } from "vitest";

import { DocumentAnnotationIndex } from "../DocumentAnnotationIndex";
import {
  GET_DOCUMENT_ANNOTATION_INDEX,
  GetDocumentAnnotationIndexInput,
} from "../../../graphql/queries";
import {
  DOCUMENT_ANNOTATION_INDEX_LIMIT,
  OC_SECTION_LABEL,
} from "../../../assets/configurations/constants";
import { openedCorpus } from "../../../graphql/cache";

// Mock react-router-dom's useNavigate so we can assert on navigation intent.
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom"
  );
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const DOC_ID = "doc-1";
const DOC_SLUG = "test-document";
const CORPUS_ID = "corpus-1";
const SECTION_ID = "ann-section-1";
const SECTION_TITLE = "Subchapter I. Formation";

const corpusForVar = {
  id: CORPUS_ID,
  slug: "test-corpus",
  creator: { id: "u1", slug: "test-user" },
} as Parameters<typeof openedCorpus>[0];

const variables: GetDocumentAnnotationIndexInput = {
  documentId: DOC_ID,
  corpusId: CORPUS_ID,
  labelText: OC_SECTION_LABEL,
  first: DOCUMENT_ANNOTATION_INDEX_LIMIT,
};

const indexMock = {
  request: { query: GET_DOCUMENT_ANNOTATION_INDEX, variables },
  result: {
    data: {
      annotations: {
        totalCount: 1,
        edges: [
          {
            node: {
              id: SECTION_ID,
              rawText: SECTION_TITLE,
              longDescription: null,
              page: 2,
              parent: null,
            },
          },
        ],
      },
    },
  },
};

const renderIndex = (props: {
  onDocumentPage?: boolean;
  initialEntry: string;
}) => {
  return render(
    <MockedProvider mocks={[indexMock]} addTypename={false}>
      <MemoryRouter initialEntries={[props.initialEntry]}>
        <DocumentAnnotationIndex
          documentId={DOC_ID}
          documentSlug={DOC_SLUG}
          corpusId={CORPUS_ID}
          embedded
          onDocumentPage={props.onDocumentPage}
        />
      </MemoryRouter>
    </MockedProvider>
  );
};

describe("DocumentAnnotationIndex — section click deep-link routing", () => {
  beforeEach(() => {
    mockNavigate.mockReset();
    openedCorpus(corpusForVar);
  });

  it("navigates to the document URL with ?ann=<id> when clicked from the corpus home (default)", async () => {
    renderIndex({ initialEntry: "/c/test-user/test-corpus" });

    // Wait for the section to render (data resolved)
    const item = await screen.findByRole("treeitem", {
      name: new RegExp(SECTION_TITLE, "i"),
    });

    await userEvent.click(item);

    // Should have triggered a full navigation to the document page.
    // navigate(targetPath) is called with a string starting with /d/...
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledTimes(1);
    });

    const navArg = mockNavigate.mock.calls[0][0];
    expect(typeof navArg).toBe("string");
    expect(navArg).toMatch(/^\/d\/test-user\/test-corpus\/test-document/);
    expect(navArg).toContain(`ann=${SECTION_ID}`);
  });

  it("only updates ?ann= on the current URL when onDocumentPage is true", async () => {
    renderIndex({
      onDocumentPage: true,
      initialEntry: "/d/test-user/test-corpus/test-document",
    });

    const item = await screen.findByRole("treeitem", {
      name: new RegExp(SECTION_TITLE, "i"),
    });

    await userEvent.click(item);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledTimes(1);
    });

    // Search-only navigation: navigate({ search: "..." }, { replace: true })
    const [navArg, navOpts] = mockNavigate.mock.calls[0];
    expect(navArg).toEqual({
      search: expect.stringContaining(`ann=${SECTION_ID}`),
    });
    expect(navOpts).toEqual({ replace: true });
  });

  it("does NOT update ?ann= on the current URL when on the corpus home (regression: embedded must not imply onDocumentPage)", async () => {
    renderIndex({
      // embedded=true is set by renderIndex, but onDocumentPage is unset
      initialEntry: "/c/test-user/test-corpus",
    });

    const item = await screen.findByRole("treeitem", {
      name: new RegExp(SECTION_TITLE, "i"),
    });

    await userEvent.click(item);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledTimes(1);
    });

    // The single navigate call must be a full URL string (not a {search}
    // object), proving we did NOT take the "already on the document page"
    // branch that originally swallowed the deep link.
    const navArg = mockNavigate.mock.calls[0][0];
    expect(typeof navArg).toBe("string");
    expect(navArg).not.toMatch(/^\/c\//); // must leave the corpus URL
    expect(navArg).toMatch(/^\/d\//);
  });
});
