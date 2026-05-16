import React, { useEffect, useRef, useState } from "react";
import styled from "styled-components";
import { color } from "../../theme/colors";
import { spacing } from "../../theme/spacing";

/**
 * Slim popover for selecting an agent to @mention in chat input.
 *
 * Design choice (Task 9): we considered wrapping
 * `frontend/src/components/threads/UnifiedMentionPicker.tsx` since CLAUDE.md
 * says "Re-use, don't fork". However, UnifiedMentionPicker:
 *   - Requires the caller to manage `selectedIndex` and to forward keyboard
 *     events through an imperative ref (`useImperativeHandle`).
 *   - Operates on the richer `UnifiedMentionResource` shape with cross-type
 *     categorization (users/corpuses/documents/annotations/agents).
 *   - Triggers GraphQL searches via `useUnifiedMentionSearch` for multi-type
 *     auto-suggest.
 *
 * Phase 1 of the rich-mention agent delegation feature only needs an
 * agent-only picker driven by a fragment string and a pre-fetched agent
 * list (the agents are fetched once at chat-open time and filtered locally).
 * Wrapping UnifiedMentionPicker would require either adapting that local
 * list into `UnifiedMentionResource` plus re-implementing keyboard state
 * locally, or threading new "agent-only" props through it — both of which
 * are heavier than this slim component. We will revisit consolidation in
 * a later phase once both pickers share more behavior.
 *
 * Styling mirrors UnifiedMentionPicker's theme-token usage (no hex literals)
 * so visual treatment stays consistent across mention surfaces.
 *
 * Accessibility: arrow-key navigation + Enter-to-select are wired via a
 * document-level capture-phase keydown listener so the picker behaves even
 * though keyboard focus stays in the parent textarea. ``aria-selected`` on
 * each option mirrors the active row so AT users get audible feedback.
 */

const Container = styled.div`
  background: ${color.N1};
  border: 1px solid ${color.N4};
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
  max-height: 240px;
  overflow-y: auto;
  min-width: 240px;
`;

const NoResults = styled.div`
  padding: ${spacing.xs} ${spacing.sm};
  color: ${color.N7};
  font-size: 13px;
`;

const OptionButton = styled.button<{ $active: boolean }>`
  display: block;
  width: 100%;
  text-align: left;
  padding: ${spacing.xs} ${spacing.sm};
  background: ${(p) => (p.$active ? color.N2 : "transparent")};
  border: none;
  cursor: pointer;
  font-size: 13px;
  color: ${color.N10};
  transition: background 0.15s;

  &:hover {
    background: ${color.N2};
  }
`;

const OptionName = styled.strong`
  font-weight: 600;
  color: ${color.N10};
`;

const OptionMeta = styled.span`
  color: ${color.N7};
`;

export interface AgentItem {
  id: string;
  slug: string;
  name: string;
  scope: "GLOBAL" | "CORPUS";
  corpus?: { slug: string; title: string } | null;
}

interface Props {
  fragment: string;
  agents: AgentItem[];
  onSelect: (agent: AgentItem) => void;
  onDismiss: () => void;
}

export const AgentMentionPopover: React.FC<Props> = ({
  fragment,
  agents,
  onSelect,
  onDismiss,
}) => {
  const lower = fragment.toLowerCase();
  const matches = agents.filter(
    (a) =>
      a.slug.toLowerCase().includes(lower) ||
      a.name.toLowerCase().includes(lower)
  );

  const [activeIndex, setActiveIndex] = useState(0);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);

  // Reset selection when the result set shrinks/grows so the highlight
  // never points past the last row.
  useEffect(() => {
    setActiveIndex(0);
  }, [matches.length, fragment]);

  // Document-level capture so the listener fires before the textarea
  // consumes Arrow/Enter (the textarea retains focus while the picker is
  // open). Escape continues to dismiss even when no matches are visible.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        onDismiss();
        return;
      }
      if (matches.length === 0) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        e.stopPropagation();
        setActiveIndex((i) => (i + 1) % matches.length);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        e.stopPropagation();
        setActiveIndex((i) => (i - 1 + matches.length) % matches.length);
      } else if (e.key === "Enter") {
        e.preventDefault();
        e.stopPropagation();
        const next = matches[activeIndex];
        if (next) onSelect(next);
      }
    };
    document.addEventListener("keydown", handler, true);
    return () => document.removeEventListener("keydown", handler, true);
  }, [matches, activeIndex, onSelect, onDismiss]);

  // Keep the active row visible inside the scroll container.
  useEffect(() => {
    optionRefs.current[activeIndex]?.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  return (
    <Container role="listbox" data-testid="agent-mention-popover">
      {matches.length === 0 && <NoResults>No matching agents.</NoResults>}
      {matches.map((a, i) => (
        <OptionButton
          key={a.id}
          ref={(el) => {
            optionRefs.current[i] = el;
          }}
          role="option"
          aria-selected={i === activeIndex}
          $active={i === activeIndex}
          onMouseEnter={() => setActiveIndex(i)}
          onClick={() => onSelect(a)}
        >
          <OptionName>{a.name}</OptionName> <OptionMeta>@{a.slug}</OptionMeta>
          {a.scope === "CORPUS" && a.corpus && (
            <OptionMeta> · {a.corpus.title}</OptionMeta>
          )}
        </OptionButton>
      ))}
    </Container>
  );
};
