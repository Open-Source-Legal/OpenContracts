/**
 * CamlArticleEditor — Full-screen modal editor for Readme.CAML articles.
 *
 * Supports both creating new articles and editing existing ones.
 * Uses the UploadDocument mutation to create/version the Readme.CAML document.
 * Preview pane renders the parsed CAML via CamlArticle renderer.
 */
import React, {
  useState,
  useEffect,
  useCallback,
  useMemo,
  useRef,
} from "react";
import { useQuery, useMutation } from "@apollo/client";
import { toast } from "react-toastify";
import { BookOpen, Check, Eye, Edit, Save, Table2 } from "lucide-react";
import styled from "styled-components";

import { Modal } from "@os-legal/ui";
import { ConfirmModal } from "../widgets/modals/ConfirmModal";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { CAML_ARTICLE_FILENAME } from "../../assets/configurations/constants";
import {
  GET_CORPUS_ARTICLE,
  GetCorpusArticleInput,
  GetCorpusArticleOutput,
  GET_EXTRACTS,
  GetExtractsOutput,
} from "../../graphql/queries";
import {
  UPLOAD_DOCUMENT,
  UploadDocumentInputProps,
  UploadDocumentOutputProps,
} from "../../graphql/mutations";
import { parseCaml } from "@os-legal/caml";
import { CamlArticle, CamlThemeProvider } from "@os-legal/caml-react";
import { useCamlComponentRenderer } from "../../hooks/useCamlComponentRenderer";
import { buildComponentProseFence } from "../../utils/camlComponents";
import { CAML_COMPONENTS } from "../../utils/camlComponentRegistry";

// ---------------------------------------------------------------------------
// Styled components
// ---------------------------------------------------------------------------

const StyledModalWrapper = styled.div`
  .modal-overlay {
    z-index: 1000;
  }

  [class*="modal-content"],
  [class*="ModalContent"],
  [role="dialog"] > div {
    width: 95vw !important;
    max-width: 1400px !important;
    height: 90vh !important;
    max-height: 90vh !important;
    border-radius: 16px !important;
    overflow: hidden !important;
  }

  @media (max-width: 768px) {
    [class*="modal-content"],
    [class*="ModalContent"],
    [role="dialog"] > div {
      width: 100vw !important;
      height: 100vh !important;
      max-height: 100vh !important;
      border-radius: 0 !important;
    }
  }
`;

const ModalHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  background: ${OS_LEGAL_COLORS.background};

  h2 {
    font-size: 1rem;
    font-weight: 600;
    color: ${OS_LEGAL_COLORS.textPrimary};
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 0;
    flex: 1;
  }
`;

const ContentWrapper = styled.div`
  display: flex;
  height: calc(90vh - 60px - 64px);
  overflow: hidden;

  @media (max-width: 768px) {
    flex-direction: column;
    height: calc(100vh - 60px - 64px);
  }
`;

const EditorPane = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  border-right: 1px solid ${OS_LEGAL_COLORS.border};
`;

const PaneHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  font-size: 0.75rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textSecondary};
  text-transform: uppercase;
  letter-spacing: 0.05em;
`;

const EditorTextarea = styled.textarea`
  flex: 1;
  width: 100%;
  padding: 1rem;
  border: none;
  resize: none;
  font-family: "SF Mono", Monaco, "Cascadia Code", monospace;
  font-size: 0.875rem;
  line-height: 1.6;
  color: ${OS_LEGAL_COLORS.textPrimary};
  background: ${OS_LEGAL_COLORS.surface};
  outline: none;

  &::placeholder {
    color: ${OS_LEGAL_COLORS.textMuted};
  }
`;

const PreviewPane = styled.div`
  flex: 1;
  overflow-y: auto;
  background: ${OS_LEGAL_COLORS.surface};
  min-width: 0;
