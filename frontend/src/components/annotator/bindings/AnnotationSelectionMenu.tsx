/**
 * The menu shown for a text selection in the PDF/DOCX viewer, rendered in
 * `@os-legal/react-contract-annotate`'s `renderSelectionMenu` slot (the
 * library positions it at the selection and portals it out of the viewer).
 *
 * Copy Text and Copy Link work in every mode; creating an annotation or a
 * link needs an editable document in a corpus the user may update, and
 * Apply Label needs an active label. Keyboard: C copies the text, L the
 * link, A applies the label, Escape cancels.
 */
import React, { useCallback, useEffect, useRef } from "react";
import type { SelectionMenuContext } from "@os-legal/react-contract-annotate/core";
import { AlertCircle, Copy, Link, Link2, Settings, Tag, X } from "lucide-react";
import { useLocation } from "react-router-dom";

import {
  encodeTextBlock,
  textBlockFromMultipageJson,
  textBlockFromSpan,
} from "../../../utils/textBlockEncoding";
import { MultipageAnnotationJson, SpanAnnotationJson } from "../../types";
import {
  ActionMenuItem,
  HelpMessage,
  HelpText,
  MenuDivider,
  SelectionActionMenu,
  ShortcutHint,
} from "../components/SelectionActionMenu";
import { useCorpusState } from "../context/CorpusAtom";
import { useAnnotationControls } from "../context/UISettingsAtom";
import { ViewerFormat } from "./convert";

export interface AnnotationSelectionMenuProps {
  ctx: SelectionMenuContext;
  format: ViewerFormat;
  readOnly: boolean;
  /**
   * Starts creating an OC_URL link annotation from this selection (the
   * caller asks for the URL). Omitted where links cannot be created.
   */
  onStartCreateLink?: (ctx: SelectionMenuContext) => void;
}

/** A `?tb=` deep link to the selected text on the current page. */
function textBlockLink(
  ctx: SelectionMenuContext,
  format: ViewerFormat,
  pathname: string,
  search: string
): string | null {
  const block =
    format === "docx"
      ? textBlockFromSpan(
          (ctx.pending.json as SpanAnnotationJson).start,
          (ctx.pending.json as SpanAnnotationJson).end
        )
      : textBlockFromMultipageJson(ctx.pending.json as MultipageAnnotationJson);
  if (block.type === "pdf" && Object.keys(block.tokensByPage).length === 0) {
    return null;
  }
  const params = new URLSearchParams(search);
  params.set("tb", encodeTextBlock(block));
  return `${window.location.origin}${pathname}?${params.toString()}`;
}

export const AnnotationSelectionMenu: React.FC<
  AnnotationSelectionMenuProps
> = ({ ctx, format, readOnly, onStartCreateLink }) => {
  const location = useLocation();
  const { canUpdateCorpus, selectedCorpus, humanSpanLabels, humanTokenLabels } =
    useCorpusState();
  const { activeSpanLabel } = useAnnotationControls();
  const menuRef = useRef<HTMLDivElement>(null);

  const canAnnotate = !readOnly && canUpdateCorpus;
  const hasLabelset = Boolean(selectedCorpus?.labelSet);
  const hasLabels = humanTokenLabels.length > 0 || humanSpanLabels.length > 0;

  const copyText = useCallback(() => {
    void ctx.copyText();
    ctx.clear();
  }, [ctx]);

  const copyLink = useCallback(() => {
    const url = textBlockLink(ctx, format, location.pathname, location.search);
    if (url) navigator.clipboard.writeText(url).catch(() => {});
    ctx.clear();
  }, [ctx, format, location.pathname, location.search]);

  const applyLabel = useCallback(() => {
    if (canAnnotate && activeSpanLabel) ctx.commit();
    else ctx.clear();
  }, [ctx, canAnnotate, activeSpanLabel]);

  // Shortcuts and dismissal, while the menu is shown.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      switch (event.key.toLowerCase()) {
        case "c":
          event.preventDefault();
          copyText();
          break;
        case "l":
          event.preventDefault();
          copyLink();
          break;
        case "a":
          if (canAnnotate && activeSpanLabel) {
            event.preventDefault();
            applyLabel();
          }
          break;
        case "escape":
          event.preventDefault();
          ctx.clear();
          break;
      }
    };
    const onMouseDown = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) ctx.clear();
    };
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onMouseDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onMouseDown);
    };
  }, [ctx, copyText, copyLink, applyLabel, canAnnotate, activeSpanLabel]);

  return (
    <SelectionActionMenu ref={menuRef} data-testid="selection-action-menu">
      <ActionMenuItem onClick={copyText} data-testid="copy-text-button">
        <Copy size={16} />
        <span>Copy Text</span>
        <ShortcutHint>C</ShortcutHint>
      </ActionMenuItem>

      <ActionMenuItem onClick={copyLink} data-testid="copy-link-button">
        <Link size={16} />
        <span>Copy Link</span>
        <ShortcutHint>L</ShortcutHint>
      </ActionMenuItem>

      <MenuDivider />
      {canAnnotate ? (
        <>
          {onStartCreateLink && (
            <ActionMenuItem
              onClick={() => onStartCreateLink(ctx)}
              data-testid="create-link-button"
            >
              <Link2 size={16} />
              <span>Add link…</span>
            </ActionMenuItem>
          )}
          {activeSpanLabel ? (
            <ActionMenuItem
              onClick={applyLabel}
              data-testid="apply-label-button"
            >
              <Tag size={16} />
              <span>Apply Label: {activeSpanLabel.text}</span>
              <ShortcutHint>A</ShortcutHint>
            </ActionMenuItem>
          ) : !hasLabelset ? (
            <HelpMessage>
              <AlertCircle size={16} />
              <div>
                <span>No labelset configured</span>
                <HelpText>
                  Click the label selector (bottom right) to create one
                </HelpText>
              </div>
            </HelpMessage>
          ) : !hasLabels ? (
            <HelpMessage>
              <AlertCircle size={16} />
              <div>
                <span>No labels available</span>
                <HelpText>Click the label selector to create labels</HelpText>
              </div>
            </HelpMessage>
          ) : (
            <HelpMessage>
              <Settings size={16} />
              <div>
                <span>Select a label to annotate</span>
                <HelpText>Click the label selector (bottom right)</HelpText>
              </div>
            </HelpMessage>
          )}
        </>
      ) : (
        <HelpMessage>
          <AlertCircle size={16} />
          <div>
            <span>Annotation unavailable</span>
            <HelpText>
              {readOnly ? "Document is read-only" : "No corpus permissions"}
            </HelpText>
          </div>
        </HelpMessage>
      )}

      <MenuDivider />
      <ActionMenuItem onClick={() => ctx.clear()} data-testid="cancel-button">
        <X size={16} />
        <span>Cancel</span>
        <ShortcutHint>ESC</ShortcutHint>
      </ActionMenuItem>
    </SelectionActionMenu>
  );
};
