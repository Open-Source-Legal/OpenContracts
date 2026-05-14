/**
 * useChatMentionPicker
 *
 * Shared wiring for the agent `@mention` picker used by both `ChatTray`
 * (document-scope chat) and `CorpusChat` (corpus-scope chat). Both surfaces
 * previously duplicated ~90 lines for:
 *   1. `useAgentMentionTrigger` + `useUnifiedMentionSearch` setup
 *   2. Mapping `mentionResults.agents` into `AgentItem[]`
 *   3. Portaling `AgentMentionPopover` to <body> with a fixed-position anchor
 *      derived from the textarea's bounding rect
 *   4. The `onSelect` handler that splices the markdown link via the trigger
 *      hook and restores the textarea caret on the next tick
 *   5. The `onValueChange` wrapper that forwards the textarea value + caret
 *      to the mention trigger
 *
 * This hook consolidates all of that. Each consumer now:
 *   - Calls `handleValueChange(value, caret)` from its textarea `onChange`
 *     after updating its own `newMessage` state
 *   - Renders `popoverNode` somewhere inside its chat input container
 *
 * The portal is anchored to the textarea via `textareaRef`, so layout in the
 * consumer is unaffected — the popover floats above any `overflow: hidden`
 * ancestor.
 *
 * Behavioural guarantees preserved from the original inline copies:
 *   - The popover only renders when `mention.isOpen && agentItems.length > 0`
 *   - Caret is restored via `setTimeout(..., 0)` after `setValue` so React
 *     has committed the spliced value before we call `setSelectionRange`
 *   - Positioning falls back to `left: 16` / `bottom: 80` when the textarea
 *     ref is not yet mounted (e.g. first render)
 */

import React, { RefObject, useMemo, useCallback } from "react";
import { createPortal } from "react-dom";
import {
  AgentMentionPopover,
  AgentItem,
} from "../components/chat/AgentMentionPopover";
import { useAgentMentionTrigger } from "./useAgentMentionTrigger";
import { useUnifiedMentionSearch } from "../components/threads/hooks/useUnifiedMentionSearch";
import { buildAgentMentionLink } from "../utils/agentMentionLink";

export interface UseChatMentionPickerOptions {
  /** Ref to the textarea — used for caret restoration and popover anchoring. */
  textareaRef: RefObject<HTMLTextAreaElement>;
  /**
   * The corpus the chat is bound to (optional — `ChatTray` may be mounted
   * without a corpus). Forwarded to `useUnifiedMentionSearch` so the
   * backend resolver can scope agent results (global + this corpus only).
   */
  corpusId?: string | null;
  /**
   * Called with the spliced textarea value when the user picks an agent.
   * Consumers wire this to their `setNewMessage` setter.
   */
  onValueChange: (next: string) => void;
}

export interface UseChatMentionPickerResult {
  /**
   * Forward the textarea's current value + caret position to the mention
   * trigger so it can detect `@<fragment>` and open/close the picker.
   * Call this from the textarea's `onChange` (after updating local state).
   */
  handleValueChange: (value: string, caret: number) => void;
  /**
   * Portal containing the `AgentMentionPopover`. Render this anywhere
   * inside the chat input container — its absolute position is anchored
   * to the textarea, so DOM placement doesn't affect layout. Returns
   * `null` when the picker is closed or has no agents to show.
   */
  popoverNode: React.ReactNode | null;
}

/**
 * Shared @mention picker wiring for chat surfaces. See module-level docstring
 * for the full contract.
 */
export function useChatMentionPicker({
  textareaRef,
  corpusId,
  onValueChange,
}: UseChatMentionPickerOptions): UseChatMentionPickerResult {
  const mention = useAgentMentionTrigger();
  const { categorizedResults: mentionCategorizedResults } =
    useUnifiedMentionSearch(mention.fragment, corpusId ?? undefined);

  const agentItems: AgentItem[] = useMemo(
    () =>
      mentionCategorizedResults.agents
        .map((r) => {
          if (!r.agent) return null;
          return {
            id: r.agent.id,
            slug: r.agent.slug,
            name: r.agent.name,
            scope: r.agent.scope,
            corpus: r.agent.corpus
              ? {
                  slug: r.agent.corpus.slug,
                  title: r.agent.corpus.title,
                }
              : null,
          } as AgentItem;
        })
        .filter((a): a is AgentItem => a !== null),
    [mentionCategorizedResults.agents]
  );

  const handleValueChange = useCallback(
    (value: string, caret: number) => {
      mention.onValueChange(value, caret);
    },
    [mention]
  );

  const popoverNode =
    mention.isOpen && agentItems.length > 0
      ? createPortal(
          // Portal to <body> so the picker isn't clipped by ancestor
          // `overflow: hidden` and stacks above the messages layer.
          // Position anchored to the textarea's bounding rect.
          <div
            data-testid="agent-mention-anchor"
            style={(() => {
              const rect = textareaRef.current?.getBoundingClientRect();
              return {
                position: "fixed",
                left: rect ? rect.left : 16,
                bottom: rect
                  ? Math.max(8, window.innerHeight - rect.top + 6)
                  : 80,
                zIndex: 1000,
                pointerEvents: "auto",
              };
            })()}
          >
            <AgentMentionPopover
              fragment={mention.fragment}
              agents={agentItems}
              onSelect={(a) => {
                const { value, caretPos } = mention.onSelect({
                  slug: a.slug,
                  name: a.name,
                  url: buildAgentMentionLink({
                    slug: a.slug,
                    scope: a.scope,
                    corpus: a.corpus,
                  }).url,
                });
                onValueChange(value);
                setTimeout(() => {
                  const ta = textareaRef.current;
                  if (ta) {
                    ta.focus();
                    ta.setSelectionRange(caretPos, caretPos);
                  }
                }, 0);
              }}
              onDismiss={mention.onDismiss}
            />
          </div>,
          document.body
        )
      : null;

  return { handleValueChange, popoverNode };
}