`;

const ActionBar = styled.div`
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 0.75rem 1.5rem;
  border-top: 1px solid ${OS_LEGAL_COLORS.border};
  background: ${OS_LEGAL_COLORS.background};
`;

const ActionButton = styled.button<{ $primary?: boolean }>`
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 1rem;
  border-radius: 8px;
  font-size: 0.8125rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  border: 1px solid
    ${({ $primary }) =>
      $primary ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.border};
  background: ${({ $primary }) =>
    $primary ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.surface};
  color: ${({ $primary }) =>
    $primary ? OS_LEGAL_COLORS.surface : OS_LEGAL_COLORS.textPrimary};

  &:hover {
    background: ${({ $primary }) =>
      $primary ? OS_LEGAL_COLORS.accentHover : OS_LEGAL_COLORS.surfaceHover};
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
`;

const UnsavedBadge = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.5rem;
  border-radius: 9999px;
  font-size: 0.6875rem;
  font-weight: 600;
  background: ${OS_LEGAL_COLORS.warningSurface};
  color: ${OS_LEGAL_COLORS.warningText};
`;

const EditorToolbar = styled.div`
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.5rem;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  background: ${OS_LEGAL_COLORS.surface};
`;

const ToolbarBtn = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.5rem;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 0.75rem;
  cursor: pointer;
  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    color: ${OS_LEGAL_COLORS.textPrimary};
  }
`;

const ExtractPickerDropdown = styled.div`
  position: absolute;
  top: 100%;
  left: 0;
  z-index: 20;
  min-width: 280px;
  max-height: 240px;
  overflow-y: auto;
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
`;

const ExtractPickerItem = styled.button<{ $active?: boolean }>`
  display: block;
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: none;
  /* Keyboard-active ($active) and mouse-hover share the same visual highlight. */
  background: ${(p) =>
    p.$active ? OS_LEGAL_COLORS.surfaceLight : "transparent"};
  text-align: left;
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  cursor: pointer;
  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
  }
  &:focus-visible {
    outline: 2px solid ${OS_LEGAL_COLORS.accent};
    outline-offset: -2px;
  }
`;

const ExtractPickerEmpty = styled.div`
  padding: 0.75rem;
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  text-align: center;
`;

const CAML_TEMPLATE = `---
version: "1.0"

hero:
  kicker: "Your organization · Interactive analysis"
  title:
    - "Your article"
    - "{title here}"
  subtitle: >
    Write a compelling subtitle that describes what this
    article is about and why readers should care.
  stats:
    - "Documents analyzed"
    - "Key findings"
---

