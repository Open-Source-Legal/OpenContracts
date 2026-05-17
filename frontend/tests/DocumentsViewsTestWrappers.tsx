// Thin harnesses around the three view components extracted in PR #1677.
// Each harness owns the prop-derived state (selectedIds /
// activeContextMenuDocId / a handful of "last call" flags) so the test
// can assert on visible text rather than spying on functions through the
// playwright bridge.
import React, { useState } from "react";
import { DocumentType } from "../src/types/graphql-api";
import { DocumentsGridView } from "../src/views/DocumentsGridView";
import { DocumentsListView } from "../src/views/DocumentsListView";
import { DocumentsCompactView } from "../src/views/DocumentsCompactView";

// Document with no title, no icon, no page count — exercises every
// fallback branch (``Untitled``, placeholder card preview, ``Document``
// meta label) and the processing overlay/chip branches.
const docMinimal: DocumentType = {
  id: "doc-1",
  slug: "doc-1",
  title: "",
  fileType: "pdf",
  backendLock: true,
  pageCount: 0,
  icon: null,
  created: "2026-05-01T12:00:00Z",
  creator: {
    id: "u-1",
    slug: "u-1",
    email: "creator@example.com",
  },
} as any;

// Document with icon, page count, no backendLock — exercises the
// non-fallback branches in the same components.
const docRich: DocumentType = {
  id: "doc-2",
  slug: "doc-2",
  title: "Rich Document",
  fileType: "docx",
  backendLock: false,
  pageCount: 12,
  icon: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
  created: "2026-05-02T12:00:00Z",
  creator: {
    id: "u-2",
    slug: "u-2",
    email: "second@example.com",
  },
} as any;

// Image alt text is the title — replace docRich with a stable label so
// the test can locate it via ``img[alt="With icon"]`` (the alt for
// docMinimal would otherwise collide with the ``Untitled`` text node).
const docRichWithKnownAlt: DocumentType = {
  ...docRich,
  title: "With icon",
} as any;

const docs: DocumentType[] = [docMinimal, docRichWithKnownAlt];

// Banner shown via state changes — lets the test ``expect text=...``
// instead of bridging callback values back to the test process.
const Banner: React.FC<{ value: string | null }> = ({ value }) =>
  value === null ? null : <div data-testid="banner">{value}</div>;

export const DocumentsGridViewHarness: React.FC = () => {
  const [clicked, setClicked] = useState<string | null>(null);
  const [context, setContext] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <div>
      <DocumentsGridView
        documents={docs}
        selectedIds={[]}
        activeContextMenuDocId={undefined}
        onDocumentClick={(d) => setClicked(`clicked-${d.id}`)}
        onSelect={(id) => setSelected(`selected-${id}`)}
        onContextMenu={(_, d) => setContext(`context-${d.id}`)}
      />
      <Banner value={clicked} />
      <Banner value={context} />
      <Banner value={selected} />
    </div>
  );
};

export const DocumentsListViewHarness: React.FC = () => {
  const [clicked, setClicked] = useState<string | null>(null);
  const [context, setContext] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [allSelected, setAllSelected] = useState<string | null>(null);

  return (
    <div>
      <DocumentsListView
        documents={docs}
        selectedIds={[]}
        activeContextMenuDocId={undefined}
        allSelected={false}
        onDocumentClick={(d) => setClicked(`clicked-${d.id}`)}
        onSelect={(id) => setSelected(`selected-${id}`)}
        onSelectAll={() => setAllSelected("select-all-fired")}
        onContextMenu={(_, d) => setContext(`context-${d.id}`)}
      />
      <Banner value={clicked} />
      <Banner value={context} />
      <Banner value={selected} />
      <Banner value={allSelected} />
    </div>
  );
};

export const DocumentsCompactViewHarness: React.FC = () => {
  const [clicked, setClicked] = useState<string | null>(null);
  const [context, setContext] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <div>
      <DocumentsCompactView
        documents={docs}
        selectedIds={[]}
        activeContextMenuDocId={undefined}
        onDocumentClick={(d) => setClicked(`clicked-${d.id}`)}
        onSelect={(id) => setSelected(`selected-${id}`)}
        onContextMenu={(_, d) => setContext(`context-${d.id}`)}
      />
      <Banner value={clicked} />
      <Banner value={context} />
      <Banner value={selected} />
    </div>
  );
};
