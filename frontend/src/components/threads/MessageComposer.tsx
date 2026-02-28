import React, { useCallback, useEffect, useRef, useState } from "react";
import { useEditor, EditorContent, Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import Mention from "@tiptap/extension-mention";
import Link from "@tiptap/extension-link";
import { Markdown } from "tiptap-markdown";
import { ReactRenderer } from "@tiptap/react";
import { computePosition, flip, shift, offset } from "@floating-ui/dom";
import styled from "styled-components";
import { Send, Bold, Italic, List, ListOrdered } from "lucide-react";
import {
  CORPUS_COLORS,
  CORPUS_FONTS,
  CORPUS_RADII,
  CORPUS_SHADOWS,
  CORPUS_TRANSITIONS,
  mediaQuery,
} from "./styles/discussionStyles";
import { MENTION_PREVIEW_LENGTH } from "../../assets/configurations/constants";
import {
  UnifiedMentionPicker,
  UnifiedMentionPickerRef,
} from "./UnifiedMentionPicker";
import {
  useUnifiedMentionSearch,
  UnifiedMentionResource,
} from "./hooks/useUnifiedMentionSearch";
import { sanitizeForMention } from "../../utils/textSanitization";
import type { MarkdownStorage } from "tiptap-markdown";

const Toolbar = styled.div`
  display: flex;
  align-items: center;
  gap: 0.25rem;
  background: ${CORPUS_COLORS.slate[50]};
  max-height: 0;
  overflow: hidden;
  padding: 0 0.5rem;
  border-bottom: none;
  transition: max-height ${CORPUS_TRANSITIONS.normal},
    padding ${CORPUS_TRANSITIONS.normal},
    border-bottom ${CORPUS_TRANSITIONS.normal};

  /* Mobile: Larger touch targets */
  ${mediaQuery.mobile} {
    gap: 0.5rem;
  }
`;

const ToolbarButton = styled.button<{ $isActive?: boolean }>`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border: none;
  border-radius: ${CORPUS_RADII.sm};
  background: ${({ $isActive }) =>
    $isActive ? CORPUS_COLORS.teal[100] : "transparent"};
  color: ${({ $isActive }) =>
    $isActive ? CORPUS_COLORS.teal[700] : CORPUS_COLORS.slate[600]};
  cursor: pointer;
  transition: all ${CORPUS_TRANSITIONS.fast};

  &:hover:not(:disabled) {
    background: ${CORPUS_COLORS.teal[50]};
    color: ${CORPUS_COLORS.teal[700]};
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  svg {
    width: 1rem;
    height: 1rem;
  }

  /* Mobile: Larger touch targets */
  ${mediaQuery.mobile} {
    width: 2.5rem;
    height: 2.5rem;
    border-radius: ${CORPUS_RADII.md};

    svg {
      width: 1.125rem;
      height: 1.125rem;
    }
  }
`;

const EditorContainer = styled.div`
  flex: 1;
  padding: 0.5rem 0.875rem;
  min-height: 2.5rem;
  max-height: 25rem;
  overflow-y: auto;
  transition: min-height ${CORPUS_TRANSITIONS.normal};

  .ProseMirror {
    outline: none;
    min-height: 1.25rem;
    font-family: ${CORPUS_FONTS.sans};
    font-size: 0.9375rem;
    color: ${CORPUS_COLORS.slate[800]};
    line-height: 1.6;

    p.is-editor-empty:first-child::before {
      content: attr(data-placeholder);
      float: left;
      color: ${CORPUS_COLORS.slate[400]};
      pointer-events: none;
      height: 0;
    }

    p {
      margin: 0 0 0.5rem 0;

      &:last-child {
        margin-bottom: 0;
      }
    }

    ul,
    ol {
      padding-left: 1.5rem;
      margin: 0.5rem 0;
    }

    strong {
      font-weight: 600;
    }

    em {
      font-style: italic;
    }

    /* Mention styling */
    .mention {
      padding: 0.125rem 0.375rem;
      border-radius: ${CORPUS_RADII.sm};
      font-weight: 500;
      font-size: 0.9em;
    }

    .mention-user {
      background-color: ${CORPUS_COLORS.teal[50]};
      color: ${CORPUS_COLORS.teal[700]};
    }

    .mention-resource {
      background: linear-gradient(
        135deg,
        ${CORPUS_COLORS.teal[50]} 0%,
        #f0fdfa 100%
      );
      color: ${CORPUS_COLORS.teal[700]};
      border: 1px solid ${CORPUS_COLORS.teal[200]};
    }

    /* Agent mention link styling */
    a[href^="/agents/"],
    a[href*="/agents/"] {
      background: linear-gradient(
        135deg,
        ${CORPUS_COLORS.teal[50]} 0%,
        #f0fdfa 100%
      );
      color: ${CORPUS_COLORS.teal[700]};
      padding: 0.125rem 0.375rem;
      border-radius: ${CORPUS_RADII.sm};
      font-weight: 500;
      text-decoration: none;
      border: 1px solid ${CORPUS_COLORS.teal[200]};

      &:hover {
        background: ${CORPUS_COLORS.teal[100]};
      }
    }
  }
`;

const Footer = styled.div`
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 0.375rem 0.5rem;
  border-top: 1px solid ${CORPUS_COLORS.slate[100]};
  background: transparent;
  transition: padding ${CORPUS_TRANSITIONS.normal},
    background ${CORPUS_TRANSITIONS.normal};
`;

const CharacterCount = styled.span`
  display: none;
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.75rem;
  color: ${CORPUS_COLORS.slate[400]};
`;

const ComposerContainer = styled.div`
  display: flex;
  flex-direction: column;
  border: 2px solid ${CORPUS_COLORS.slate[200]};
  border-radius: ${CORPUS_RADII.xl};
  background: ${CORPUS_COLORS.white};
  overflow: hidden;
  box-shadow: ${CORPUS_SHADOWS.sm};
  transition: all ${CORPUS_TRANSITIONS.normal};

  &:focus-within {
    border-color: ${CORPUS_COLORS.teal[500]};
    box-shadow: 0 0 0 3px ${CORPUS_COLORS.teal[50]}, ${CORPUS_SHADOWS.md};

    ${Toolbar} {
      max-height: 3rem;
      padding: 0.5rem;
      border-bottom: 1px solid ${CORPUS_COLORS.slate[200]};
    }

    ${EditorContainer} {
      min-height: 5rem;
    }

    ${EditorContainer} .ProseMirror {
      min-height: 3.5rem;
    }

    ${Footer} {
      padding: 0.5rem 0.875rem;
      background: ${CORPUS_COLORS.slate[50]};
      justify-content: space-between;
    }

    ${CharacterCount} {
      display: inline;
    }
  }
`;

const SendButton = styled.button`
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.4rem 0.875rem;
  border: none;
  border-radius: ${CORPUS_RADII.lg};
  background: linear-gradient(
    135deg,
    ${CORPUS_COLORS.teal[600]} 0%,
    ${CORPUS_COLORS.teal[700]} 100%
  );
  color: ${CORPUS_COLORS.white};
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.8125rem;
  font-weight: 600;
  cursor: pointer;
  transition: all ${CORPUS_TRANSITIONS.normal};
  box-shadow: 0 2px 8px rgba(15, 118, 110, 0.25);
  letter-spacing: -0.01em;

  &:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(15, 118, 110, 0.45);
    background: linear-gradient(
      135deg,
      ${CORPUS_COLORS.teal[500]} 0%,
      ${CORPUS_COLORS.teal[600]} 100%
    );
  }

  &:active:not(:disabled) {
    transform: translateY(0);
    box-shadow: 0 2px 8px rgba(15, 118, 110, 0.3);
  }

  &:disabled {
    opacity: 0.4;
    cursor: not-allowed;
    transform: none;
    box-shadow: 0 2px 6px rgba(15, 118, 110, 0.2);
  }

  svg {
    width: 1.125rem;
    height: 1.125rem;
  }
`;

const ErrorMessage = styled.div`
  padding: 0.5rem 0.75rem;
  background: #fee2e2;
  color: #dc2626;
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.8125rem;
  border-top: 1px solid #fca5a5;
`;

export interface MessageComposerProps {
  /** Placeholder text for empty editor */
  placeholder?: string;
  /** Initial content (HTML string) */
  initialContent?: string;
  /** Maximum character count (default: 10000) */
  maxLength?: number;
  /** Called when user submits message */
  onSubmit: (content: string) => void | Promise<void>;
  /** Called when content changes */
  onChange?: (content: string) => void;
  /** Disable the composer (e.g., while submitting) */
  disabled?: boolean;
  /** Error message to display */
  error?: string;
  /** Auto-focus on mount */
  autoFocus?: boolean;
  /** Enable @ mentions (default: true) */
  enableMentions?: boolean;
  /** Corpus ID for context-aware annotation search */
  corpusId?: string;
}

export function MessageComposer({
  placeholder = "Write your message...",
  initialContent = "",
  maxLength = 10000,
  onSubmit,
  onChange,
  disabled = false,
  error,
  autoFocus = false,
  enableMentions = true,
  corpusId,
}: MessageComposerProps) {
  const [mentionSearchQuery, setMentionSearchQuery] = React.useState("");
  const [characterCount, setCharacterCount] = React.useState(0);

  // Unified mention search for all resource types
  const { allResults, loading, hint } = useUnifiedMentionSearch(
    mentionSearchQuery,
    corpusId // Context-aware annotation search
  );

  // Use ref to always get latest results (TipTap captures closure)
  const allResultsRef = useRef(allResults);
  const loadingRef = useRef(loading);
  const hintRef = useRef(hint);
  const mentionComponentRef = useRef<any>(null);

  useEffect(() => {
    allResultsRef.current = allResults;
    loadingRef.current = loading;
    hintRef.current = hint;

    // Update the component props when results arrive
    if (mentionComponentRef.current) {
      mentionComponentRef.current.updateProps({
        resources: allResults,
        loading,
        hint,
      });
    }
  }, [allResults, loading, hint]);
  const editor = useEditor({
    // Use TipTap's built-in autofocus - handles mount timing correctly
    autofocus: autoFocus,
    extensions: [
      StarterKit.configure({
        // Disable code blocks and blockquotes for simpler UX
        codeBlock: false,
        blockquote: false,
      }),
      Markdown.configure({
        html: false, // Disable HTML in markdown
        linkify: false, // Disable - use Link extension's autolink instead (avoids duplicate 'link' warning)
        breaks: true, // Convert \n to <br>
      }),
      Link.configure({
        openOnClick: false, // Don't open links while editing
        autolink: true, // Auto-convert URLs to links (replaces Markdown's linkify)
        HTMLAttributes: {
          class: "mention-link", // Style mention links
        },
      }),
      Placeholder.configure({
        placeholder,
      }),
      ...(enableMentions
        ? [
            Mention.configure({
              HTMLAttributes: {
                class: "mention mention-unified",
              },
              suggestion: {
                char: "@",
                items: ({ query }: { query: string }) => {
                  // Trigger unified search for all resource types
                  setMentionSearchQuery(query);
                  return allResultsRef.current;
                },
                render: () => {
                  let component: ReactRenderer<UnifiedMentionPickerRef> | null =
                    null;
                  let popup: HTMLDivElement | null = null;

                  const updatePosition = (props: any) => {
                    if (!popup || !props.clientRect) return;

                    const virtualReference = {
                      getBoundingClientRect: props.clientRect,
                    };

                    computePosition(virtualReference, popup, {
                      placement: "bottom-start",
                      middleware: [offset(8), flip(), shift({ padding: 8 })],
                    }).then(({ x, y }) => {
                      Object.assign(popup!.style, {
                        left: `${x}px`,
                        top: `${y}px`,
                      });
                    });
                  };

                  /**
                   * Generate mention format and deep link URL based on resource type
                   */
                  const getMentionData = (resource: UnifiedMentionResource) => {
                    switch (resource.type) {
                      case "user":
                        // Use slug if available, fallback to ID (auto-redirects to slug)
                        const userIdent =
                          resource.user!.slug || resource.user!.id;
                        return {
                          label: `@${resource.user!.username}`,
                          href: `/users/${userIdent}`,
                          type: "user",
                        };

                      case "corpus":
                        // Issue #689: Show corpus name instead of cryptic slug
                        return {
                          label: resource.title,
                          href: `/c/${resource.corpus!.creator.slug}/${
                            resource.corpus!.slug
                          }`,
                          type: "corpus",
                        };

                      case "document":
                        const doc = resource.document!;
                        const corpus = doc.corpus;
                        // Issue #689: Show document title instead of cryptic slug format
                        // Include corpus context if available
                        const docLabel = corpus
                          ? `${resource.title} (in ${corpus.title})`
                          : resource.title;
                        return {
                          label: docLabel,
                          href: corpus
                            ? `/d/${corpus.creator.slug}/${corpus.slug}/${doc.slug}`
                            : `/d/${doc.creator.slug}/${doc.slug}`,
                          type: "document",
                        };

                      case "annotation":
                        const ann = resource.annotation!;
                        const annDoc = ann.document;
                        const annCorpus = ann.corpus;
                        // Deep link to annotation in document with optimal viewer settings
                        // URL pattern: /d/{creatorSlug}/{corpusSlug}/{docSlug} or /d/{creatorSlug}/{docSlug}
                        const baseUrl = annCorpus
                          ? `/d/${annCorpus.creator.slug}/${annCorpus.slug}/${annDoc.slug}`
                          : `/d/${annDoc.creator.slug}/${annDoc.slug}`;
                        // Issue #689: Show annotation text preview instead of cryptic ID
                        // Format: "Text preview..." (Label) in Document
                        // Sanitize user-generated content to prevent XSS (per CLAUDE.md)
                        const labelText = ann.label?.text ?? "Annotation";
                        const sanitizedRawText = ann.rawText
                          ? sanitizeForMention(ann.rawText)
                          : null;
                        const annTextPreview = sanitizedRawText
                          ? sanitizedRawText.length > MENTION_PREVIEW_LENGTH
                            ? `"${sanitizedRawText.substring(
                                0,
                                MENTION_PREVIEW_LENGTH
                              )}…"`
                            : `"${sanitizedRawText}"`
                          : `[${labelText}]`;
                        const annLabel = `${annTextPreview} (${labelText})`;
                        return {
                          label: annLabel,
                          href: `${baseUrl}?ann=${resource.id}&structural=true`,
                          type: "annotation",
                        };

                      case "agent":
                        const agent = resource.agent!;
                        // Use the mention format from the agent, or construct it
                        const agentLabel =
                          agent.mentionFormat || `@agent:${agent.slug}`;
                        // Agent URL - global agents at /agents/{slug}, corpus agents at corpus path
                        // URL-encode the corpus title to handle spaces and special characters
                        const agentHref =
                          agent.scope === "GLOBAL"
                            ? `/agents/${encodeURIComponent(agent.slug)}`
                            : agent.corpus
                            ? `/c/${agent.corpus.id}/${encodeURIComponent(
                                agent.corpus.title
                              )}/agents/${encodeURIComponent(agent.slug)}`
                            : `/agents/${encodeURIComponent(agent.slug)}`;
                        return {
                          label: agentLabel,
                          href: agentHref,
                          type: "agent",
                        };

                      default:
                        return {
                          label: `@${resource.title}`,
                          href: null,
                          type: "unknown",
                        };
                    }
                  };

                  return {
                    onStart: (props: any) => {
                      component = new ReactRenderer(UnifiedMentionPicker, {
                        props: {
                          ...props,
                          resources: allResultsRef.current,
                          loading: loadingRef.current,
                          hint: hintRef.current,
                          onSelect: (resource: UnifiedMentionResource) => {
                            // Generate mention with deep link as markdown [text](url)
                            const mentionData = getMentionData(resource);

                            // Delete the @ trigger character and insert link
                            props.editor
                              .chain()
                              .focus()
                              .deleteRange(props.range) // Delete @query
                              .insertContent([
                                {
                                  type: "text",
                                  marks: mentionData.href
                                    ? [
                                        {
                                          type: "link",
                                          attrs: { href: mentionData.href },
                                        },
                                      ]
                                    : [],
                                  text: mentionData.label,
                                },
                                { type: "text", text: " " }, // Add space after mention
                              ])
                              .run();
                          },
                        },
                        editor: props.editor,
                      });

                      // Store component ref for updates when results arrive
                      mentionComponentRef.current = component;

                      if (!props.clientRect) {
                        return;
                      }

                      popup = document.createElement("div");
                      popup.style.position = "absolute";
                      popup.style.zIndex = "9999";
                      popup.appendChild(component.element);
                      document.body.appendChild(popup);

                      updatePosition(props);
                    },

                    onUpdate(props: any) {
                      component?.updateProps({
                        ...props,
                        resources: allResultsRef.current,
                        loading: loadingRef.current,
                        hint: hintRef.current,
                        onSelect: (resource: UnifiedMentionResource) => {
                          const mentionData = getMentionData(resource);

                          // Delete the @ trigger character and insert link
                          props.editor
                            .chain()
                            .focus()
                            .deleteRange(props.range)
                            .insertContent([
                              {
                                type: "text",
                                marks: mentionData.href
                                  ? [
                                      {
                                        type: "link",
                                        attrs: { href: mentionData.href },
                                      },
                                    ]
                                  : [],
                                text: mentionData.label,
                              },
                              { type: "text", text: " " },
                            ])
                            .run();
                        },
                      });

                      updatePosition(props);
                    },

                    onKeyDown(props: any) {
                      if (props.event.key === "Escape") {
                        return true;
                      }

                      return component?.ref?.onKeyDown(props) ?? false;
                    },

                    onExit() {
                      popup?.remove();
                      component?.destroy();
                      mentionComponentRef.current = null;
                    },
                  };
                },
              },
            }),
          ]
        : []),
    ],
    content: initialContent,
    editable: !disabled,
    onUpdate: ({ editor }) => {
      const text = editor.getText();
      setCharacterCount(text.length);
      // Export as Markdown instead of HTML
      const markdown = (editor.storage as any).markdown.getMarkdown();
      onChange?.(markdown);
    },
  });

  // Update editor content when initialContent changes
  useEffect(() => {
    if (!editor || !initialContent) return;

    try {
      if (editor.getHTML() !== initialContent) {
        editor.commands.setContent(initialContent);
        setCharacterCount(editor.getText().length);
      }
    } catch (err) {
      console.debug("Editor not ready for content update, will retry");
    }
  }, [editor, initialContent]);

  // Initialize character count when editor is created
  useEffect(() => {
    if (!editor) return;

    try {
      setCharacterCount(editor.getText().length);
    } catch (err) {
      console.debug("Editor not ready for character count, will retry");
    }
  }, [editor]);

  // Update editor editable state when disabled changes
  useEffect(() => {
    if (editor) {
      editor.setEditable(!disabled);
    }
  }, [editor, disabled]);

  // Note: autofocus is handled via TipTap's built-in `autofocus` option in useEditor
  // This ensures proper timing (waits for view to mount) and avoids the
  // "editor view is not available" error that occurred with manual focus.

  const handleSubmit = useCallback(async () => {
    if (!editor || disabled) return;

    // Export as Markdown instead of HTML
    const content = (editor.storage as any).markdown.getMarkdown();
    const text = editor.getText();

    // Validate
    if (!text.trim()) {
      return;
    }

    if (text.length > maxLength) {
      return;
    }

    try {
      await onSubmit(content);
      // Clear editor on success
      editor.commands.clearContent();
      setCharacterCount(0);
    } catch (err) {
      // Parent component handles error display
      console.error("Failed to submit message:", err);
    }
  }, [editor, disabled, maxLength, onSubmit]);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      // Submit on Cmd/Ctrl+Enter
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
        event.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit]
  );

  useEffect(() => {
    if (!editor) return;

    try {
      // TipTap's view.dom getter throws if editor isn't fully mounted
      const editorElement = editor.view?.dom;
      if (editorElement) {
        editorElement.addEventListener("keydown", handleKeyDown as any);
        return () => {
          editorElement.removeEventListener("keydown", handleKeyDown as any);
        };
      }
    } catch (err) {
      // Editor not fully mounted yet, will retry on next render
      console.debug("Editor view not ready yet, skipping keydown listener");
    }
  }, [editor, handleKeyDown]);

  if (!editor) {
    return null;
  }

  // Use state-based character count for reactivity
  let isEmpty = characterCount === 0;
  let isOverLimit = characterCount > maxLength;

  // Safely check if editor has content (TipTap might not be ready yet)
  try {
    isEmpty = characterCount === 0 || !editor.getText().trim();
  } catch (err) {
    // Editor not fully mounted, default to empty
    isEmpty = true;
  }

  return (
    <ComposerContainer>
      <Toolbar>
        <ToolbarButton
          $isActive={editor.isActive("bold")}
          onClick={() => editor.chain().focus().toggleBold().run()}
          disabled={disabled}
          title="Bold (Cmd+B)"
        >
          <Bold />
        </ToolbarButton>
        <ToolbarButton
          $isActive={editor.isActive("italic")}
          onClick={() => editor.chain().focus().toggleItalic().run()}
          disabled={disabled}
          title="Italic (Cmd+I)"
        >
          <Italic />
        </ToolbarButton>
        <ToolbarButton
          $isActive={editor.isActive("bulletList")}
          onClick={() => editor.chain().focus().toggleBulletList().run()}
          disabled={disabled}
          title="Bullet List"
        >
          <List />
        </ToolbarButton>
        <ToolbarButton
          $isActive={editor.isActive("orderedList")}
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
          disabled={disabled}
          title="Numbered List"
        >
          <ListOrdered />
        </ToolbarButton>
      </Toolbar>

      <EditorContainer>
        <EditorContent editor={editor} />
      </EditorContainer>

      <Footer>
        <CharacterCount>
          {characterCount} / {maxLength}
          {isOverLimit && " (too long)"}
        </CharacterCount>
        <SendButton
          onClick={handleSubmit}
          disabled={disabled || isEmpty || isOverLimit}
          title="Send (Cmd+Enter)"
        >
          <Send />
          Send
        </SendButton>
      </Footer>

      {error && <ErrorMessage>{error}</ErrorMessage>}
    </ComposerContainer>
  );
}