::: chapter {#introduction}
>! Chapter 1
## Getting started

Write your article content here using CAML syntax.
You can use **bold**, *italic*, and [links](https://example.com).

>>> "Use triple blockquotes for pullquotes that stand out."

:::: cards {columns: 2}

- **Key Finding 1** | #0f766e
  Describe the first key finding here.
  ~ Source: Document A

- **Key Finding 2** | #c4573a
  Describe the second key finding here.
  ~ Source: Document B

::::

:::

::: chapter {#case-tracker}
>! Chapter 2
## Case History

:::: case-history
title: Example Case v. Sample Corp
docket: No. 24-cv-01234 (S.D.N.Y.)
status: Pending

- District Court | S.D.N.Y. | 2024-03-15 | Motion to Dismiss | Denied
  Court found sufficient facts to proceed.

- Court of Appeals | 2nd Circuit | 2025-01-20 | Appeal | Pending
  Oral arguments scheduled.

::::

:::

::: chapter {#jurisdiction}
>! Chapter 3
## Jurisdiction Map

:::: map {type: us}
legend:
- Compliant | #0f766e
- Pending | #f59e0b
- Non-compliant | #dc2626

- CA | Compliant
- NY | Compliant
- TX | Pending
- FL | Non-compliant
- IL | Compliant

::::

:::
`;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface CamlArticleEditorProps {
  corpusId: string;
  isOpen: boolean;
  onClose: () => void;
  onUpdate?: () => void;
}

export const CamlArticleEditor: React.FC<CamlArticleEditorProps> = ({
  corpusId,
  isOpen,
  onClose,
  onUpdate,
}) => {
  const [content, setContent] = useState("");
  const [currentContent, setCurrentContent] = useState("");
  const [hasChanges, setHasChanges] = useState(false);
  const [isNew, setIsNew] = useState(false);
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);
  const [showExtractPicker, setShowExtractPicker] = useState(false);
  // Index of the keyboard-focused option within the extract picker dropdown.
  // `-1` means no option is focused (initial state when the dropdown opens).
  const [activeExtractIndex, setActiveExtractIndex] = useState<number>(-1);
  // Mirror of `activeExtractIndex` in a ref so that the keyboard handler can
  // read the latest value when consecutive keystrokes (e.g. ArrowDown then
  // Enter) arrive faster than React schedules a re-render. Without this, the
  // Enter handler would observe a stale closure value of `-1` and bail out.
  const activeExtractIndexRef = useRef<number>(-1);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const extractPickerRef = useRef<HTMLDivElement>(null);
  const extractPickerTriggerRef = useRef<HTMLButtonElement>(null);

  // Query for existing Readme.CAML
  const articleVars = useMemo<GetCorpusArticleInput>(
    () => ({ corpusId, title: CAML_ARTICLE_FILENAME }),
    [corpusId]
  );

  const { data, refetch } = useQuery<
    GetCorpusArticleOutput,
    GetCorpusArticleInput
  >(GET_CORPUS_ARTICLE, {
    variables: articleVars,
    skip: !isOpen,
  });

  const [uploadDocument, { loading: saving }] = useMutation<
    UploadDocumentOutputProps,
    UploadDocumentInputProps
  >(UPLOAD_DOCUMENT, {
    refetchQueries: [
      {
        query: GET_CORPUS_ARTICLE,
        variables: { corpusId, title: CAML_ARTICLE_FILENAME },
      },
    ],
  });

  const articleDoc = data?.documents?.edges?.[0]?.node;

  // Load content from existing document or start with template
  useEffect(() => {
    if (!isOpen) return;

    if (articleDoc?.txtExtractFile) {
      setIsNew(false);
      fetch(articleDoc.txtExtractFile)
        .then((res) => res.text())
        .then((text) => {
          setContent(text);
          setCurrentContent(text);
          setHasChanges(false);
        })
        .catch((err) => {
          console.error("Failed to fetch article content:", err);
          setContent(CAML_TEMPLATE);
          setCurrentContent(CAML_TEMPLATE);
        });
    } else if (data && !articleDoc) {
      // No existing article — start fresh
      setIsNew(true);
      setContent(CAML_TEMPLATE);
      setCurrentContent(CAML_TEMPLATE);
      setHasChanges(false);
    }
  }, [articleDoc, data, isOpen]);

  // Track changes
  useEffect(() => {
    setHasChanges(content !== currentContent);
  }, [content, currentContent]);

  // Parse content for preview
  const parsedDocument = useMemo(() => {
    try {
      return parseCaml(content);
    } catch {
      return null;
    }
  }, [content]);

  const handleSave = useCallback(async () => {
    if (!hasChanges && !isNew) return;

    try {
      // Encode content as base64 for the upload mutation
      const bytes = new TextEncoder().encode(content);
      const base64Content = btoa(
        Array.from(bytes, (b) => String.fromCharCode(b)).join("")
      );

      const result = await uploadDocument({
        variables: {
          base64FileString: base64Content,
          filename: CAML_ARTICLE_FILENAME,
          title: CAML_ARTICLE_FILENAME,
          description: "Corpus article (CAML format)",
          customMeta: {},
          makePublic: false,
          addToCorpusId: corpusId,
        },
      });

      if (result.data?.uploadDocument.ok) {
        toast.success(isNew ? "Article created!" : "Article updated!", {
          icon: <Check size={20} />,
        });
        setCurrentContent(content);
        setHasChanges(false);
        setIsNew(false);
        await refetch();
        onUpdate?.();
      } else {
        toast.error(
          result.data?.uploadDocument.message || "Failed to save article"
        );
      }
    } catch (error) {
      console.error("Error saving article:", error);
      toast.error("Failed to save article");
    }
  }, [content, hasChanges, isNew, corpusId, uploadDocument, refetch, onUpdate]);

  // Query for corpus extracts (for the insert toolbar).
  // corpusAction_Isnull: true excludes action-triggered extracts (i.e. extracts
  // created automatically by a pipeline step / corpus action). Those are internal
  // implementation details and should not appear in the user-facing embed picker.
  const { data: extractsData, loading: extractsLoading } =
    useQuery<GetExtractsOutput>(GET_EXTRACTS, {
      variables: { corpusId, corpusAction_Isnull: true },
      skip: !isOpen,
    });

  const corpusExtracts = useMemo(() => {
    const edges = extractsData?.extracts?.edges ?? [];
    return (
      edges
        .map((e) => e?.node)
        .filter((e): e is NonNullable<typeof e> => Boolean(e))
        // Only show extracts that have either completed processing or have
        // associated documents. This hides newly-created extracts that haven't
        // started yet and would produce empty grid embeds.
        // NOTE: Relies on `finished` and `fullDocumentList` being present in the
        // GET_EXTRACTS query response. If those fields are ever removed from
        // the query, this filter silently degrades to `e.finished` only.
        .filter((e) => {
          if (
            process.env.NODE_ENV === "development" &&
            e.finished === undefined &&
            e.fullDocumentList === undefined
          ) {
            console.warn(
              "[CamlArticleEditor] GET_EXTRACTS missing finished/fullDocumentList — extract picker filter degraded"
            );
          }
          return e.finished || (e.fullDocumentList?.length ?? 0) > 0;
        })
    );
  }, [extractsData]);

  // Close extract picker when clicking outside.
  // The listener is added/removed synchronously when `showExtractPicker`
  // toggles — no setTimeout needed because the open button stops propagation.
  useEffect(() => {
    if (!showExtractPicker) return;

    const handleClickOutside = (event: MouseEvent) => {
      if (
        extractPickerRef.current &&
        !extractPickerRef.current.contains(event.target as Node)
      ) {
        setShowExtractPicker(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showExtractPicker]);

  // Reset the keyboard-focused option whenever the picker closes so the next
  // open starts in a clean state. The ref mirror is reset alongside state so
  // the next ArrowDown reads the fresh `-1` value synchronously.
  useEffect(() => {
    if (!showExtractPicker) {
      activeExtractIndexRef.current = -1;
      setActiveExtractIndex(-1);
    }
  }, [showExtractPicker]);

  /** Insert a component marker as a prose block at the cursor. */
  const handleInsertComponent = useCallback(
    (type: string, props: Record<string, string>) => {
      setShowExtractPicker(false);
      const fence = buildComponentProseFence(type, props);
      const textarea = textareaRef.current;
      const cursorPos = textarea?.selectionStart ?? -1;

      setContent((prev) => {
        const pos = cursorPos >= 0 ? cursorPos : prev.length;
        return prev.slice(0, pos) + fence + prev.slice(pos);
      });
      setHasChanges(true);

      // Restore cursor position after React re-renders the textarea
      requestAnimationFrame(() => {
        if (textarea) {
          const pos =
            cursorPos >= 0 ? cursorPos + fence.length : textarea.value.length;
          textarea.selectionStart = pos;
          textarea.selectionEnd = pos;
          textarea.focus();
        }
      });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- setContent and
    // setHasChanges (from useState) are guaranteed stable; textareaRef.current
    // is read at call-time through the ref object, not captured at creation time.
    []
  );

  /**
   * Keyboard handler for the extract picker (listbox pattern).
   *
   * - ArrowDown / ArrowUp move the focused option (wrapping at the ends).
   * - Home / End jump to first / last option.
   * - Enter selects the focused option (inserts the extract grid marker).
   * - Escape closes the dropdown and returns focus to the trigger button.
   *
   * Attached to the trigger button (role="combobox") so
   * `aria-activedescendant` and the keyboard handler share the same DOM
   * focus context — required by WAI-ARIA for virtual-focus patterns.
   */
  const handleExtractPickerKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLButtonElement>) => {
      if (!showExtractPicker) return;
      const count = corpusExtracts.length;

      // Helper: update both state (drives render) and ref (drives next
      // synchronous keystroke). The ref read in the Enter case below would
      // otherwise observe a stale `-1` if Enter arrives in the same tick as
      // a preceding ArrowDown.
      const updateActiveIndex = (next: number) => {
        activeExtractIndexRef.current = next;
        setActiveExtractIndex(next);
      };

      switch (event.key) {
        case "Escape":
          event.preventDefault();
          setShowExtractPicker(false);
          extractPickerTriggerRef.current?.focus();
          break;
        case "ArrowDown": {
          if (count === 0) return;
          event.preventDefault();
          const prev = activeExtractIndexRef.current;
          updateActiveIndex(prev + 1 >= count ? 0 : prev + 1);
          break;
        }
        case "ArrowUp": {
          if (count === 0) return;
          event.preventDefault();
          // `prev <= 0` covers both `0` (first item → wrap to last) and `-1`
          // (no item focused → jump to last). This is intentional per WAI-ARIA
          // Authoring Practices for listbox keyboard interaction.
          const prev = activeExtractIndexRef.current;
          updateActiveIndex(prev <= 0 ? count - 1 : prev - 1);
          break;
        }
        case "Home":
          if (count === 0) return;
          event.preventDefault();
          updateActiveIndex(0);
          break;
        case "End":
          if (count === 0) return;
          event.preventDefault();
          updateActiveIndex(count - 1);
          break;
        case "Enter": {
          if (count === 0) return;
          // Only act when a menu option is focused — otherwise let the
          // default button behaviour on the trigger toggle the picker.
          const current = activeExtractIndexRef.current;
          if (current < 0 || current >= count) return;
          event.preventDefault();
          event.stopPropagation();
          const selected = corpusExtracts[current];
          if (selected) {
            // handleInsertComponent already calls setShowExtractPicker(false)
            // internally, so the picker is closed as part of the insertion.
            handleInsertComponent("extract-grid", { extractId: selected.id });
            extractPickerTriggerRef.current?.focus();
          }
          break;
        }
        default:
          break;
      }
    },
    [showExtractPicker, corpusExtracts, handleInsertComponent]
  );

  // Markdown renderer with generic component marker interception
  const {
    renderMarkdown: renderMarkdownPreview,
    customBlocks: previewCustomBlocks,
  } = useCamlComponentRenderer(CAML_COMPONENTS);

  const handleClose = () => {
    if (hasChanges) {
      setShowCloseConfirm(true);
    } else {
      onClose();
    }
  };

  return (
    <StyledModalWrapper>
      <Modal size="full" open={isOpen} onClose={handleClose}>
        <ModalHeader>
          <h2>
            <BookOpen size={18} />
            {isNew ? "Create Article" : "Edit Article"}
            {hasChanges && <UnsavedBadge>Unsaved changes</UnsavedBadge>}
          </h2>
        </ModalHeader>

        <ContentWrapper>
          <EditorPane>
            <PaneHeader>
              <Edit size={12} />
              CAML Source
            </PaneHeader>
            <EditorToolbar>
              <div ref={extractPickerRef} style={{ position: "relative" }}>
                <ToolbarBtn
                  ref={extractPickerTriggerRef}
                  type="button"
                  // WAI-ARIA combobox pattern: role="combobox" is required for
                  // aria-activedescendant to be valid.  A plain role="button"
                  // is NOT in the spec's allowed list, causing screen readers
                  // to silently ignore the active descendant announcement.
                  role="combobox"
                  aria-haspopup="listbox"
                  aria-expanded={showExtractPicker}
                  aria-controls={
                    showExtractPicker
                      ? "caml-extract-picker-listbox"
                      : undefined
                  }
                  aria-activedescendant={
                    showExtractPicker &&
                    activeExtractIndex >= 0 &&
                    activeExtractIndex < corpusExtracts.length
                      ? `caml-extract-picker-option-${corpusExtracts[activeExtractIndex].id}`
                      : undefined
                  }
                  onKeyDown={handleExtractPickerKeyDown}
                  onClick={(e) => {
                    e.stopPropagation();
                    setShowExtractPicker((v) => !v);
                  }}
                  onMouseDown={(e) => e.stopPropagation()}
                  aria-label="Insert extract grid table"
                >
                  <Table2 size={12} />
                  Insert Extract Grid
                </ToolbarBtn>
                {showExtractPicker && (
                  <ExtractPickerDropdown
                    id="caml-extract-picker-listbox"
                    role="listbox"
                    aria-label="Corpus extracts"
                  >
                    {extractsLoading ? (
                      <ExtractPickerEmpty>
                        Loading extracts...
                      </ExtractPickerEmpty>
                    ) : corpusExtracts.length === 0 ? (
                      <ExtractPickerEmpty>
                        No extracts found for this corpus.
                      </ExtractPickerEmpty>
                    ) : (
                      corpusExtracts.map((ext, index) => (
                        <ExtractPickerItem
                          tabIndex={-1}
                          type="button"
                          role="option"
                          id={`caml-extract-picker-option-${ext.id}`}
                          key={ext.id}
                          $active={index === activeExtractIndex}
                          aria-selected={false}
                          onMouseEnter={() => {
                            activeExtractIndexRef.current = index;
                            setActiveExtractIndex(index);
                          }}
                          onClick={() =>
                            handleInsertComponent("extract-grid", {
                              extractId: ext.id,
                            })
                          }
                        >
                          {ext.name}
                        </ExtractPickerItem>
                      ))
                    )}
                  </ExtractPickerDropdown>
                )}
              </div>
            </EditorToolbar>
            <EditorTextarea
              ref={textareaRef}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Write your CAML article here..."
              spellCheck={false}
            />
          </EditorPane>

          <PreviewPane>
            <PaneHeader>
              <Eye size={12} />
              Preview
            </PaneHeader>
            {parsedDocument && (
              <CamlThemeProvider>
                <CamlArticle
                  document={parsedDocument}
                  renderMarkdown={renderMarkdownPreview}
                  customBlocks={previewCustomBlocks}
                />
              </CamlThemeProvider>
            )}
          </PreviewPane>
        </ContentWrapper>

        <ActionBar>
          <ActionButton type="button" onClick={handleClose}>
            Close
          </ActionButton>
          <ActionButton
            type="button"
            $primary
            onClick={handleSave}
            disabled={(!hasChanges && !isNew) || saving}
          >
            <Save size={14} />
            {saving ? "Saving..." : isNew ? "Create Article" : "Save Changes"}
          </ActionButton>
        </ActionBar>
      </Modal>

      <ConfirmModal
        message="You have unsaved changes. Are you sure you want to close?"
        visible={showCloseConfirm}
        yesAction={onClose}
        noAction={() => {}}
        toggleModal={() => setShowCloseConfirm(false)}
        confirmVariant="danger"
        confirmLabel="Discard"
        cancelLabel="Keep editing"
      />
    </StyledModalWrapper>
  );
};
