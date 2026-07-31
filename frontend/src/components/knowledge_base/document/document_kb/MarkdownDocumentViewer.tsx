/**
 * Markdown document body, with a Rendered / Raw toggle.
 *
 * Markdown documents are `text/…`, so they used to fall into the plain-text
 * branch and display their own source — `# Heading`, `- **Corpus:**` — which is
 * exactly wrong for the things that produce them: saved chat answers, research
 * reports and CAML articles are written to be *read*.
 *
 * The toggle is not cosmetic. "Raw" is the annotator: span annotations need
 * character offsets into the source text, so annotating has to happen against
 * the raw document, not a rendered tree. Rendered is the default because
 * reading is the common case; annotating is a deliberate act and one click
 * away.
 *
 * The renderer is the same `MarkdownMessageRenderer` the chat uses, so a saved
 * answer looks in the document viewer the way it looked in the conversation it
 * came from.
 */
import React, { useState } from "react";
import styled from "styled-components";
import { Code2, Eye } from "lucide-react";

import { MarkdownMessageRenderer } from "../../../threads/MarkdownMessageRenderer";
import TxtAnnotatorWrapper from "../../../annotator/components/wrappers/TxtAnnotatorWrapper";
import { useDocText } from "../../../annotator/context/DocumentAtom";
import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";

export type MarkdownViewMode = "rendered" | "raw";

const Layout = styled.div`
  position: relative;
  height: 100%;
  width: 100%;
  overflow: auto;
`;

// Left-aligned deliberately: the viewer's zoom control is pinned to the top
// RIGHT of this same container, and an earlier revision put the toggle there
// too — where it sat underneath the zoom pill and was invisible in rendered
// mode. A control the user cannot find is the same as not shipping it.
const ToggleBar = styled.div`
  position: sticky;
  top: 0;
  z-index: 5;
  display: flex;
  justify-content: flex-start;
  padding: 0.5rem 0.75rem 0;
  pointer-events: none;
`;

const ToggleGroup = styled.div`
  display: inline-flex;
  pointer-events: auto;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.45);
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(4px);
  overflow: hidden;
`;

const ToggleButton = styled.button<{ $active: boolean }>`
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.3rem 0.65rem;
  border: none;
  cursor: pointer;
  font-size: 0.74rem;
  font-weight: 600;
  color: ${(props) =>
    props.$active ? "#ffffff" : OS_LEGAL_COLORS.textSecondary};
  background: ${(props) => (props.$active ? "#0f766e" : "transparent")};

  &:hover:not(:disabled) {
    background: ${(props) =>
      props.$active ? "#0f766e" : "rgba(148, 163, 184, 0.16)"};
  }
`;

const RenderedSurface = styled.div`
  padding: 1.25rem 2rem 3rem;
  max-width: 900px;
  margin: 0 auto;
  font-size: 0.95rem;
  line-height: 1.6;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const EmptyNote = styled.p`
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-style: italic;
`;

export interface MarkdownDocumentViewerProps {
  /** Whether the viewer may create/edit annotations (raw mode only). */
  canEdit: boolean;
  /** Initial mode; defaults to rendered because reading is the common case. */
  initialMode?: MarkdownViewMode;
}

export const MarkdownDocumentViewer: React.FC<MarkdownDocumentViewerProps> = ({
  canEdit,
  initialMode = "rendered",
}) => {
  const [mode, setMode] = useState<MarkdownViewMode>(initialMode);
  const { docText } = useDocText();

  return (
    <Layout data-testid="markdown-document-viewer">
      <ToggleBar>
        <ToggleGroup role="group" aria-label="Markdown view mode">
          <ToggleButton
            type="button"
            $active={mode === "rendered"}
            aria-pressed={mode === "rendered"}
            onClick={() => setMode("rendered")}
            data-testid="markdown-view-rendered"
            title="Show the formatted document"
          >
            <Eye size={13} />
            Rendered
          </ToggleButton>
          <ToggleButton
            type="button"
            $active={mode === "raw"}
            aria-pressed={mode === "raw"}
            onClick={() => setMode("raw")}
            data-testid="markdown-view-raw"
            // Annotating needs character offsets into the source, so it only
            // works here — say so rather than leaving the mode unexplained.
            title={
              canEdit
                ? "Show the Markdown source (annotations are made here)"
                : "Show the Markdown source"
            }
          >
            <Code2 size={13} />
            Raw
          </ToggleButton>
        </ToggleGroup>
      </ToggleBar>

      {mode === "rendered" ? (
        <RenderedSurface data-testid="markdown-rendered-surface">
          {docText ? (
            <MarkdownMessageRenderer content={docText} />
          ) : (
            <EmptyNote>This document has no text content.</EmptyNote>
          )}
        </RenderedSurface>
      ) : (
        <TxtAnnotatorWrapper readOnly={!canEdit} allowInput={canEdit} />
      )}
    </Layout>
  );
};

export default MarkdownDocumentViewer;
